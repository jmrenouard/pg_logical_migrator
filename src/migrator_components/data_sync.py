import logging
import time
import re
from src import db

class DataSyncMixin:
    def sync_large_objects(self):
        """
        Identify tables with OID columns referring to Large Objects and synchronize them.
        logical replication doesn't support BLOBs/LOBs, so we must manually migrate them
        and update the OID references on the destination.
        """
        logging.info("[BOTH] Starting Large Objects (LOBs) synchronization...")

        executed_sqls = []
        out_results = []

        try:
            source_client = db.PostgresClient(self.config.get_source_conn(), label="SOURCE")

            # Fetch all Large Objects globally from source
            query_all_lobs = "SELECT oid FROM pg_largeobject_metadata;"
            all_lobs = source_client.execute_query(query_all_lobs)

            if not all_lobs:
                logging.info("[BOTH] No Large Objects found in metadata.")
                return True, "No Large Objects to synchronize.", [], []

            total_synced = 0
            batch_size = 100

            src_conn_str = self.config.get_source_conn()
            dst_conn_str = self.config.get_dest_conn()

            s_client = db.PostgresClient(src_conn_str)
            d_client = db.PostgresClient(dst_conn_str)
            
            with s_client.get_conn() as s_conn, d_client.get_conn() as d_conn:
                s_conn.autocommit = False
                d_conn.autocommit = False

                for row in all_lobs:
                    old_oid = row['oid']

                    try:
                        with s_conn.cursor() as s_cur, d_conn.cursor() as d_cur:
                            # 1. Open source LOB (INV_READ)
                            s_cur.execute("SELECT lo_open(%s, %s)", (old_oid, 0x40000))
                            fd_src = list(s_cur.fetchone().values())[0]

                            # 2. Recreate exact same OID on destination
                            d_cur.execute("SAVEPOINT lob_sp")
                            try:
                                d_cur.execute("SELECT lo_create(%s)", (old_oid,))
                            except Exception:
                                d_cur.execute("ROLLBACK TO lob_sp")
                                d_cur.execute("SELECT lo_unlink(%s)", (old_oid,))
                                d_cur.execute("SELECT lo_create(%s)", (old_oid,))
                            d_cur.execute("RELEASE SAVEPOINT lob_sp")

                            # Open dest LOB (INV_WRITE)
                            d_cur.execute("SELECT lo_open(%s, %s)", (old_oid, 0x20000))
                            fd_dst = list(d_cur.fetchone().values())[0]

                            # 3. Stream data from source to dest
                            CHUNK_SIZE = 4 * 1024 * 1024
                            while True:
                                s_cur.execute("SELECT loread(%s, %s)", (fd_src, CHUNK_SIZE))
                                content = list(s_cur.fetchone().values())[0]
                                if not content:
                                    break
                                d_cur.execute("SELECT lowrite(%s, %s)", (fd_dst, content))

                            s_cur.execute("SELECT lo_close(%s)", (fd_src,))
                            d_cur.execute("SELECT lo_close(%s)", (fd_dst,))

                        total_synced += 1
                        if total_synced % batch_size == 0:
                            s_conn.commit()
                            d_conn.commit()
                    except Exception as e:
                        s_conn.rollback()
                        d_conn.rollback()
                        logging.error(f"[BOTH] Failed to sync LOB OID={old_oid}: {e}")
                        out_results.append(f"Error LOB OID={old_oid}: {e}")

                if total_synced % batch_size != 0:
                    s_conn.commit()
                    d_conn.commit()

            out_results.append(f"  - Total Large Objects Synced: {total_synced}")
            executed_sqls.append(f"LOB SYNC: {total_synced} objects processed.")

            msg = f"Large Objects synchronization complete. Processed {total_synced} objects."
            return True, msg, executed_sqls, out_results

        except Exception as e:
            logging.error(f"Large Objects sync failed: {e}", exc_info=True)
            return False, f"LOB sync failed: {str(e)}", executed_sqls, out_results
    def sync_unlogged_tables(self):
        """
        Identify UNLOGGED tables and manually sync their data because 
        logical replication does not copy UNLOGGED tables.
        """
        logging.info("[BOTH] Starting UNLOGGED tables synchronization...")
        executed_sqls = []
        out_results = []
        
        try:
            source_client = db.PostgresClient(
                self.config.get_source_conn(), label="SOURCE")
            
            schemas = db.resolve_target_schemas(source_client, self.config, getattr(self.config, 'override_db', None))
            schema_filter = ""
            if schemas != ['all']:
                schema_list = ", ".join([f"'{s}'" for s in schemas])
                schema_filter = f"AND n.nspname IN ({schema_list})"
                
            query_unlogged = f"""
            SELECT
                n.nspname AS schema_name,
                c.relname AS table_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND c.relpersistence = 'u'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              {schema_filter};
            """
            
            unlogged_tables = source_client.execute_query(query_unlogged)
            if not unlogged_tables:
                logging.info("[BOTH] No UNLOGGED tables found.")
                return True, "No UNLOGGED tables to synchronize.", [], []
                
            total_synced = 0
            
            s_client = db.PostgresClient(self.config.get_source_conn())
            d_client = db.PostgresClient(self.config.get_dest_conn())
            
            with s_client.get_conn() as s_conn, d_client.get_conn() as d_conn:
                for row in unlogged_tables:
                    schema = row['schema_name']
                    table = row['table_name']
                    full_name = f'"{schema}"."{table}"'
                    
                    logging.info(f"[BOTH] Syncing UNLOGGED table: {full_name}...")
                    
                    try:
                        with s_conn.cursor() as s_cur, d_conn.cursor() as d_cur:
                            d_cur.execute(f"TRUNCATE TABLE {full_name};")
                            with s_cur.copy(f"COPY {full_name} TO STDOUT") as copy_out:
                                with d_cur.copy(f"COPY {full_name} FROM STDIN") as copy_in:
                                    for data in copy_out:
                                        copy_in.write(data)
                        s_conn.commit()
                        d_conn.commit()
                        out_results.append(f"  - UNLOGGED Table {schema}.{table}: SUCCESS")
                        total_synced += 1
                        executed_sqls.append(f"SYNC UNLOGGED {full_name}")
                    except Exception as e:
                        logging.error(f"[DEST] Failed to sync UNLOGGED table {full_name}: {e}")
                        s_conn.rollback()
                        d_conn.rollback()
                        raise
                        
            msg = f"Successfully synced {total_synced} UNLOGGED tables."
            logging.info(msg)
            return True, msg, executed_sqls, out_results
            
        except Exception as e:
            msg = f"Failed to sync UNLOGGED tables: {e}"
            logging.error(f"[BOTH] {msg}")
            return False, msg, executed_sqls, out_results
