import logging
import subprocess
from src.db import PostgresClient

class Migrator:
    def __init__(self, config):
        self.config = config
        self.source_conn = config.get_source_dict()
        self.dest_conn = config.get_dest_dict()
        self.replication_cfg = config.get_replication()

    def step4_migrate_schema(self, drop_dest=False):
        """Step 4: Copy schema using pg_dump -s | psql (local commands)."""
        logging.info("[BOTH] Starting schema migration...")
        src_db = self.source_conn['database']
        src_user = self.source_conn['user']
        src_host = self.source_conn['host']
        src_port = self.source_conn['port']
        src_pass = self.source_conn.get('password', '')

        dst_db = self.dest_conn['database']
        dst_user = self.dest_conn['user']
        dst_host = self.dest_conn['host']
        dst_port = self.dest_conn['port']
        dst_pass = self.dest_conn.get('password', '')

        if drop_dest:
            logging.info(f"[DEST] Targeting maintenance database to drop and recreate '{dst_db}'...")
            import psycopg
            
            # Pre-cleanup target DB: terminate active logical replication slots and subscriptions
            try:
                tgt_conn_str = f"host={dst_host} port={dst_port} user={dst_user} dbname={dst_db} password={dst_pass}"
                with psycopg.connect(tgt_conn_str, autocommit=True) as tgt_conn:
                    # Safely drop subscriptions
                    try:
                        subs = tgt_conn.execute("SELECT subname FROM pg_subscription").fetchall()
                        for (sub,) in subs:
                            tgt_conn.execute(f'ALTER SUBSCRIPTION "{sub}" DISABLE')
                            tgt_conn.execute(f'ALTER SUBSCRIPTION "{sub}" SET (slot_name = NONE)')
                            tgt_conn.execute(f'DROP SUBSCRIPTION "{sub}"')
                    except Exception as e:
                        logging.warning(f"[DEST] Error dropping subscriptions during pre-cleanup: {e}")
                    
                    # Safely drop replication slots
                    try:
                        slots = tgt_conn.execute("SELECT slot_name, active_pid FROM pg_replication_slots WHERE database = current_database()").fetchall()
                        for slot, pid in slots:
                            if pid:
                                tgt_conn.execute(f"SELECT pg_terminate_backend({pid})")
                            tgt_conn.execute(f"SELECT pg_drop_replication_slot('{slot}')")
                    except Exception as e:
                        logging.warning(f"[DEST] Error dropping replication slots during pre-cleanup: {e}")
            except Exception as e:
                # If DB doesn't exist or is unreachable, the drop will likely pass or fail naturally
                logging.info(f"[DEST] Pre-cleanup skip (DB might not exist or unreachable): {e}")

            # Pre-cleanup source DB: drop the replication slot if it was orphaned
            try:
                src_conn_str = f"host={src_host} port={src_port} user={src_user} dbname={src_db} password={src_pass}"
                with psycopg.connect(src_conn_str, autocommit=True) as src_conn:
                    sub_name = self.replication_cfg.get('subscription_name', 'migrator_sub')
                    try:
                        slots = src_conn.execute("SELECT slot_name, active_pid FROM pg_replication_slots WHERE slot_name = %s", (sub_name,)).fetchall()
                        for slot, pid in slots:
                            if pid:
                                src_conn.execute(f"SELECT pg_terminate_backend({pid})")
                            src_conn.execute(f"SELECT pg_drop_replication_slot('{slot}')")
                            logging.info(f"[SOURCE] Dropped orphaned replication slot '{slot}' on source database.")
                    except Exception as e:
                        logging.warning(f"[SOURCE] Error dropping replication slot on source: {e}")
            except Exception as e:
                logging.warning(f"[SOURCE] Source pre-cleanup skip (DB unreachable): {e}")

            admin_conn_str = f"host={dst_host} port={dst_port} user={dst_user} dbname=postgres password={dst_pass}"
            try:
                with psycopg.connect(admin_conn_str, autocommit=True) as conn:
                    # Attempt DROP DATABASE WITH (FORCE) compatible with PG13+
                    try:
                        conn.execute(f'DROP DATABASE IF EXISTS "{dst_db}" WITH (FORCE);')
                    except Exception:
                        # Fallback for PostgreSQL < 13
                        conn.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{dst_db}' AND pid <> pg_backend_pid();")
                        conn.execute(f'DROP DATABASE IF EXISTS "{dst_db}";')
                        
                    conn.execute(f'CREATE DATABASE "{dst_db}";')
                logging.info(f"[DEST] Successfully dropped and recreated database '{dst_db}'.")
            except Exception as e:
                logging.error(f"[DEST] Failed to drop/recreate DB: {e}")
                return False, f"Failed to drop/recreate destination database: {e}", [], [str(e)]

        target_schema = self.replication_cfg.get('target_schema', 'public')

        dump_cmd = f"PGPASSWORD='{src_pass}' pg_dump -h {src_host} -p {src_port} -U {src_user} -s --schema={target_schema} {src_db}"
        psql_cmd = f"PGPASSWORD='{dst_pass}' psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = f"[SOURCE] pg_dump -h {src_host} -p {src_port} -U {src_user} -s --schema={target_schema} {src_db}"
        psql_cmd_log = f"[DEST] psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"[BOTH] {dump_cmd_log} | {psql_cmd_log}"

        from src.db import execute_shell_command
        # We need executable='/bin/bash' to use set -o pipefail, but we can't easily change db.py right now. 
        # Actually /bin/sh is usually dash or bash. Instead of pipefail, if psql fails we catch it.
        # But wait, psql is the LAST command in the pipe, so its exit code WILL be returned by default even without pipefail!
        success, out = execute_shell_command(cmd, log_cmd=cmd_log)
        if not success:
            err_msg = out.strip() if out else "Unknown error"
            tip = ""
            if "already exists" in err_msg.lower():
                tip = "\n[!] Tip: Destination database is not empty. Consider using --drop-dest to start fresh."
            
            return False, f"Schema migration failed: {err_msg}{tip}", [cmd_log], [err_msg]
        return True, "Schema successfully migrated.", [cmd_log], [out or "Success"]

    def step5_setup_source(self):
        """Step 5: Create Publication and set identity for tables without PK."""
        logging.info("[SOURCE] Setting up publication...")
        pub_name = self.replication_cfg['publication_name']
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        
        query_no_pk = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND NOT EXISTS (
            SELECT 1 FROM pg_index i
            WHERE i.indrelid = c.oid AND i.indisprimary
          );
        """
        
        executed_sqls = []
        out_results = []
        
        try:
            no_pk_tables = source_client.execute_query(query_no_pk)
            for row in no_pk_tables:
                schema = row['schema_name']
                table = row['table_name']
                alt_sql = f'ALTER TABLE "{schema}"."{table}" REPLICA IDENTITY FULL;'
                executed_sqls.append(f"[SOURCE] {alt_sql}")
                source_client.execute_script(alt_sql)
                out_results.append("OK")
                logging.info(f"[SOURCE] Set REPLICA IDENTITY FULL for no-PK table: {schema}.{table}")

            sql1 = f"DROP PUBLICATION IF EXISTS {pub_name};"
            sql2 = f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;"
            
            executed_sqls.append(f"[SOURCE] {sql1}")
            source_client.execute_script(sql1)
            out_results.append("OK")
            
            executed_sqls.append(f"[SOURCE] {sql2}")
            source_client.execute_script(sql2)
            out_results.append("OK")
            
            return True, f"Publication '{pub_name}' created.", executed_sqls, out_results
        except Exception as e:
            logging.error(f"[SOURCE] Source setup failed: {e}")
            while len(out_results) < len(executed_sqls):
                out_results.append(str(e))
            if not executed_sqls:
                executed_sqls.append("INITIALIZATION")
                out_results.append(str(e))
            return False, f"Source setup failed: {str(e)}", executed_sqls, out_results

    def step6_setup_destination(self):
        """Step 6: Create Subscription."""
        logging.info("[DEST] Setting up subscription...")
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']
        
        src_user = self.source_conn['user']
        src_pass = self.source_conn['password']
        src_db = self.source_conn['database']
        
        # In Docker/NAT setups, the target DB might need a different host/port 
        # to reach the source DB than the host machine running pg_migrator.
        rep_config = self.config.get_replication()
        sub_host = rep_config.get('source_host', self.source_conn['host'])
        sub_port = rep_config.get('source_port', self.source_conn['port'])

        conn_str = f"host={sub_host} port={sub_port} user={src_user} password={src_pass} dbname={src_db}"
        
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        sql1 = f"DROP SUBSCRIPTION IF EXISTS {sub_name};"
        sql2 = f"CREATE SUBSCRIPTION {sub_name} CONNECTION '{conn_str}' PUBLICATION {pub_name} WITH (copy_data = true);"
        try:
            dest_client.execute_script(sql1, autocommit=True)
            dest_client.execute_script(sql2, autocommit=True)
            return True, f"Subscription '{sub_name}' created.", [f"[DEST] {sql1}", f"[DEST] {sql2}"], ["OK", "OK"]
        except Exception as e:
            logging.error(f"[DEST] Subscription creation failed: {e}")
            return False, f"Destination setup failed: {str(e)}", [f"[DEST] {sql1}", f"[DEST] {sql2}"], [str(e), str(e)]

    def wait_for_sync(self, timeout=300, poll_interval=2):
        """Wait until all tables in the subscription are synchronized."""
        import time
        logging.info("[DEST] Waiting for initial data sync to complete...")
        
        dst_db = self.dest_conn['database']
        dst_user = self.dest_conn['user']
        dst_host = self.dest_conn['host']
        dst_port = self.dest_conn['port']
        dst_pass = self.dest_conn.get('password', '')
        
        tgt_conn_uri = f"host={dst_host} port={dst_port} user={dst_user} dbname={dst_db} password={dst_pass}"
        client = PostgresClient(tgt_conn_uri, "DEST_WAIT")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            query = "SELECT count(*) AS pending FROM pg_subscription_rel WHERE srsubstate NOT IN ('s', 'r');"
            try:
                result = client.execute_query(query, fetch=True)
                if result is not None and len(result) > 0:
                    pending = result[0]['pending']
                    if pending == 0:
                        return True, "Sync completed. All tables synchronized.", ["[DEST] [POLL pg_subscription_rel]"], ["Sync finished"]
                logging.debug("[DEST] Syncing... Waiting for tables to finish initial copy.")
            except Exception as e:
                logging.warning(f"[DEST] Error checking sync status: {e}")
            
            time.sleep(poll_interval)
            
        return False, f"Sync timed out after {timeout} seconds.", ["[DEST] [POLL pg_subscription_rel]"], ["TIMEOUT"]

    def get_replication_status(self):
        """Step 7: Check replication status for both publisher and subscriber."""
        sub_name = self.config.get_replication()['subscription_name']
        
        # Subscriber status (Destination)
        sub_query = f"SELECT subname, remote_host, last_msg_send_time, last_msg_receipt_time, latest_end_lsn FROM pg_stat_subscription WHERE subname = '{sub_name}';"
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        try:
            sub_status = dest_client.execute_query(sub_query)
        except Exception:
            sub_status = []

        # Publisher status (Source)
        pub_query = "SELECT * FROM pg_stat_replication;"
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        try:
            pub_status = source_client.execute_query(pub_query)
        except Exception:
            pub_status = []

        # Slots information (Source)
        slots_query = "SELECT *, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size FROM pg_replication_slots;"
        try:
            slots_status = source_client.execute_query(slots_query)
        except Exception:
            slots_status = []

        # Full subscription stat (Destination)
        full_sub_query = "SELECT * FROM pg_stat_subscription;"
        try:
            full_sub_status = dest_client.execute_query(full_sub_query)
        except Exception:
            full_sub_status = []

        # Publications info (Source)
        pub_info_query = "SELECT * FROM pg_publication;"
        try:
            pub_info_status = source_client.execute_query(pub_info_query)
        except Exception:
            pub_info_status = []

        # Publication tables info (Source)
        pub_tables_query = "SELECT * FROM pg_publication_tables;"
        try:
            pub_tables_status = source_client.execute_query(pub_tables_query)
        except Exception:
            pub_tables_status = []

        return {
            "publisher": pub_status,
            "subscriber": sub_status,
            "slots": slots_status,
            "full_sub": full_sub_status,
            "publications": pub_info_status,
            "pub_tables": pub_tables_status
        }

    def step12_terminate_replication(self):
        """Step 12: Cleanup publication and subscription."""
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']
        sql1 = f"DROP SUBSCRIPTION IF EXISTS {sub_name};"
        sql2 = f"DROP PUBLICATION IF EXISTS {pub_name};"
        try:
            dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
            source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
            dest_client.execute_script(sql1, autocommit=True)
            source_client.execute_script(sql2, autocommit=True)
            return True, "Replication cleaned up.", [f"[DEST] {sql1}", f"[SOURCE] {sql2}"], ["OK", "OK"]
        except Exception as e:
            return False, f"Cleanup failed: {str(e)}", [f"[DEST] {sql1}", f"[SOURCE] {sql2}"], [str(e)]
