import logging


class PostSync:
    def __init__(self, source_client, dest_client, config=None):
        self.source = source_client
        self.dest = dest_client
        self.config = config

    def _get_schema_filter(self, nspname_col="n.nspname"):
        if not self.config:
            return ""
        schemas = self.config.get_target_schemas()
        if schemas == ['all']:
            return ""
        schema_list = ", ".join([f"'{s}'" for s in schemas])
        return f"AND {nspname_col} IN ({schema_list})"

    def refresh_materialized_views(self):
        logging.info("[DEST] Refreshing materialized views on destination...")
        sf = self._get_schema_filter()
        query = f"""
        SELECT n.nspname AS schema_name, c.relname AS matview_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        cmds = []
        outs = []
        try:
            matviews = self.dest.execute_query(query) or []
            for row in matviews:
                schema = row['schema_name']
                name = row['matview_name']
                sql = f'REFRESH MATERIALIZED VIEW "{schema}"."{name}";'
                cmds.append(f"[DEST] {sql}")
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Processed {len(cmds)} materialized views", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def sync_sequences(self):
        logging.info("[BOTH] Synchronizing sequences...")
        sf = self._get_schema_filter()
        query = f"""
        SELECT n.nspname AS schema_name, c.relname AS seq_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        cmds = []
        outs = []
        try:
            seqs = self.source.execute_query(query) or []
            for row in seqs:
                schema = row['schema_name']
                name = row['seq_name']
                try:
                    res = self.source.execute_query(
                        f'SELECT last_value, is_called FROM "{schema}"."{name}"')
                    if res:
                        last_val = res[0]['last_value']
                        is_called = res[0]['is_called']
                        is_called_str = str(is_called).lower()
                        sql = (f'SELECT setval(\'"{schema}"."{name}"\', {last_val}, '
                               f'{is_called_str});')
                        cmds.append(f"[DEST] {sql}")
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
        logging.info("[DEST] Enabling all triggers on destination...")
        sf = self._get_schema_filter()
        query = f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        cmds = []
        outs = []
        try:
            tables = self.dest.execute_query(query) or []
            for row in tables:
                schema = row['schema_name']
                name = row['table_name']
                sql = f'ALTER TABLE "{schema}"."{name}" ENABLE TRIGGER ALL;'
                cmds.append(f"[DEST] {sql}")
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Enabled triggers on {len(cmds)} tables", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def disable_triggers(self):
        logging.info("[DEST] Disabling all triggers on destination...")
        sf = self._get_schema_filter()
        query = f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        cmds = []
        outs = []
        try:
            tables = self.dest.execute_query(query) or []
            for row in tables:
                schema = row['schema_name']
                name = row['table_name']
                sql = f'ALTER TABLE "{schema}"."{name}" DISABLE TRIGGER ALL;'
                cmds.append(f"[DEST] {sql}")
                try:
                    self.dest.execute_script(sql)
                    outs.append("SUCCESS")
                except Exception as e:
                    outs.append(f"FAILED: {e}")
            return True, f"Disabled triggers on {len(cmds)} tables", cmds, outs
        except Exception as e:
            return False, str(e), [query], [str(e)]

    def _apply_reassign(self, sql, label, cmds, outs):
        cmds.append(f"[DEST] {sql}")
        try:
            self.dest.execute_script(sql)
            outs.append("SUCCESS")
            return 0
        except Exception as e:
            logging.error(f"[DEST] Failed to reassign owner ({label}): {e}")
            outs.append(f"FAILED: {e}")
            return 1

    def reassign_ownership(self, target_owner):
        """Reassign ownership of ALL database objects to target_owner on destination."""
        logging.info(
            f"[DEST] Reassigning ownership of all objects to '{target_owner}'...")
        sf = self._get_schema_filter()
        cmds = []
        outs = []
        errors = 0

        # --- 1. Database ---
        try:
            db_name_result = self.dest.execute_query(
                "SELECT current_database() AS db;")
            if db_name_result:
                db_name = db_name_result[0]['db']
                sql = f'ALTER DATABASE "{db_name}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(sql,
                                               f"Database {db_name}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER DATABASE ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 2. Schemas ---
        schema_query = f"""
        SELECT nspname AS schema_name
        FROM pg_namespace
        WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND nspname NOT LIKE 'pg_temp_%'
          AND nspname NOT LIKE 'pg_toast_temp_%'
          {self._get_schema_filter(nspname_col="nspname")};
        """
        try:
            schemas = self.dest.execute_query(schema_query) or []
            for row in schemas:
                schema = row['schema_name']
                sql = f'ALTER SCHEMA "{schema}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(sql,
                                               f"Schema {schema}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER SCHEMA ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 3. Tables (relkind = 'r') ---
        table_query = f"""
        SELECT n.nspname AS schema_name, c.relname AS obj_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            tables = self.dest.execute_query(table_query) or []
            for row in tables:
                sch = row['schema_name']
                obj = row['obj_name']
                sql = f'ALTER TABLE "{sch}"."{obj}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"Table {sch}.{obj}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER TABLE ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 4. Views (relkind = 'v') ---
        view_query = f"""
        SELECT n.nspname AS schema_name, c.relname AS obj_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'v'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            views = self.dest.execute_query(view_query) or []
            for row in views:
                sch = row['schema_name']
                obj = row['obj_name']
                sql = f'ALTER VIEW "{sch}"."{obj}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"View {sch}.{obj}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER VIEW ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 5. Materialized Views (relkind = 'm') ---
        matview_query = f"""
        SELECT n.nspname AS schema_name, c.relname AS obj_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            matviews = self.dest.execute_query(matview_query) or []
            for row in matviews:
                sch = row['schema_name']
                obj = row['obj_name']
                sql = f'ALTER MATERIALIZED VIEW "{sch}"."{obj}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"MatView {sch}.{obj}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER MATERIALIZED VIEW ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 6. Sequences (relkind = 'S') ---
        seq_query = f"""
        SELECT n.nspname AS schema_name, c.relname AS obj_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            seqs = self.dest.execute_query(seq_query) or []
            for row in seqs:
                sch = row['schema_name']
                obj = row['obj_name']
                sql = f'ALTER SEQUENCE "{sch}"."{obj}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"Sequence {sch}.{obj}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER SEQUENCE ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 7. Functions and Procedures ---
        func_query = f"""
        SELECT n.nspname AS schema_name,
               p.proname AS func_name,
               pg_catalog.pg_get_function_identity_arguments(p.oid) AS func_args,
               CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS func_type
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            funcs = self.dest.execute_query(func_query) or []
            for row in funcs:
                ftype = row['func_type']
                sch = row['schema_name']
                fname = row['func_name']
                fargs = row['func_args']
                sql = f'ALTER {ftype} "{sch}"."{fname}"({fargs}) OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"{ftype} {sch}.{fname}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER FUNCTION/PROCEDURE ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        # --- 8. Custom Types (enums, composites, domains) ---
        type_query = f"""
        SELECT n.nspname AS schema_name, t.typname AS type_name
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typtype IN ('e', 'c', 'd')
          AND t.typrelid = 0
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf};
        """
        try:
            types = self.dest.execute_query(type_query) or []
            for row in types:
                sch = row['schema_name']
                tname = row['type_name']
                sql = f'ALTER TYPE "{sch}"."{tname}" OWNER TO "{target_owner}";'
                errors += self._apply_reassign(
                    sql, f"Type {sch}.{tname}", cmds, outs)
        except Exception as e:
            cmds.append("[DEST] ALTER TYPE ... OWNER TO ...")
            outs.append(f"FAILED: {e}")
            errors += 1

        total = len(cmds)
        success_count = total - errors
        ok = errors == 0
        msg = f"Reassigned {success_count}/{total} objects to '{target_owner}'" + \
            (f" ({errors} errors)" if errors else "")
        return ok, msg, cmds, outs
