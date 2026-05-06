import logging
import time
import re
from src import db

class CoreReplicationMixin:
    def step5_setup_source(self):
        """Step 5: Create Publication and set identity for tables without PK."""
        logging.info("[SOURCE] Setting up publication...")
        pub_name = self.replication_cfg['publication_name']
        source_client = db.PostgresClient(
            self.config.get_source_conn(), label="SOURCE")

        schemas = db.resolve_target_schemas(source_client, self.config, getattr(self.config, 'override_db', None))
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
                logging.info(
                    f"[SOURCE] Set REPLICA IDENTITY FULL for no-PK table: {schema}.{table}")

            sql1 = f"DROP PUBLICATION IF EXISTS {pub_name};"

            schemas = db.resolve_target_schemas(source_client, self.config, getattr(self.config, 'override_db', None))
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
    def _resolve_source_host(self, configured_host: str, configured_port: str) -> tuple:
        """Return (host, port) reachable from inside the DEST container.

        When the configured source host is a loopback address the subscription
        connection string would point to 'localhost' which, inside the DEST
        container, resolves to the DEST itself — not the SOURCE.  We query
        ``inet_server_addr()`` on the SOURCE to get its Docker bridge IP.

        Priority:
        1. Explicit ``source_host`` / ``source_port`` in [replication] config.
        2. Auto-detected Docker bridge IP via ``inet_server_addr()`` on SOURCE.
        3. Original configured host (works for non-Docker / bare-metal setups).
        """
        rep_config = self.config.get_replication()
        if rep_config.get('source_host'):
            return rep_config['source_host'], rep_config.get('source_port', configured_port)

        is_loopback = configured_host in ('localhost', '127.0.0.1', '::1', '')
        if is_loopback:
            try:
                source_client = db.PostgresClient(self.config.get_source_conn(), label="SOURCE")
                res = source_client.execute_query("SELECT inet_server_addr()::text AS ip")
                if res and res[0].get('ip'):
                    docker_ip = res[0]['ip'].split('/')[0]
                    logging.info(
                        f"[SOURCE] Auto-detected Docker/container IP: {docker_ip} "
                        f"(configured '{configured_host}' is loopback — using container IP)"
                    )
                    return docker_ip, '5432'
            except Exception as exc:
                logging.warning(f"[SOURCE] Could not auto-detect container IP: {exc}")

        return configured_host, configured_port
    def step6_setup_destination(self):
        """Step 6: Create Subscription (non-blocking).

        Strategy:
        1. Safe DROP of any existing subscription (disable→detach slot→drop).
        2. Drop orphaned slot on SOURCE if present.
        3. Create the replication slot on SOURCE manually (instant psycopg call).
        4. CREATE SUBSCRIPTION with ``create_slot = false, copy_data = true``.
           PostgreSQL registers the tables in pg_subscription_rel and starts
           background tablesync workers immediately.  The command returns in
           milliseconds because the slot already exists.
        """
        logging.info("[DEST] Setting up subscription...")
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']

        src_user = self.source_conn.get('user', 'postgres')
        src_pass = self.source_conn.get('password', '')
        src_db = self.source_conn.get('database', self.config.override_db or 'postgres')

        configured_host = self.source_conn.get('host', 'localhost')
        configured_port = self.source_conn.get('port', '5432')
        sub_host, sub_port = self._resolve_source_host(configured_host, configured_port)

        conn_str = (f"host={sub_host} port={sub_port} user={src_user} "
                    f"password={src_pass} dbname={src_db}")
        logging.info(f"[DEST] Subscription connection: {sub_host}:{sub_port}/{src_db}")

        dest_client = db.PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        source_client = db.PostgresClient(self.config.get_source_conn(), label="SOURCE")

        # ── Phase 1: Safe non-blocking DROP of existing subscription on DEST ──
        sql_drop_sub = f"""\
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_subscription WHERE subname = '{sub_name}') THEN
        ALTER SUBSCRIPTION {sub_name} DISABLE;
        ALTER SUBSCRIPTION {sub_name} SET (slot_name = NONE);
        DROP SUBSCRIPTION {sub_name};
    END IF;
END
$$;"""

        # ── Phase 2: Drop orphaned slot on SOURCE (if any) ──
        sql_drop_slot = (
            f"SELECT pg_drop_replication_slot(slot_name) "
            f"FROM pg_replication_slots WHERE slot_name = '{sub_name}';"
        )

        # ── Phase 3: Create slot on SOURCE manually (pgoutput plugin, instant) ──
        sql_create_slot = (
            f"SELECT pg_create_logical_replication_slot('{sub_name}', 'pgoutput');"
        )

        # ── Phase 4: CREATE SUBSCRIPTION — slot exists, so this returns fast ──
        # copy_data=true → PG registers all tables in pg_subscription_rel and
        # starts background tablesync workers immediately.
        sql_create_sub = (
            f"CREATE SUBSCRIPTION {sub_name} "
            f"CONNECTION '{conn_str}' "
            f"PUBLICATION {pub_name} "
            f"WITH (create_slot = false, copy_data = true);"
        )

        executed_sqls = [
            f"[DEST] DROP subscription (safe)",
            f"[SOURCE] DROP orphan slot",
            f"[SOURCE] CREATE slot '{sub_name}'",
            f"[DEST] CREATE SUBSCRIPTION (create_slot=false, copy_data=true)",
        ]
        out_results = []
        try:
            dest_client.execute_script(sql_drop_sub, autocommit=True)
            out_results.append("OK")
            logging.info(f"[DEST] Existing subscription '{sub_name}' safely dropped (if any).")

            try:
                source_client.execute_script(sql_drop_slot, autocommit=True)
            except Exception:
                pass  # Slot may not exist — fine
            out_results.append("OK")
            logging.info(f"[SOURCE] Orphaned slot '{sub_name}' dropped (if any).")

            source_client.execute_script(sql_create_slot, autocommit=True)
            out_results.append("OK")
            logging.info(f"[SOURCE] Replication slot '{sub_name}' created.")

            dest_client.execute_script(sql_create_sub, autocommit=True)
            out_results.append("OK")
            logging.info(
                f"[DEST] Subscription '{sub_name}' created — "
                f"initial COPY started in PostgreSQL background workers."
            )

            return True, (
                f"Subscription '{sub_name}' created. "
                f"Initial data copy is running in PostgreSQL background workers. "
                f"Use 'progress' (step 7 / U1) to monitor."
            ), executed_sqls, out_results

        except Exception as e:
            logging.error(f"[DEST] Subscription creation failed: {e}")
            out_results.append(str(e))
            return False, f"Destination setup failed: {str(e)}", executed_sqls, out_results
    def step10_terminate_replication(self):
        """Step 10: Cleanup publication and subscription."""
        sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name']

        # Robust subscription drop
        sql1 = f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_subscription WHERE subname = '{sub_name}') THEN
                ALTER SUBSCRIPTION {sub_name} DISABLE;
                ALTER SUBSCRIPTION {sub_name} SET (slot_name = NONE);
                DROP SUBSCRIPTION {sub_name};
            END IF;
        END
        $$;
        """
        sql2 = f"DROP PUBLICATION IF EXISTS {pub_name};"
        sql3 = (f"SELECT pg_drop_replication_slot('{sub_name}') WHERE EXISTS "
                f"(SELECT 1 FROM pg_replication_slots WHERE slot_name = '{sub_name}');")

        try:
            dest_client = db.PostgresClient(
                self.config.get_dest_conn(), label="DESTINATION")
            source_client = db.PostgresClient(
                self.config.get_source_conn(), label="SOURCE")

            dest_client.execute_script(sql1, autocommit=True)
            source_client.execute_script(sql3, autocommit=True)
            source_client.execute_script(sql2, autocommit=True)

            return True, "Replication cleaned up.", [
                f"[DEST] {sql1}", f"[SOURCE] {sql3}", f"[SOURCE] {sql2}"], [
                f"  - Subscription {sub_name}: DISABLED AND DROPPED",
                f"  - Replication slot {sub_name}: DROPPED",
                f"  - Publication {pub_name}: DROPPED"
            ]
        except Exception as e:
            return False, f"Cleanup failed: {str(e)}", [
                f"[DEST] {sql1}", f"[SOURCE] {sql3}", f"[SOURCE] {sql2}"], [str(e), str(e), str(e)]
    def setup_reverse_replication(self):
        """
        Reverse the replication flow: Destination becomes Publisher, Source becomes Subscriber.
        Used for rapid rollback after a successful migration.
        """
        logging.info(
            "[BOTH] Setting up REVERSE replication (Rollback capability)...")

        fwd_sub_name = self.replication_cfg['subscription_name']
        pub_name = self.replication_cfg['publication_name'] + "_rev"
        sub_name = self.replication_cfg['subscription_name'] + "_rev"

        dst_conn = self.dest_conn

        # Preparation of SQLs
        sql_pub1 = f"DROP PUBLICATION IF EXISTS {pub_name};"
        sql_pub2 = f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;"

        rep_config = self.config.get_replication()
        dst_host_for_src = rep_config.get(
            'dest_host', dst_conn['host'])
        dst_port_for_src = rep_config.get(
            'dest_port', dst_conn['port'])
        dst_user = dst_conn['user']
        dst_password = dst_conn['password']
        dst_database = dst_conn['database']
        conn_str = (f"host={dst_host_for_src} port={dst_port_for_src}"
                    f" user={dst_user} password={dst_password} dbname={dst_database}")

        sql_sub1 = f"DROP SUBSCRIPTION IF EXISTS {sub_name};"
        sql_sub2 = (f"CREATE SUBSCRIPTION {sub_name} CONNECTION '{conn_str}' "
                    f"PUBLICATION {pub_name} WITH (copy_data = false, create_slot = true);")

        executed_sqls = []
        out_results = []

        try:
            dest_client = db.PostgresClient(
                self.config.get_dest_conn(), label="DESTINATION")
            source_client = db.PostgresClient(
                self.config.get_source_conn(), label="SOURCE")

            # BLOCK: Check if forward subscription still exists on DESTINATION
            check_sql = "SELECT count(*) FROM pg_subscription WHERE subname = %s;"
            res = dest_client.execute_query(check_sql, (fwd_sub_name,))
            if res and res[0]['count'] > 0:
                msg = (f"Forward replication subscription '{fwd_sub_name}' still exists on "
                       "destination. Please run 'cleanup' first to terminate forward replication "
                       "before setting up reverse replication.")
                logging.error(msg)
                return False, msg, [
                    f"[DEST] {check_sql} | params={fwd_sub_name!r}"], ["Exists"]

            # Exec on SOURCE: drop sub (this might fail if slot is missing, so
            # we wrap it)
            try:
                source_client.execute_script(sql_sub1, autocommit=True)
            except Exception:
                pass

            # Exec on DEST: ensure slot is gone
            drop_slot_sql = (f"SELECT pg_drop_replication_slot('{sub_name}') WHERE EXISTS "
                             f"(SELECT 1 FROM pg_replication_slots WHERE slot_name = '{sub_name}');")
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
            while len(out_results) < len(executed_sqls):
                out_results.append(str(e))
            if not executed_sqls:
                executed_sqls.append("INITIALIZATION")
                out_results.append(str(e))
            return False, f"Reverse setup failed: {str(e)}", executed_sqls, out_results
    def cleanup_reverse_replication(self):
        """Cleanup reverse publication (on DEST) and reverse subscription (on SOURCE)."""
        pub_name = self.replication_cfg['publication_name'] + "_rev"
        sub_name = self.replication_cfg['subscription_name'] + "_rev"

        # Robust subscription drop (on SOURCE for reverse)
        sql_sub = f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_subscription WHERE subname = '{sub_name}') THEN
                ALTER SUBSCRIPTION {sub_name} DISABLE;
                ALTER SUBSCRIPTION {sub_name} SET (slot_name = NONE);
                DROP SUBSCRIPTION {sub_name};
            END IF;
        END
        $$;
        """
        sql_pub = f"DROP PUBLICATION IF EXISTS {pub_name};"
        sql_slot = (f"SELECT pg_drop_replication_slot('{sub_name}') WHERE EXISTS "
                    f"(SELECT 1 FROM pg_replication_slots WHERE slot_name = '{sub_name}');")

        executed_sqls = []
        out_results = []

        try:
            dest_client = db.PostgresClient(
                self.config.get_dest_conn(), label="DESTINATION")
            source_client = db.PostgresClient(
                self.config.get_source_conn(), label="SOURCE")

            # Sub is on SOURCE for reverse
            executed_sqls.append(f"[SOURCE] {sql_sub}")
            try:
                source_client.execute_script(sql_sub, autocommit=True)
                out_results.append("OK")
            except Exception as e:
                logging.warning(
                    f"Failed to drop reverse subscription on source: {e}")
                out_results.append(str(e))

            # Slot is on DEST for reverse
            executed_sqls.append(f"[DEST] {sql_slot}")
            try:
                dest_client.execute_script(sql_slot, autocommit=True)
                out_results.append("OK")
            except Exception as e:
                logging.warning(
                    f"Failed to drop reverse replication slot on destination: {e}")
                out_results.append(str(e))
            # Pub is on DEST for reverse
            executed_sqls.append(f"[DEST] {sql_pub}")
            try:
                dest_client.execute_script(sql_pub, autocommit=True)
                out_results.append("OK")
            except Exception as e:
                logging.warning(
                    f"Failed to drop reverse publication on destination: {e}")
                out_results.append(str(e))

            success = all(res == "OK" for res in out_results)
            msg = "Reverse replication cleaned up." if success else "Reverse replication cleanup partially failed."
            return success, msg, executed_sqls, out_results

        except Exception as e:
            logging.error(f"Reverse cleanup failed: {e}", exc_info=True)
            # Ensure out_results has same length as executed_sqls for
            # consistency
            while len(out_results) < len(executed_sqls):
                out_results.append(str(e))
            if not executed_sqls:
                executed_sqls.append("INITIALIZATION")
                out_results.append(str(e))
            return False, f"Reverse cleanup failed: {str(e)}", executed_sqls, out_results
