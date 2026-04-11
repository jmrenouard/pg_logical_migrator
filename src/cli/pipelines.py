import os
import time
import logging
from src.config import Config
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator
from src.cli.helpers import build_clients, print_status, setup_results_dir, setup_logging

__version__ = "unknown"
try:
    import os, re
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pg_mig_path = os.path.join(base_dir, "pg_migrator.py")
    with open(pg_mig_path, "r") as f:
        for line in f:
            if line.startswith("__version__"):
                __version__ = line.split("=")[1].strip().strip('\'"')
                break
except Exception:
    pass

# -- Full Init Replication pipeline --------------------------------------------
def cmd_init_replication(args):
    """Initialize replication WITHOUT terminating it."""
    results_dir = setup_results_dir(args.results_dir)
    log_file = os.path.join(results_dir, "pg_migrator.log")
    setup_logging(args.loglevel, log_file)

    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc, cfg)
    migrator = Migrator(cfg)
    post_sync = PostSync(sc, dc, cfg)
    validator = Validator(sc, dc, cfg)
    reporter = ReportGenerator()

    sync_delay = args.sync_delay

    print(f"\n{'='*60}")
    print(f"  pg_logical_migrator — Automated Pipeline v{__version__}")
    print(f"  Config      : {args.config}")
    print(f"  Results dir : {results_dir}")
    print(f"  Log level   : {args.loglevel}")
    print(f"  Sync delay  : {sync_delay}s")
    if args.dry_run:
        print(f"  Mode        : DRY-RUN (no changes)")
    print(f"{'='*60}\n")

    if args.dry_run:
        steps = [
            ("1",  "Connectivity Check"),
            ("2",  "Pre-Migration Diagnostics"),
            ("3",  "Replication Parameters Check"),
            ("4a", "Schema Migration (Pre-Data)"),
            ("5",  "Create Publication"),
            ("6",  "Create Subscription"),
            ("--", f"Wait {sync_delay}s for initial sync"),
            ("13", "Object Audit"),
            ("14", "Row Parity Check"),
        ]
        for num, desc in steps:
            print(f"  [DRY-RUN] Step {num:>2s} : {desc}")
        print("\n  No changes were made.\n")
        return 0

    exit_code = 0
    try:
        # Step 1 — Connectivity
        print("[Step  1] Connectivity check...")
        res = checker.check_connectivity()
        ok = res["source"] and res["dest"]
        reporter.add_step("1", "Connectivity", "OK" if ok else "FAIL",
                          f"Source: {res['source']}, Dest: {res['dest']}")
        print_status(ok, f"Source={res['source']}  Dest={res['dest']}")
        if not ok:
            raise RuntimeError("Connectivity check failed — aborting pipeline.")

        # Step 2 — Pre-Migration Diagnostics
        print("[Step  2] Pre-migration diagnostics...")
        diag = checker.check_problematic_objects()
        diag_lines = [
            f"{'Category':<25} {'Count / Detail':>15}",
            "-" * 42,
            f"{'Tables without PK':<25} {len(diag['no_pk']):>15}",
            f"{'Large Objects':<25} {diag['large_objects']:>15}",
            f"{'Identity Columns':<25} {len(diag['identities']):>15}",
            f"{'Unowned Sequences':<25} {len(diag['unowned_seqs']):>15}",
            f"{'Unlogged Tables':<25} {len(diag.get('unlogged_tables', [])):>15}",
            f"{'Temporary Tables':<25} {len(diag.get('temp_tables', [])):>15}",
            f"{'Foreign Tables':<25} {len(diag.get('foreign_tables', [])):>15}",
            f"{'Materialized Views':<25} {len(diag.get('matviews', [])):>15}",
        ]
        if diag["no_pk"]:
            diag_lines.append("\nTables without Primary Key:")
            for t in diag["no_pk"]:
                diag_lines.append(f"  - {t['schema_name']}.{t['table_name']}")
        if diag["unowned_seqs"]:
            diag_lines.append("\nUnowned Sequences:")
            for s in diag["unowned_seqs"]:
                diag_lines.append(f"  - {s['schema_name']}.{s['seq_name']}")
        if diag["identities"]:
            diag_lines.append("\nIdentity Columns:")
            for ic in diag["identities"]:
                diag_lines.append(f"  - {ic['table_schema']}.{ic['table_name']}.{ic['column_name']}")
        if diag.get("matviews"):
            diag_lines.append("\nMaterialized Views:")
            for m in diag["matviews"]:
                diag_lines.append(f"  - {m['schema_name']}.{m['matview_name']}")
        
        # Size Analysis
        sizes = checker.get_database_size_analysis(sc)
        if sizes:
            diag_lines.append(f"\nTotal Database Size: {sizes['database']['total_pretty']}")
            diag_lines.append("\nTop 10 Tables by Size:")
            diag_lines.append(f"{'Table':<45} {'Data':>10} {'Index':>10} {'Total':>10} {'%':>8}")
            diag_lines.append("-" * 87)
            for t in sizes["tables"][:10]:
                diag_lines.append(
                    f"{t['schema_name'] + '.' + t['table_name']:<45} "
                    f"{t['data_pretty']:>10} {t['index_pretty']:>10} {t['total_pretty']:>10} {str(t['percent']) + '%':>8}"
                )

        diag_details = "\n".join(diag_lines)
        has_warnings = len(diag["no_pk"]) > 0 or diag["large_objects"] > 0
        reporter.add_step("2", "Pre-Migration Diagnostics",
                          "WARN" if has_warnings else "OK",
                          f"PK missing: {len(diag['no_pk'])}, LOBs: {diag['large_objects']}, "
                          f"Identity cols: {len(diag['identities'])}, Unowned seqs: {len(diag['unowned_seqs'])}",
                          details=diag_details)
        print_status(not has_warnings,
                     f"No-PK={len(diag['no_pk'])}  LOBs={diag['large_objects']}  "
                     f"Identities={len(diag['identities'])}  UnownedSeqs={len(diag['unowned_seqs'])}")

        # Step 3 — Replication Parameters
        print("[Step  3] Replication parameters...")
        params = checker.check_replication_params()
        param_lines = []
        params_ok = True
        for label, title in [("source", "SOURCE"), ("dest", "DESTINATION")]:
            if params.get(label):
                param_lines.append(f"=== {title} ===")
                param_lines.append(f"{'Parameter':<35} {'Current':>15} {'Expected':>15} {'Status':>8}")
                param_lines.append("-" * 75)
                for r in params[label]:
                    param_lines.append(
                        f"{r['parameter']:<35} {r['actual']:>15} {r['expected']:>15} {r['status']:>8}"
                    )
                    if r['status'] != 'OK':
                        params_ok = False
                param_lines.append("")
        param_details = "\n".join(param_lines)
        reporter.add_step("3", "Replication Parameters",
                          "OK" if params_ok else "FAIL",
                          "Source and destination parameters verified",
                          details=param_details)
        print_status(params_ok, "Replication parameters verified")

        # Step 4a — Schema Pre-Data
        print("[Step 4a] Schema pre-data migration...")
        s, m, c, o = migrator.step4a_migrate_schema_pre_data(drop_dest=args.drop_dest)
        reporter.add_step("4a", "Schema Pre-Data", "OK" if s else "FAIL", m, commands=c, outputs=o)
        print_status(s, m)

        # Step 5 — Publication
        print("[Step  5] Setup Publication...")
        s, m, c, o = migrator.step5_setup_source()
        reporter.add_step("5", "Source Setup", "OK" if s else "FAIL", m, commands=c, outputs=o)
        print_status(s, m)

        # Step 6 — Subscription
        print("[Step  6] Setup Subscription...")
        s, m, c, o = migrator.step6_setup_destination()
        reporter.add_step("6", "Destination Setup", "OK" if s else "FAIL", m, commands=c, outputs=o)
        print_status(s, m)

        # Wait for sync
        if not getattr(args, "no_wait", False):
            print("[  wait ] Waiting for initial table sync to complete...")
            success_sync, msg_sync, _, _ = migrator.wait_for_sync(timeout=args.sync_delay, show_progress=True)
            print_status(success_sync, msg_sync)
        else:
            print("[  skip ] Skipping wait for initial synchronization (--no-wait).")

        # Step 13 — Object Audit
        print("[Step 13] Object audit...")
        s1, m1, c1, o1, r1 = validator.audit_objects()
        # Build a readable text table from the object audit report
        audit_detail_lines = [f"{'Object Type':<15} {'Source':>10} {'Dest':>10} {'Status':>8}"]
        audit_detail_lines.append("-" * 47)
        for row in r1:
            audit_detail_lines.append(
                f"{row['type']:<15} {str(row['source']):>10} {str(row['dest']):>10} {row['status']:>8}"
            )
        audit_details = "\n".join(audit_detail_lines)
        reporter.add_step("13", "Object Audit", "OK" if s1 else "FAIL", m1,
                          details=audit_details, commands=c1, outputs=o1)
        print_status(s1, m1)

        # Step 14 — Row Parity
        print("[Step 14] Row count parity...")
        s2, m2, c2, o2, r2 = validator.compare_row_counts(use_stats=args.use_stats)
        # Build a readable text table from the per-table report
        parity_detail_lines = [f"{'Table':<45} {'Source':>10} {'Dest':>10} {'Diff':>8} {'Status':>8}"]
        parity_detail_lines.append("-" * 85)
        for row in r2:
            parity_detail_lines.append(
                f"{row['table']:<45} {str(row['source']):>10} {str(row['dest']):>10} "
                f"{str(row['diff']):>8} {row['status']:>8}"
            )
        parity_details = "\n".join(parity_detail_lines)
        reporter.add_step("14", "Row Parity", "OK" if s2 else "FAIL", m2,
                          details=parity_details, commands=c2, outputs=o2)
        print_status(s2, m2)


        # Generate report
        report_path = os.path.join(results_dir, "report_init.html")
        out = reporter.generate_html(report_path)
        print(f"\n  HTML report : {out}")

    except Exception as e:
        print(f"\n\033[31mFATAL ERROR: {e}\033[0m")
        logging.critical(f"Fatal error: {e}", exc_info=True)
        reporter.add_step("FATAL", "Exception", "ERROR", str(e))
        report_path = os.path.join(results_dir, "report_init_error.html")
        reporter.generate_html(report_path)
        exit_code = 2

    print(f"\n  Log file    : {log_file}")
    print(f"  Results dir : {results_dir}")
    return exit_code



# -- Full Post Migration pipeline --------------------------------------------
def cmd_post_migration(args):
    """Stop replication and finalize migration objects."""
    results_dir = setup_results_dir(args.results_dir)
    log_file = os.path.join(results_dir, "pg_migrator.log")
    setup_logging(args.loglevel, log_file)

    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc, cfg)
    migrator = Migrator(cfg)
    post_sync = PostSync(sc, dc, cfg)
    validator = Validator(sc, dc, cfg)
    reporter = ReportGenerator()

    sync_delay = 0

    print(f"\n{'='*60}")
    print(f"  pg_logical_migrator — Automated Pipeline v{__version__}")
    print(f"  Config      : {args.config}")
    print(f"  Results dir : {results_dir}")
    print(f"  Log level   : {args.loglevel}")
    print(f"  Sync delay  : {sync_delay}s")
    if args.dry_run:
        print(f"  Mode        : DRY-RUN (no changes)")
    print(f"{'='*60}\n")

    if args.dry_run:
        steps = [
            ("1",  "Connectivity Check"),
            ("12", "Cleanup Replication (Stop)"),
            ("4b", "Schema Migration (Post-Data)"),
            ("8",  "Refresh Materialized Views"),
            ("9",  "Sync Sequences"),
            ("10", "Enable Triggers"),
            ("13", "Object Audit"),
            ("14", "Row Parity Check"),
        ]
        for num, desc in steps:
            print(f"  [DRY-RUN] Step {num:>2s} : {desc}")
        print("\n  No changes were made.\n")
        return 0

    exit_code = 0
    try:
        # Step 1 — Connectivity
        print("[Step  1] Connectivity check...")
        res = checker.check_connectivity()
        ok = res["source"] and res["dest"]
        reporter.add_step("1", "Connectivity", "OK" if ok else "FAIL",
                          f"Source: {res['source']}, Dest: {res['dest']}")
        print_status(ok, f"Source={res['source']}  Dest={res['dest']}")
        if not ok:
            raise RuntimeError("Connectivity check failed — aborting pipeline.")

        # Ensure sync is finished
        print("[  wait ] Ensuring all data is synchronized before stopping replication...")
        success_sync, msg_sync, _, _ = migrator.wait_for_sync(timeout=args.sync_delay, show_progress=True)
        print_status(success_sync, msg_sync)

        # Step 12 — Cleanup (Stop replication)
        print("[Step 12] Cleanup replication...")
        s, m, c, o = migrator.step12_terminate_replication()
        reporter.add_step("12", "Cleanup", "OK" if s else "FAIL", m, commands=c, outputs=o)
        print_status(s, m)

        # Step 4b / 8/9/10/11 — Post-Sync
        print("[Step 4b] Schema post-data migration...")
        s4b, m4b, c4b, o4b = migrator.step4b_migrate_schema_post_data()
        reporter.add_step("4b", "Schema Post-Data", "OK" if s4b else "FAIL", m4b, commands=c4b, outputs=o4b)
        print_status(s4b, m4b)

        print("[Step  8] Refresh materialized views...")
        s1, m1, c1, o1 = post_sync.refresh_materialized_views()
        print_status(s1, m1)

        print("[Step  9] Sync sequences...")
        s2, m2, c2, o2 = post_sync.sync_sequences()
        print_status(s2, m2)

        print("[Step 10] Enable triggers...")
        s3, m3, c3, o3 = post_sync.enable_triggers()
        print_status(s3, m3)

        # Reassign Ownership
        target_owner = cfg.get_dest_dict()['user']
        print(f"[  owner] Reassign ownership to '{target_owner}'...")
        s4, m4, c4, o4 = post_sync.reassign_ownership(target_owner)
        print_status(s4, m4)

        all_cmds = (c1 or []) + (c2 or []) + (c3 or []) + (c4 or [])
        all_outs = (o1 or []) + (o2 or []) + (o3 or []) + (o4 or [])
        reporter.add_step("POST", "Post-Sync", "OK",
                          "MatViews, Sequences, Triggers, Ownership processed",
                          commands=all_cmds, outputs=all_outs)

        # Step 13 — Object Audit
        print("[Step 13] Object audit...")
        s1, m1, c1, o1, r1 = validator.audit_objects()
        audit_detail_lines = [f"{'Object Type':<15} {'Source':>10} {'Dest':>10} {'Status':>8}"]
        audit_detail_lines.append("-" * 47)
        for row in r1:
            audit_detail_lines.append(f"{row['type']:<15} {str(row['source']):>10} {str(row['dest']):>10} {row['status']:>8}")
        audit_details = "\n".join(audit_detail_lines)
        reporter.add_step("13", "Object Audit", "OK" if s1 else "FAIL", m1,
                          details=audit_details, commands=c1, outputs=o1)
        print_status(s1, m1)

        # Step 14 — Row Parity
        print("[Step 14] Row count parity...")
        s2, m2, c2, o2, r2 = validator.compare_row_counts(use_stats=args.use_stats)
        parity_detail_lines = [f"{'Table':<45} {'Source':>10} {'Dest':>10} {'Diff':>8} {'Status':>8}"]
        parity_detail_lines.append("-" * 85)
        for row in r2:
            parity_detail_lines.append(f"{row['table']:<45} {str(row['source']):>10} {str(row['dest']):>10} {str(row['diff']):>8} {row['status']:>8}")
        parity_details = "\n".join(parity_detail_lines)
        reporter.add_step("14", "Row Parity", "OK" if s2 else "FAIL", m2,
                          details=parity_details, commands=c2, outputs=o2)
        print_status(s2, m2)

        # Generate report
        report_path = os.path.join(results_dir, "report_post.html")
        out = reporter.generate_html(report_path)
        print(f"\n  HTML report : {out}")

    except Exception as e:
        print(f"\n\033[31mFATAL ERROR: {e}\033[0m")
        logging.critical(f"Fatal error: {e}", exc_info=True)
        reporter.add_step("FATAL", "Exception", "ERROR", str(e))
        report_path = os.path.join(results_dir, "report_post_error.html")
        reporter.generate_html(report_path)
        exit_code = 2

    print(f"\n  Log file    : {log_file}")
    print(f"  Results dir : {results_dir}")
    return exit_code
