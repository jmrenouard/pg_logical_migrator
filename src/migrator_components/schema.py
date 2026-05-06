import logging
import time
import re
from src import db

class SchemaMigrationMixin:
    def drop_recreate_dest_db(self):
        """Pre-cleanup target database by terminating active logical replication slots,
        subscriptions, and recreating the database."""
        src_db = self.source_conn.get('database', self.config.override_db or 'postgres')
        src_user = self.source_conn.get('user', 'postgres')
        src_host = self.source_conn.get('host', 'localhost')
        src_port = self.source_conn.get('port', '5432')
        src_pass = self.source_conn.get('password', '')

        dst_db = self.dest_conn.get('database', self.config.override_db or 'postgres')
        dst_user = self.dest_conn.get('user', 'postgres')
        dst_host = self.dest_conn.get('host', 'localhost')
        dst_port = self.dest_conn.get('port', '5432')
        dst_pass = self.dest_conn.get('password', '')

        logging.info(f"[DEST] Targeting maintenance database to drop and recreate '{dst_db}'...")

        executed_sqls = []
        out_results = []

        # Pre-cleanup target DB: terminate active logical replication slots
        # and subscriptions
        try:
            tgt_conn_str = f"host={dst_host} port={dst_port} user={dst_user} dbname={dst_db} password={dst_pass}"
            tgt_client = db.PostgresClient(tgt_conn_str)
            with tgt_client.get_conn(autocommit=True) as tgt_conn:
                # Safely drop subscriptions
                try:
                    subs = tgt_conn.execute("SELECT subname FROM pg_subscription").fetchall()
                    for row in subs:
                        sub = row['subname']
                        tgt_conn.execute(f'ALTER SUBSCRIPTION "{sub}" DISABLE')
                        tgt_conn.execute(f'ALTER SUBSCRIPTION "{sub}" SET (slot_name = NONE)')
                        tgt_conn.execute(f'DROP SUBSCRIPTION "{sub}"')
                except Exception as e:
                    logging.warning(f"[DEST] Error dropping subscriptions during pre-cleanup: {e}")

                # Safely drop replication slots
                try:
                    slots = tgt_conn.execute(
                        "SELECT slot_name, active_pid FROM pg_replication_slots "
                        "WHERE database = current_database()").fetchall()
                    for row in slots:
                        slot = row['slot_name']
                        pid = row['active_pid']
                        if pid:
                            tgt_conn.execute(f"SELECT pg_terminate_backend({pid})")
                            time.sleep(1)
                        try:
                            tgt_conn.execute(f"SELECT pg_drop_replication_slot('{slot}')")
                        except Exception as e:
                            logging.warning(f"[DEST] Could not drop slot {slot}: {e}")
                except Exception as e:
                    logging.warning(f"[DEST] Error dropping replication slots during pre-cleanup: {e}")
        except Exception as e:
            # If DB doesn't exist or is unreachable, the drop will likely
            # pass or fail naturally
            logging.info(f"[DEST] Pre-cleanup skip (DB might not exist or unreachable): {e}")

        # Pre-cleanup source DB: drop the replication slot if it was
        # orphaned
        try:
            src_conn_str = f"host={src_host} port={src_port} user={src_user} dbname={src_db} password={src_pass}"
            src_client = db.PostgresClient(src_conn_str)
            with src_client.get_conn(autocommit=True) as src_conn:
                sub_name = self.replication_cfg.get('subscription_name', 'migrator_sub')
                try:
                    slots = src_conn.execute(
                        "SELECT slot_name, active_pid FROM pg_replication_slots WHERE slot_name = %s",
                        (sub_name,)).fetchall()
                    for row in slots:
                        slot = row['slot_name']
                        pid = row['active_pid']
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
            admin_client = db.PostgresClient(admin_conn_str)
            with admin_client.get_conn(autocommit=True) as conn:
                # Attempt DROP DATABASE WITH (FORCE) compatible with PG13+
                try:
                    conn.execute(f'DROP DATABASE IF EXISTS "{dst_db}" WITH (FORCE);')
                except Exception:
                    # Fallback for PostgreSQL < 13
                    conn.execute(
                        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        f"WHERE datname = '{dst_db}' AND pid <> pg_backend_pid();")
                    conn.execute(f'DROP DATABASE IF EXISTS "{dst_db}";')

                conn.execute(f'CREATE DATABASE "{dst_db}";')
            logging.info(f"[DEST] Successfully dropped and recreated database '{dst_db}'.")
            executed_sqls.append(f"DROP DATABASE IF EXISTS {dst_db} & CREATE DATABASE {dst_db}")
            out_results.append("OK")
            return True, f"Successfully dropped and recreated database '{dst_db}'.", executed_sqls, out_results
        except Exception as e:
            logging.error(f"[DEST] Failed to drop/recreate DB: {e}")
            executed_sqls.append(f"DROP DATABASE IF EXISTS {dst_db} & CREATE DATABASE {dst_db}")
            out_results.append(str(e))
            return False, f"Failed to drop/recreate destination database: {e}", executed_sqls, out_results
    def step4a_migrate_schema_pre_data(self, drop_dest=False):
        """Step 4a: Copy schema PRE-DATA using pg_dump -s --section=pre-data | psql (local commands)."""
        logging.info("[BOTH] Starting schema PRE-DATA migration...")
        src_db = self.source_conn.get('database', self.config.override_db or 'postgres')
        src_user = self.source_conn.get('user', 'postgres')
        src_host = self.source_conn.get('host', 'localhost')
        src_port = self.source_conn.get('port', '5432')
        src_pass = self.source_conn.get('password', '')

        dst_db = self.dest_conn.get('database', self.config.override_db or 'postgres')
        dst_user = self.dest_conn.get('user', 'postgres')
        dst_host = self.dest_conn.get('host', 'localhost')
        dst_port = self.dest_conn.get('port', '5432')
        dst_pass = self.dest_conn.get('password', '')

        if drop_dest:
            success, msg, executed, outs = self.drop_recreate_dest_db()
            if not success:
                return success, msg, executed, outs

        source_client = db.PostgresClient(self.config.get_source_conn(), label="SOURCE")
        schemas = db.resolve_target_schemas(source_client, self.config, getattr(self.config, 'override_db', None))
        schema_args = ""
        if schemas != ['all']:
            schema_args = " ".join([f"--schema='{s}'" for s in schemas])

        dump_cmd = (f"pg_dump -h {src_host} -p {src_port} -U {src_user} "
                    f"-s --section=pre-data {schema_args} {src_db}")
        psql_cmd = (f"psql -v ON_ERROR_STOP=0 --echo-all "
                    f"-h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}")
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = (f"[SOURCE] pg_dump -h {src_host} -p {src_port} -U {src_user} "
                        f"-s --section=pre-data {schema_args} {src_db}")
        psql_cmd_log = f"[DEST] psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"[BOTH] {dump_cmd_log} | {psql_cmd_log}"

        with db.pgpass_context(self.source_conn, self.dest_conn):
            success, out = db.execute_shell_command(cmd, log_cmd=cmd_log)
            
        if not success:
            err_msg = out.strip() if out else "Unknown error"
            tip = ""
            if "already exists" in err_msg.lower():
                tip = "\n[!] Tip: Destination database is not empty. Consider using --drop-dest to start fresh."

            return False, f"Schema PRE-DATA migration failed: {err_msg}{tip}", [
                cmd_log], [err_msg]
        return True, "Schema PRE-DATA successfully migrated.", [
            cmd_log], [out or "Success"]
    def step4b_migrate_schema_post_data(self):
        """Step 4b: Copy schema POST-DATA using pg_dump -s --section=post-data | psql (local commands)."""
        logging.info("[BOTH] Starting schema POST-DATA migration...")
        src_db = self.source_conn.get('database', self.config.override_db or 'postgres')
        src_user = self.source_conn.get('user', 'postgres')
        src_host = self.source_conn.get('host', 'localhost')
        src_port = self.source_conn.get('port', '5432')
        src_pass = self.source_conn.get('password', '')

        dst_db = self.dest_conn.get('database', self.config.override_db or 'postgres')
        dst_user = self.dest_conn.get('user', 'postgres')
        dst_host = self.dest_conn.get('host', 'localhost')
        dst_port = self.dest_conn.get('port', '5432')
        dst_pass = self.dest_conn.get('password', '')

        source_client = db.PostgresClient(self.config.get_source_conn(), label="SOURCE")
        schemas = db.resolve_target_schemas(source_client, self.config, getattr(self.config, 'override_db', None))
        schema_args = ""
        if schemas != ['all']:
            schema_args = " ".join([f"--schema='{s}'" for s in schemas])

        dump_cmd = (f"pg_dump -h {src_host} -p {src_port} -U {src_user} "
                    f"-s --section=post-data {schema_args} {src_db}")
        psql_cmd = (f"psql -v ON_ERROR_STOP=0 --echo-all "
                    f"-h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}")
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = (f"[SOURCE] pg_dump -h {src_host} -p {src_port} -U {src_user} "
                        f"-s --section=post-data {schema_args} {src_db}")
        psql_cmd_log = f"[DEST] psql -v ON_ERROR_STOP=0 --echo-all -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"[BOTH] {dump_cmd_log} | {psql_cmd_log}"

        with db.pgpass_context(self.source_conn, self.dest_conn):
            success, out = db.execute_shell_command(cmd, log_cmd=cmd_log)
            
        if not success:
            err_msg = out.strip() if out else "Unknown error"
            return False, f"Schema POST-DATA migration failed: {err_msg}", [
                cmd_log], [err_msg]
        return True, "Schema POST-DATA successfully migrated.", [
            cmd_log], [out or "Success"]
