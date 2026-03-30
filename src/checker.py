import logging
import psycopg
from src.db import PostgresClient

class DBChecker:
    def __init__(self, source_client, dest_client=None):
        self.source = source_client
        self.dest = dest_client

    def check_connectivity(self):
        results = {"source": False, "dest": False}
        try:
            with self.source.get_conn() as conn:
                results["source"] = True
        except Exception as e:
            logging.error(f"[SOURCE] Source Connection Failed: {e}")

        if self.dest:
            try:
                with self.dest.get_conn() as conn:
                    results["dest"] = True
            except Exception as e:
                logging.error(f"[DEST] Destination Connection Failed: {e}")
        return results

    def get_pg_parameters(self, client):
        query = """
        SELECT name, setting, unit, category, pending_restart
        FROM pg_settings
        WHERE name IN (
            'wal_level', 'max_replication_slots', 'max_wal_senders', 
            'max_worker_processes', 'server_version',
            'max_logical_replication_workers', 'max_sync_workers_per_subscription'
        );
        """
        return client.execute_query(query)

    def check_problematic_objects(self):
        # Tables without Primary Keys
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
        no_pk = self.source.execute_query(query_no_pk)

        # Large Objects
        query_lo = "SELECT count(*)::int as count FROM pg_largeobject_metadata;"
        lo_count = self.source.execute_query(query_lo)[0]['count']

        # Tables with Identity Columns
        query_identity = """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE is_identity = 'YES'
          AND table_schema NOT IN ('pg_catalog', 'information_schema');
        """
        identities = self.source.execute_query(query_identity)

        # Sequences WITHOUT parent table
        query_unowned_seq = """
        SELECT n.nspname as schema_name, c.relname as seq_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d 
              WHERE d.objid = c.oid AND d.deptype = 'a'
          );
        """
        unowned_seqs = self.source.execute_query(query_unowned_seq)
        
        # Unlogged tables (relpersistence = 'u')
        query_unlogged = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND c.relpersistence = 'u'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        unlogged_tables = self.source.execute_query(query_unlogged)

        # Temporary tables (relpersistence = 't')
        query_temp = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND c.relpersistence = 't'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        temp_tables = self.source.execute_query(query_temp)

        # Foreign tables (relkind = 'f')
        query_foreign = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'f'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        foreign_tables = self.source.execute_query(query_foreign)

        # Materialized views (relkind = 'm')
        query_matviews = """
        SELECT n.nspname AS schema_name, c.relname AS matview_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        matviews = self.source.execute_query(query_matviews)

        return {
            "no_pk": no_pk,
            "large_objects": lo_count,
            "identities": identities,
            "unowned_seqs": unowned_seqs,
            "unlogged_tables": unlogged_tables,
            "temp_tables": temp_tables,
            "foreign_tables": foreign_tables,
            "matviews": matviews
        }

    def check_replication_params(self, apply_source=False, apply_dest=False):
        """Step 3: Verify parameters on source and destination."""
        results = {"source": [], "dest": []}
        
        reqs = {
            "source": ['server_version', 'wal_level', 'max_replication_slots', 'max_wal_senders', 'max_worker_processes'],
            "dest": ['server_version', 'wal_level', 'max_replication_slots', 'max_logical_replication_workers', 'max_sync_workers_per_subscription', 'max_worker_processes']
        }
        
        apply_flags = {"source": apply_source, "dest": apply_dest}

        for label, client in [("source", self.source), ("dest", self.dest)]:
            if client is None:
                continue
            params = self.get_pg_parameters(client)
            for p in params:
                name = p['name']
                if name not in reqs[label]:
                    continue
                val = p['setting']
                pending_restart = p.get('pending_restart', False)
                status = "PENDING RESTART" if pending_restart else "OK"
                expected = val
                needs_apply = False
                apply_val = None
                
                if name == 'wal_level':
                    expected = "logical"
                    if val != 'logical':
                        if not pending_restart:
                            status = "FAIL"
                        needs_apply = True
                        apply_val = "logical"
                elif name in ('max_replication_slots', 'max_wal_senders', 'max_logical_replication_workers', 'max_sync_workers_per_subscription'):
                    min_val = 10 if name in ('max_replication_slots', 'max_wal_senders') else 4
                    expected = f">= {min_val}"
                    try:
                        int_val = int(val)
                        if int_val < min_val:
                            if not pending_restart:
                                status = "FAIL"
                            needs_apply = True
                            apply_val = str(min_val)
                    except ValueError:
                        if not pending_restart:
                            status = "FAIL"
                        needs_apply = True
                        apply_val = str(min_val)

                # Apply parameter if specified and needed
                if needs_apply and apply_flags[label] and apply_val is not None:
                    try:
                        client.execute_query(f"ALTER SYSTEM SET {name} = '{apply_val}';")
                        status = "PENDING RESTART"
                        logging.info(f"[{label.upper()}] Applied {name} = '{apply_val}' on {label}. Restart required.")
                    except Exception as e:
                        logging.error(f"[{label.upper()}] Failed to apply parameter {name} on {label}: {e}")

                results[label].append({
                    "parameter": name,
                    "actual": val,
                    "expected": expected,
                    "status": status
                })
        return results

    def get_object_counts(self, client):
        query = """
        SELECT
            (SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema') as schemas,
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')) as tables,
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'v' AND n.nspname NOT IN ('pg_catalog', 'information_schema')) as views,
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'm' AND n.nspname NOT IN ('pg_catalog', 'information_schema')) as matviews,
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema')) as sequences,
            (SELECT count(*) FROM pg_trigger) as triggers;
        """
        return client.execute_query(query)
