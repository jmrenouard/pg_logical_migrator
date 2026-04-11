import logging

class Validator:
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

    def compare_row_counts(self, use_stats=False):
        """Step 14: Compare row counts. Exact via COUNT(*) or estimated via pg_stat_user_tables."""
        mode_label = "ESTIMATED (stats)" if use_stats else "EXACT (count)"
        logging.info(f"[BOTH] Comparing row counts between source and destination ({mode_label})...")
        
        schema_filter = self._get_schema_filter()
        
        if use_stats:
            query_tables = f"""
            SELECT 
                schemaname AS schema_name, 
                relname AS table_name, 
                n_live_tup AS row_count
            FROM pg_stat_user_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
              {self._get_schema_filter(nspname_col="schemaname")};
            """
        else:
            query_tables = f"""
            SELECT n.nspname AS schema_name, c.relname AS table_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              {schema_filter};
            """

        report = []
        cmds = [f"[SOURCE] {query_tables}"]
        outs = [f"Mode: {mode_label}"]
        
        try:
            if use_stats:
                s_stats = self.source.execute_query(query_tables) or []
                d_stats = self.dest.execute_query(query_tables) or []
                
                # Convert to dict for easy lookup: {(schema, table): count}
                s_map = {(r['schema_name'], r['table_name']): r['row_count'] for r in s_stats}
                d_map = {(r['schema_name'], r['table_name']): r['row_count'] for r in d_stats}
                
                # Union of all keys
                all_keys = sorted(list(set(s_map.keys()) | set(d_map.keys())))
                
                for schema, name in all_keys:
                    s_count = s_map.get((schema, name), 0)
                    d_count = d_map.get((schema, name), 0)
                    diff = s_count - d_count
                    status = "OK" if diff == 0 else "DIFF"
                    
                    report.append({
                        "table": f"{schema}.{name}",
                        "source": s_count,
                        "dest": d_count,
                        "diff": diff,
                        "status": status
                    })
                    outs.append(f"{schema}.{name}: source~{s_count}  dest~{d_count}  diff~{diff}  [{status}]")
            else:
                tables = self.source.execute_query(query_tables) or []
                for row in tables:
                    schema = row['schema_name']
                    name = row['table_name']
                    q_count = f'SELECT count(*) FROM "{schema}"."{name}"'
                    cmds.append(f"[BOTH] {q_count}")
                    try:
                        s_res = self.source.execute_query(q_count)
                        d_res = self.dest.execute_query(q_count)
                        s_count = s_res[0]['count'] if s_res else 0
                        d_count = d_res[0]['count'] if d_res else 0
                        diff = s_count - d_count
                        status = "OK" if diff == 0 else "DIFF"
                        outs.append(f"{schema}.{name}: source={s_count}  dest={d_count}  diff={diff}  [{status}]")
                        report.append({
                            "table": f"{schema}.{name}",
                            "source": s_count,
                            "dest": d_count,
                            "diff": diff,
                            "status": status
                        })
                    except Exception as e:
                        logging.error(f"[BOTH] Error counting table {schema}.{name}: {e}")
                        outs.append(f"{schema}.{name}: ERROR - {e}")
                        report.append({
                            "table": f"{schema}.{name}",
                            "source": "ERROR",
                            "dest": "ERROR",
                            "diff": "-",
                            "status": "ERROR"
                        })
        except Exception as e:
            logging.error(f"Failed to fetch row counts: {e}")
            return False, str(e), cmds, outs, []
        
        summary = f"Compared {len(report)} tables ({mode_label}). Diffs found: {len([r for r in report if r['status'] != 'OK'])}"
        return True, summary, cmds, outs, report

    def audit_objects(self):
        """Step 13: Audit and compare all object counts."""
        logging.info("[BOTH] Auditing object counts between source and destination...")
        sf = self._get_schema_filter()
        query = f"""
        SELECT 'TABLE' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema') {sf}
        UNION ALL
        SELECT 'VIEW' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'v' AND n.nspname NOT IN ('pg_catalog', 'information_schema') {sf}
        UNION ALL
        SELECT 'INDEX' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'i' AND n.nspname NOT IN ('pg_catalog', 'information_schema') {sf}
        UNION ALL
        SELECT 'SEQUENCE' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema') {sf}
        UNION ALL
        SELECT 'FUNCTION' AS type, count(*)::int as count FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') {self._get_schema_filter(nspname_col="n.nspname")};
        """
        source_res = self.source.execute_query(query)
        dest_res = self.dest.execute_query(query)
        
        s_counts = {r['type']: r['count'] for r in source_res}
        d_counts = {r['type']: r['count'] for r in dest_res}
        
        report = []
        for obj_type in ['TABLE', 'VIEW', 'INDEX', 'SEQUENCE', 'FUNCTION']:
            s_val = s_counts.get(obj_type, 0)
            d_val = d_counts.get(obj_type, 0)
            report.append({
                "type": obj_type,
                "source": s_val,
                "dest": d_val,
                "status": "OK" if s_val == d_val else "DIFF"
            })
        
        return True, "Object audit completed", [f"[BOTH] {query}"], ["Source counts: " + str(s_counts) + "\nDest counts: " + str(d_counts)], report
