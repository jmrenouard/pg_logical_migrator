import logging
import subprocess
from src.db import PostgresClient

class Migrator:
    def __init__(self, config):
        self.config = config
        self.source_conn = config.get_source_dict()
        self.dest_conn = config.get_dest_dict()
        self.replication_cfg = config.get_replication()

    def step4_migrate_schema(self):
        """Step 4: Copy schema using pg_dump -s | psql (local commands)."""
        logging.info("Starting schema migration...")
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

        dump_cmd = f"PGPASSWORD='{src_pass}' pg_dump -h {src_host} -p {src_port} -U {src_user} -s {src_db}"
        psql_cmd = f"PGPASSWORD='{dst_pass}' psql -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd = f"{dump_cmd} | {psql_cmd}"

        # Sanitised version for logs (no passwords)
        dump_cmd_log = f"pg_dump -h {src_host} -p {src_port} -U {src_user} -s {src_db}"
        psql_cmd_log = f"psql -h {dst_host} -p {dst_port} -U {dst_user} -d {dst_db}"
        cmd_log = f"{dump_cmd_log} | {psql_cmd_log}"

        from src.db import execute_shell_command
        success, out = execute_shell_command(cmd, log_cmd=cmd_log)
        if not success:
            return False, f"Schema migration failed: {out.strip()}", [cmd_log], [out]
        return True, "Schema successfully migrated.", [cmd_log], [out or "Success"]

    def step5_setup_source(self):
        """Step 5: Create Publication."""
        logging.info("Setting up publication...")
        pub_name = self.replication_cfg['publication_name']
        source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        sql1 = f"DROP PUBLICATION IF EXISTS {pub_name};"
        sql2 = f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;"
        try:
            source_client.execute_script(sql1)
            source_client.execute_script(sql2)
            return True, f"Publication '{pub_name}' created.", [sql1, sql2], ["OK", "OK"]
        except Exception as e:
            logging.error(f"Publication creation failed: {e}")
            return False, f"Source setup failed: {str(e)}", [sql1, sql2], [str(e), str(e)]

    def step6_setup_destination(self):
        """Step 6: Create Subscription."""
        logging.info("Setting up subscription...")
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']
        
        src_user = self.source_conn['user']
        src_pass = self.source_conn['password']
        src_db = self.source_conn['database']
        src_host = self.source_conn['host']
        src_port = self.source_conn['port']

        conn_str = f"host={src_host} port={src_port} user={src_user} password={src_pass} dbname={src_db}"
        
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        sql1 = f"DROP SUBSCRIPTION IF EXISTS {sub_name};"
        sql2 = f"CREATE SUBSCRIPTION {sub_name} CONNECTION '{conn_str}' PUBLICATION {pub_name} WITH (copy_data = true);"
        try:
            dest_client.execute_script(sql1, autocommit=True)
            dest_client.execute_script(sql2, autocommit=True)
            return True, f"Subscription '{sub_name}' created.", [sql1, sql2], ["OK", "OK"]
        except Exception as e:
            logging.error(f"Subscription creation failed: {e}")
            return False, f"Destination setup failed: {str(e)}", [sql1, sql2], [str(e), str(e)]

    def get_replication_status(self):
        """Step 7: Check replication status."""
        sub_name = self.config.get_replication()['subscription_name']
        query = f"SELECT subname, remote_host, last_msg_send_time, last_msg_receipt_time, latest_end_lsn FROM pg_stat_subscription WHERE subname = '{sub_name}';"
        dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        try:
            return dest_client.execute_query(query)
        except Exception:
            return []

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
            return True, "Replication cleaned up.", [sql1, sql2], ["OK", "OK"]
        except Exception as e:
            return False, f"Cleanup failed: {str(e)}", [sql1, sql2], [str(e)]
