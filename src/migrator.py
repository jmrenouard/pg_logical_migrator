import logging
import subprocess
from src.db import PostgresClient
import src.db as _db_module

class Migrator:
    def __init__(self, config):
        self.config = config
        self.source_conn = config.get_source_dict()
        self.dest_conn = config.get_dest_dict()
        self.replication_cfg = config.get_replication()

    def step4a_migrate_schema_pre_data(self, drop_dest=False):
        """Step 4a: Copy schema PRE-DATA using pg_dump -s --section=pre-data | psql (local commands)."""
        logging.info("[BOTH] Starting schema PRE-DATA migration...")
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

        schemas = self.config.get_target_schemas()
        schema_args = ""
        if schemas != ['all']:
            schema_args = " ".join([f"--schema='{s}'" for s in schemas])

        dump_cmd = f"PGPASSWORD='{src_pass}' pg_dump -h {src_host} -p {src_port} -U {src_user} -s --section=pre-data {schema_args} {src_db}"
        psql_cmd = f"PGPASSWORD='{dst_pass}' psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = f"[SOURCE] pg_dump -h {src_host} -p {src_port} -U {src_user} -s --section=pre-data {schema_args} {src_db}"
        psql_cmd_log = f"[DEST] psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"[BOTH] {dump_cmd_log} | {psql_cmd_log}"

        from src.db import execute_shell_command
        success, out = execute_shell_command(cmd, log_cmd=cmd_log)
        if not success:
            err_msg = out.strip() if out else "Unknown error"
            tip = ""
            if "already exists" in err_msg.lower():
                tip = "\n[!] Tip: Destination database is not empty. Consider using --drop-dest to start fresh."
            
            return False, f"Schema PRE-DATA migration failed: {err_msg}{tip}", [cmd_log], [err_msg]
        return True, "Schema PRE-DATA successfully migrated.", [cmd_log], [out or "Success"]

    def step4b_migrate_schema_post_data(self):
        """Step 4b: Copy schema POST-DATA using pg_dump -s --section=post-data | psql (local commands)."""
        logging.info("[BOTH] Starting schema POST-DATA migration...")
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

        schemas = self.config.get_target_schemas()
        schema_args = ""
        if schemas != ['all']:
            schema_args = " ".join([f"--schema='{s}'" for s in schemas])

        dump_cmd = f"PGPASSWORD='{src_pass}' pg_dump -h {src_host} -p {src_port} -U {src_user} -s --section=post-data {schema_args} {src_db}"
        psql_cmd = f"PGPASSWORD='{dst_pass}' psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = f"[SOURCE] pg_dump -h {src_host} -p {src_port} -U {src_user} -s --section=post-data {schema_args} {src_db}"
        psql_cmd_log = f"[DEST] psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"[BOTH] {dump_cmd_log} | {psql_cmd_log}"

        from src.db import execute_shell_command
        success, out = execute_shell_command(cmd, log_cmd=cmd_log)
        if not success:
            err_msg = out.strip() if out else "Unknown error"
            return False, f"Schema POST-DATA migration failed: {err_msg}", [cmd_log], [err_msg]
        return True, "Schema POST-DATA successfully migrated.", [cmd_log], [out or "Success"]

    def step5_setup_source(self):
        """Step 5: Create Publication and set identity for tables without PK."""
        logging.info("[SOURCE] Setting up publication...")
        pub_name = self.replication_cfg['publication_name']
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        
        schemas = self.config.get_target_schemas()
        schema_filter = ""
        if schemas != ['all']:
            schema_list = ", ".join([f"'{s}'" for s in schemas])
            schema_filter = f"AND n.nspname IN ({schema_list})"

        query_no_pk = f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {schema_filter}
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
            
            schemas = self.config.get_target_schemas()
            if schemas == ['all']:
                sql2 = f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;"
            else:
                schema_list = ", ".join(schemas)
                sql2 = f"CREATE PUBLICATION {pub_name} FOR TABLES IN SCHEMA {schema_list};"
            
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

    def wait_for_sync(self, timeout=60, poll_interval=5, show_progress=False):
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
                        if show_progress:
                            print(f"\n  [OK] All tables synchronized.")
                        return True, "Sync completed. All tables synchronized.", ["[DEST] [POLL pg_subscription_rel]"], ["Sync finished"]
                    
                    if show_progress:
                        elapsed = int(time.time() - start_time)
                        # Try to get byte progress if possible
                        progress = self.get_initial_copy_progress()
                        pct = progress['summary']['percent_bytes'] if progress else 0
                        print(f"\r  [wait] Syncing... {pending} tables remaining ({pct}% bytes) - {elapsed}s elapsed", end="", flush=True)

                logging.debug("[DEST] Syncing... Waiting for tables to finish initial copy.")
            except Exception as e:
                logging.warning(f"[DEST] Error checking sync status: {e}")
            
            time.sleep(poll_interval)
            
        if show_progress: print("\n")
        return False, f"Sync timed out after {timeout} seconds.", ["[DEST] [POLL pg_subscription_rel]"], ["TIMEOUT"]

    def get_initial_copy_progress(self):
        """Fetch progress of initial data copy based on table count AND total size."""
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']
        
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        
        # 1. Get all tables in publication and their sizes on SOURCE
        pub_tables_query = f"""
        SELECT 
            schemaname, 
            tablename, 
            pg_total_relation_size('"' || schemaname || '"."' || tablename || '"') AS total_bytes
        FROM pg_publication_tables 
        WHERE pubname = '{pub_name}';
        """
        try:
            source_tables = source_client.execute_query(pub_tables_query) or []
        except Exception as e:
            logging.error(f"Failed to fetch publication tables from source: {e}")
            return None

        source_size_map = {f"{r['schemaname']}.{r['tablename']}": r['total_bytes'] for r in source_tables}
        total_source_bytes = sum(source_size_map.values())

        # 2. Get states from DESTINATION (fully qualified names)
        rel_query = """
        SELECT 
            n.nspname || '.' || c.relname AS table_name, 
            srsubstate AS state
        FROM pg_subscription_rel sr
        JOIN pg_class c ON sr.srrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid;
        """
        
        # 3. Real-time COPY progress
        progress_query = """
        SELECT 
            n.nspname || '.' || c.relname AS table_name, 
            bytes_processed, 
            bytes_total 
        FROM pg_stat_progress_copy p
        JOIN pg_class c ON p.relid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid;
        """
        
        try:
            rel_status = dest_client.execute_query(rel_query) or []
            progress_status = dest_client.execute_query(progress_query) or []
            active_copy_map = {str(r['table_name']): r for r in progress_status}
            
            bytes_copied = 0
            completed_tables = 0
            
            detailed_tables = []
            for r in rel_status:
                t_name = str(r['table_name'])
                state = r['state']
                src_size = source_size_map.get(t_name, 0)
                
                t_bytes_copied = 0
                if state in ('r', 's'):
                    t_bytes_copied = src_size
                    completed_tables += 1
                elif state == 'd':
                    # Currently copying
                    if t_name in active_copy_map:
                        t_bytes_copied = active_copy_map[t_name]['bytes_processed']
                    else:
                        t_bytes_copied = 0
                
                bytes_copied += t_bytes_copied
                
                detailed_tables.append({
                    "table_name": t_name,
                    "state": state,
                    "size_source": src_size,
                    "bytes_copied": t_bytes_copied,
                    "percent": round(100.0 * t_bytes_copied / src_size, 2) if src_size > 0 else (100.0 if state in ('r','s') else 0)
                })

            # Sort by size descending
            detailed_tables.sort(key=lambda x: x['size_source'], reverse=True)

            return {
                "tables": detailed_tables,
                "summary": {
                    "total_tables": len(source_tables),
                    "completed_tables": completed_tables,
                    "total_source_bytes": total_source_bytes,
                    "total_source_pretty": _db_module.pretty_size(total_source_bytes),
                    "bytes_copied": bytes_copied,
                    "bytes_copied_pretty": _db_module.pretty_size(bytes_copied),
                    "percent_tables": round(100.0 * completed_tables / len(source_tables), 2) if source_tables else 0,
                    "percent_bytes": round(100.0 * bytes_copied / total_source_bytes, 2) if total_source_bytes > 0 else 0
                }
            }
        except Exception as e:
            logging.error(f"Failed to fetch replication progress: {e}")
            return None

    def get_replication_status(self):
        """Step 7: Check replication status for both publisher and subscriber on BOTH instances."""
        sub_name = self.config.get_replication()['subscription_name']
        rev_sub_name = sub_name + "_rev"
        
        # 1. Subscriber status (Both sides)
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        
        sub_status = []
        try:
            # Check standard sub on DEST
            sub_status += dest_client.execute_query(f"SELECT 'DEST' as side, * FROM pg_stat_subscription WHERE subname = '{sub_name}';")
            # Check reverse sub on SOURCE
            sub_status += source_client.execute_query(f"SELECT 'SOURCE' as side, * FROM pg_stat_subscription WHERE subname = '{rev_sub_name}';")
        except Exception: pass

        # 2. Publisher status (Both sides)
        pub_status = []
        try:
            pub_status += source_client.execute_query("SELECT 'SOURCE' as side, * FROM pg_stat_replication;")
            pub_status += dest_client.execute_query("SELECT 'DEST' as side, * FROM pg_stat_replication;")
        except Exception: pass

        # 3. Slots information (Both sides)
        slots_status = []
        try:
            slots_status += source_client.execute_query("SELECT 'SOURCE' as side, *, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size FROM pg_replication_slots;")
            slots_status += dest_client.execute_query("SELECT 'DEST' as side, *, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size FROM pg_replication_slots;")
        except Exception: pass

        # 4. Publications info (Both sides)
        pub_info_status = []
        try:
            pub_info_status += source_client.execute_query("SELECT 'SOURCE' as side, * FROM pg_publication;")
            pub_info_status += dest_client.execute_query("SELECT 'DEST' as side, * FROM pg_publication;")
        except Exception: pass

        return {
            "publisher": pub_status,
            "subscriber": sub_status,
            "slots": slots_status,
            "publications": pub_info_status
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

    def setup_reverse_replication(self):
        """
        Reverse the replication flow: Destination becomes Publisher, Source becomes Subscriber.
        Used for rapid rollback after a successful migration.
        """
        logging.info("[BOTH] Setting up REVERSE replication (Rollback capability)...")

        fwd_sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name'] + "_rev"
        sub_name = self.replication_cfg['subscription_name'] + "_rev"

        src_conn = self.source_conn
        dst_conn = self.dest_conn

        # Preparation of SQLs
        sql_pub1 = f"DROP PUBLICATION IF EXISTS {pub_name};"
        sql_pub2 = f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;"

        rep_config = self.config.get_replication()
        dst_host_for_src = rep_config.get('dest_host_for_src', dst_conn['host'])
        dst_port_for_src = rep_config.get('dest_port_for_src', dst_conn['port'])
        conn_str = f"host={dst_host_for_src} port={dst_port_for_src} user={dst_conn['user']} password={dst_conn['password']} dbname={dst_conn['database']}"

        sql_sub1 = f"DROP SUBSCRIPTION IF EXISTS {sub_name};"
        sql_sub2 = f"CREATE SUBSCRIPTION {sub_name} CONNECTION '{conn_str}' PUBLICATION {pub_name} WITH (copy_data = false, create_slot = true);"

        executed_sqls = []
        out_results = []

        try:
            dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
            source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")

            # BLOCK: Check if forward subscription still exists on DESTINATION
            check_sql = f"SELECT count(*) FROM pg_subscription WHERE subname = '{fwd_sub_name}';"
            res = dest_client.execute_query(check_sql)
            if res and res[0]['count'] > 0:
                msg = f"Forward replication subscription '{fwd_sub_name}' still exists on destination. Please run 'cleanup' first to terminate forward replication before setting up reverse replication."
                logging.error(msg)
                return False, msg, [f"[DEST] {check_sql}"], ["Exists"]

            # Exec on SOURCE: drop sub (this might fail if slot is missing, so we wrap it)
            try:
                source_client.execute_script(sql_sub1, autocommit=True)
            except Exception: pass

            # Exec on DEST: ensure slot is gone
            drop_slot_sql = f"SELECT pg_drop_replication_slot('{sub_name}') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '{sub_name}');"
            dest_client.execute_script(drop_slot_sql, autocommit=True)

            # Exec on DEST: Pub
            executed_sqls.append(f"[DEST] {sql_pub1}")
            dest_client.execute_script(sql_pub1, autocommit=True)
            out_results.append("OK")

            executed_sqls.append(f"[DEST] {sql_pub2}")
            dest_client.execute_script(sql_pub2, autocommit=True)
            out_results.append("OK")

            # Exec on SOURCE: Sub
            executed_sqls.append(f"[SOURCE] {sql_sub1}")
            out_results.append("OK")

            executed_sqls.append(f"[SOURCE] {sql_sub2}")
            source_client.execute_script(sql_sub2, autocommit=True)
            out_results.append("OK")

            return True, "Reverse replication setup successfully.", executed_sqls, out_results

        except Exception as e:
            logging.error(f"Reverse replication setup failed: {e}")
            return False, f"Reverse setup failed: {str(e)}", executed_sqls, [str(e)] * (len(executed_sqls) or 1)
