import logging

class Validator:
    def __init__(self, source_client, dest_client):
        self.source = source_client
        self.dest = dest_client

    def compare_row_counts(self):
        logging.info("Comparing row counts between source and destination...")
        query_tables = """
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');
        """
        tables = self.source.execute_query(query_tables) or []
        report = []
        cmds = [query_tables]
        outs = ["Fetched list of tables"]
        
        for row in tables:
            schema = row['schema_name']
            name = row['table_name']
            q_count = f'SELECT count(*) FROM "{schema}"."{name}"'
            cmds.append(q_count)
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
                logging.error(f"Error counting table {schema}.{name}: {e}")
                outs.append(f"{schema}.{name}: ERROR - {e}")
                report.append({
                    "table": f"{schema}.{name}",
                    "source": "ERROR",
                    "dest": "ERROR",
                    "diff": "-",
                    "status": "ERROR"
                })
        
        summary = f"Compared {len(report)} tables. Diffs found: {len([r for r in report if r['status'] != 'OK'])}"
        return True, summary, cmds, outs, report

    def audit_objects(self):
        """Step 13: Audit and compare all object counts."""
        logging.info("Auditing object counts between source and destination...")
        query = """
        SELECT 'TABLE' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        UNION ALL
        SELECT 'VIEW' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'v' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        UNION ALL
        SELECT 'INDEX' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'i' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        UNION ALL
        SELECT 'SEQUENCE' AS type, count(*)::int as count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        UNION ALL
        SELECT 'FUNCTION' AS type, count(*)::int as count FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema');
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
        
        return True, "Object audit completed", [query], ["Source counts: " + str(s_counts) + "\nDest counts: " + str(d_counts)], report
