import logging
import time
import re
from src import db

class MonitoringMixin:
    def wait_for_sync(self, timeout=60, poll_interval=5, show_progress=False):
        """Wait until all tables in the subscription are synchronized."""
        if show_progress:
            print("\n")
        logging.info("[DEST] Waiting for initial data sync to complete...")

        dst_db = self.dest_conn.get('database', self.config.override_db or 'postgres')
        dst_user = self.dest_conn.get('user', 'postgres')
        dst_host = self.dest_conn.get('host', 'localhost')
        dst_port = self.dest_conn.get('port', '5432')
        dst_pass = self.dest_conn.get('password', '')

        tgt_conn_uri = f"host={dst_host} port={dst_port} user={dst_user} dbname={dst_db} password={dst_pass}"
        client = db.PostgresClient(tgt_conn_uri, "DEST_WAIT")

        sub_name = self.replication_cfg['subscription_name']
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            query = """
            SELECT count(*) AS total, 
                   COALESCE(SUM(CASE WHEN srsubstate NOT IN ('s', 'r') THEN 1 ELSE 0 END), 0) AS pending 
            FROM pg_subscription_rel;
            """
            try:
                # Check if subscription exists
                sub_exists_query = "SELECT count(*) AS cnt FROM pg_subscription WHERE subname = %s"
                sub_res = client.execute_query(sub_exists_query, (sub_name,))
                if not sub_res or sub_res[0].get('cnt', 0) == 0:
                    elapsed = int(time.time() - start_time)
                    msg = f"Subscription '{sub_name}' not yet visible..."
                    if show_progress:
                        print(f"\r  [wait] {msg} waiting ({elapsed}s)          ", end="", flush=True)
                    logging.debug(f"[DEST] {msg}")
                    time.sleep(poll_interval)
                    continue

                result = client.execute_query(query, fetch=True)
                if result is not None and len(result) > 0:
                    total = result[0]['total']
                    pending = result[0]['pending']
                    
                    if total > 0 and pending == 0:
                        if show_progress:
                            print("\r  [OK] All tables synchronized.                                        ")
                        return True, "Sync completed. All tables synchronized.", [
                            "[DEST] [POLL pg_subscription_rel]"], ["Sync finished"]
                    elif total == 0:
                        if show_progress:
                            elapsed = int(time.time() - start_time)
                            print(f"\r  [wait] Subscription initializing ({elapsed}s)... waiting for metadata", end="", flush=True)
                        logging.debug("[DEST] No tables found in pg_subscription_rel yet.")
                    else:
                        if show_progress:
                            elapsed = int(time.time() - start_time)
                            # Try to get byte progress if possible
                            progress = self.get_initial_copy_progress()
                            if progress:
                                pct = progress['summary']['percent_bytes']
                                copied = progress['summary']['bytes_copied_pretty']
                                total_size = progress['summary']['total_source_pretty']
                                print(
                                    f"\r  [sync] {pct:>5}% | {copied:>10} / {total_size:<10} | {pending:>3} tables left | {elapsed:>4}s",
                                    end="",
                                    flush=True)
                            else:
                                print(
                                    f"\r  [sync] {pending:>3} tables remaining... | {elapsed:>4}s elapsed",
                                    end="",
                                    flush=True)

                logging.debug(
                    "[DEST] Syncing... Waiting for tables to finish initial copy.")
            except Exception as e:
                logging.warning(f"[DEST] Error checking sync status: {e}")

            time.sleep(poll_interval)

        if show_progress:
            print("\n")
        return False, f"Sync timed out after {timeout} seconds.", [
            "[DEST] [POLL pg_subscription_rel]"], ["TIMEOUT"]
    def get_initial_copy_progress(self):
        """Fetch progress of initial data copy based on table count AND total size."""
        # NOTE: subscription_name is not used in this method — only pub_name is needed
        pub_name = self.replication_cfg['publication_name']

        source_client = db.PostgresClient(
            self.config.get_source_conn(), label="SOURCE")
        dest_client = db.PostgresClient(
            self.config.get_dest_conn(),
            label="DESTINATION")

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
            logging.error(
                f"Failed to fetch publication tables from source: {e}")
            return None

        source_size_map = {
            f"{r['schemaname']}.{r['tablename']}": r['total_bytes'] for r in source_tables}
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
                    "percent": round(100.0 * t_bytes_copied / src_size, 2) if src_size > 0 else (
                        100.0 if state in ('r', 's') else 0
                    )
                })

            # Sort by size descending
            detailed_tables.sort(key=lambda x: x['size_source'], reverse=True)

            return {
                "tables": detailed_tables,
                "summary": {
                    "total_tables": len(source_tables),
                    "completed_tables": completed_tables,
                    "total_source_bytes": total_source_bytes,
                    "total_source_pretty": db.pretty_size(total_source_bytes),
                    "bytes_copied": bytes_copied,
                    "bytes_copied_pretty": db.pretty_size(bytes_copied),
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
        dest_client = db.PostgresClient(
            self.config.get_dest_conn(),
            label="DESTINATION")
        source_client = db.PostgresClient(
            self.config.get_source_conn(), label="SOURCE")

        sub_status = []
        try:
            # Check standard sub on DEST
            sub_status += dest_client.execute_query(
                f"SELECT 'DEST' as side, * FROM pg_stat_subscription WHERE subname = '{sub_name}';")
            # Check reverse sub on SOURCE
            sub_status += source_client.execute_query(
                f"SELECT 'SOURCE' as side, * FROM pg_stat_subscription WHERE subname = '{rev_sub_name}';")
        except Exception:
            pass

        # 2. Publisher status (Both sides)
        pub_status = []
        try:
            pub_status += source_client.execute_query(
                "SELECT 'SOURCE' as side, * FROM pg_stat_replication;")
            pub_status += dest_client.execute_query(
                "SELECT 'DEST' as side, * FROM pg_stat_replication;")
        except Exception:
            pass

        # 3. Slots information (Both sides)
        slots_status = []
        try:
            slots_status += source_client.execute_query(
                "SELECT 'SOURCE' as side, *, "
                "pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size "
                "FROM pg_replication_slots;")
            slots_status += dest_client.execute_query(
                "SELECT 'DEST' as side, *, "
                "pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size "
                "FROM pg_replication_slots;")
        except Exception:
            pass

        # 4. Publications info (Both sides)
        pub_info_status = []
        try:
            pub_info_status += source_client.execute_query(
                "SELECT 'SOURCE' as side, * FROM pg_publication;")
            pub_info_status += dest_client.execute_query(
                "SELECT 'DEST' as side, * FROM pg_publication;")
        except Exception:
            pass

        return {
            "publisher": pub_status,
            "subscriber": sub_status,
            "slots": slots_status,
            "publications": pub_info_status
        }
