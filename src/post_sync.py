import logging
from src.db import PostgresClient

class PostSync:
    def __init__(self, source_client, dest_client):
        self.source = source_client
        self.dest = dest_client

    def refresh_materialized_views(self):
        logging.info("Refreshing materialized views on destination...")
        query = """
        SELECT n.nspname AS schema_name, c.relname AS matview_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        cmds = []
        outs = []
        try:
            matviews = self.dest.execute_query(query) or []
            for row in matviews:
                schema = row['schema_name']
                name = row['matview_name']
                sql = f'REFRESH MATERIALIZED VIEW "{schema}"."{name}";'
                cmds.append(sql)
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Processed {len(cmds)} materialized views", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def sync_sequences(self):
        logging.info("Synchronizing sequences...")
        query = """
        SELECT n.nspname AS schema_name, c.relname AS seq_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        cmds = []
        outs = []
        try:
            seqs = self.source.execute_query(query) or []
            for row in seqs:
                schema = row['schema_name']
                name = row['seq_name']
                try:
                    res = self.source.execute_query(f'SELECT last_value, is_called FROM "{schema}"."{name}"')
                    if res:
                        last_val = res[0]['last_value']
                        is_called = res[0]['is_called']
                        sql = f'SELECT setval(\'"{schema}"."{name}"\', {last_val}, {str(is_called).lower()});'
                        cmds.append(sql)
                        self.dest.execute_script(sql)
                        outs.append(f"Synced to {last_val}")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Synced {len(cmds)} sequences", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def activate_sequences(self):
        return True, "No activation logic needed", [], []

    def enable_triggers(self):
        logging.info("Enabling all triggers on destination...")
        query = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        cmds = []
        outs = []
        try:
            tables = self.dest.execute_query(query) or []
            for row in tables:
                schema = row['schema_name']
                name = row['table_name']
                sql = f'ALTER TABLE "{schema}"."{name}" ENABLE TRIGGER ALL;'
                cmds.append(sql)
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Enabled triggers on {len(cmds)} tables", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def disable_triggers(self):
        logging.info("Disabling all triggers on destination...")
        query = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        cmds = []
        outs = []
        try:
            tables = self.dest.execute_query(query) or []
            for row in tables:
                schema = row['schema_name']
                name = row['table_name']
                sql = f'ALTER TABLE "{schema}"."{name}" DISABLE TRIGGER ALL;'
                cmds.append(sql)
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Disabled triggers on {len(cmds)} tables", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]
