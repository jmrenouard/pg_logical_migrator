from src.config import Config
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.cli.helpers import (
    build_clients, 
    print_status, 
    print_table, 
    print_verbose_execution,
    generate_sample_config
)

# -- Step 1 ------------------------------------------------------------------
def cmd_check(args):
    """Step 1: Check connectivity to source and destination databases."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc, cfg)
    res = checker.check_connectivity()
    print("\n=== Step 1 — Connectivity Check ===")
    print_status(res["source"], f"Source  : {'CONNECTED' if res['source'] else 'UNREACHABLE'}")
    print_status(res["dest"],   f"Dest    : {'CONNECTED' if res['dest'] else 'UNREACHABLE'}")
    return 0 if res["source"] and res["dest"] else 1


# -- Step 2 ------------------------------------------------------------------
def cmd_diagnose(args):
    """Step 2: Run pre-migration diagnostics on the source database."""
    cfg = Config(args.config)
    sc, _ = build_clients(cfg)
    checker = DBChecker(sc, None, cfg)
    res = checker.check_problematic_objects()
    print("\n=== Step 2 — Pre-Migration Diagnostics ===")
    print_table(
        ["Category", "Count / Detail"],
        [
            ["Tables without PK", len(res["no_pk"])],
            ["Large Objects",     res["large_objects"]],
            ["Identity Columns",  len(res["identities"])],
            ["Unowned Sequences", len(res["unowned_seqs"])],
            ["Unlogged Tables",   len(res.get("unlogged_tables", []))],
            ["Temporary Tables",  len(res.get("temp_tables", []))],
            ["Foreign Tables",    len(res.get("foreign_tables", []))],
            ["Materialized Views", len(res.get("matviews", []))],
        ],
    )
    if res["no_pk"]:
        print("  Tables without Primary Key:")
        for t in res["no_pk"]:
            print(f"    - {t['schema_name']}.{t['table_name']}")
    if res["unowned_seqs"]:
        print("  Unowned Sequences:")
        for s in res["unowned_seqs"]:
            print(f"    - {s['schema_name']}.{s['seq_name']}")
    if res.get("matviews"):
        print("  Materialized Views:")
        for m in res["matviews"]:
            print(f"    - {m['schema_name']}.{m['matview_name']}")
    print()

    # Size Analysis
    sizes = checker.get_database_size_analysis(sc)
    if sizes:
        print("=== Step 2 — Size Analysis ===")
        if sizes["database"]:
            print(f"  Total Database Size: {sizes['database']['total_pretty']}")
        
        table_rows = []
        # Show top 20 tables by total size
        for t in sizes["tables"][:20]:
            table_rows.append([
                f"{t['schema_name']}.{t['table_name']}",
                t['data_pretty'],
                t['index_pretty'],
                t['total_pretty'],
                f"{t['percent']}%"
            ])
        
        if table_rows:
            print("\n  Top 20 Tables by Size:")
            print_table(["Table", "Data Size", "Index Size", "Total Size", "% DB"], table_rows)
        print()

    return 0


# -- Step 3 ------------------------------------------------------------------
def cmd_params(args):
    """Step 3: Verify replication parameters on source and destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc, cfg)
    results = checker.check_replication_params()
    has_fail = False
    for label, title in [("source", "Source"), ("dest", "Destination")]:
        if results.get(label):
            print(f"\n=== Step 3 — Replication Parameters ({title}) ===")
            rows = [[r["parameter"], r["actual"], r["expected"], r["status"]] for r in results[label]]
            print_table(["Parameter", "Current", "Expected", "Status"], rows)
            if any(r["status"] != "OK" for r in results[label]):
                has_fail = True
    return 1 if has_fail else 0


# -- Step 4 ------------------------------------------------------------------
def cmd_migrate_schema_pre_data(args):
    """Step 4: Copy schema pre-data from source to destination (pg_dump -s --section=pre-data)."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would execute schema pre-data migration")
        if args.drop_dest:
            print("[DRY-RUN]  -> WITH --drop-dest (would drop destination DB first)")
        return 0
    print("\n=== Step 4 — Schema Migration (Pre-data) ===")
    success, msg, cmds, outs = migrator.step4a_migrate_schema_pre_data(drop_dest=args.drop_dest)
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 10 -----------------------------------------------------------------
def cmd_migrate_schema_post_data(args):
    """Step 10: Copy schema post-data from source to destination (pg_dump -s --section=post-data)."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would execute schema post-data migration")
        return 0
    print("\n=== Step 10 — Schema Migration (Post-data) ===")
    success, msg, cmds, outs = migrator.step4b_migrate_schema_post_data()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 5 ------------------------------------------------------------------
def cmd_setup_pub(args):
    """Step 5: Create publication on source database."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        pub = cfg.get_replication()["publication_name"]
        print(f"[DRY-RUN] Would create publication '{pub}' FOR ALL TABLES on source")
        return 0
    print("\n=== Step 5 — Setup Publication ===")
    success, msg, cmds, outs = migrator.step5_setup_source()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 6 ------------------------------------------------------------------
def cmd_setup_sub(args):
    """Step 6: Create subscription on destination database."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        sub = cfg.get_replication()["subscription_name"]
        print(f"[DRY-RUN] Would create subscription '{sub}' on destination")
        return 0
    print("\n=== Step 6 — Setup Subscription ===")
    success, msg, cmds, outs = migrator.step6_setup_destination()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 7 ------------------------------------------------------------------
def cmd_progress(args):
    """Step 7: Monitor progress of initial data synchronization."""
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn

    cfg = Config(args.config)
    migrator = Migrator(cfg)
    console = Console()
    
    console.print("\n[bold blue]=== Step 7 — Logical Replication Progress ===[/bold blue]")
    
    progress_data = migrator.get_initial_copy_progress()
    if not progress_data:
        console.print("[red]Error: Could not fetch progress data.[/red]")
        return 1
    
    summary = progress_data["summary"]
    tables = progress_data["tables"]
    
    if summary["total_tables"] == 0:
        console.print("[yellow]No tables found in publication/replication.[/yellow]")
        return 0

    # 1. Summary Panel
    console.print(f"\n[bold]Overall Progress (Bytes): {summary['percent_bytes']}%[/bold]")
    console.print(f"  {summary['bytes_copied_pretty']} / {summary['total_source_pretty']} copied")
    
    console.print(f"\n[bold]Table Progress: {summary['percent_tables']}%[/bold]")
    console.print(f"  {summary['completed_tables']} / {summary['total_tables']} tables ready")
    
    # 2. Individual Tables Table
    table = Table(title="[Table Sync Progress]", show_header=True, header_style="bold magenta")
    table.add_column("Table", style="cyan")
    table.add_column("State")
    table.add_column("Progress (Bytes)")
    table.add_column("%")
    
    for r in tables:
        color = "green" if r['state'] in ('r', 's') else "yellow"
        if r['state'] == 'd': color = "bold blue"
        
        from src.db import pretty_size
        table.add_row(
            str(r['table_name']),
            f"[{color}]{r['state']}[/{color}]",
            f"{pretty_size(r['bytes_copied'])} / {pretty_size(r['size_source'])}",
            f"{r['percent']}%"
        )
    console.print(table)

    return 0


def cmd_repl_progress(args):
    """Legacy alias for Step 7 progress."""
    return cmd_progress(args)


# -- Step 8 ------------------------------------------------------------------
def cmd_refresh_matviews(args):
    """Step 8: Refresh materialized views on destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc, cfg)
    if args.dry_run:
        print("[DRY-RUN] Would refresh all materialized views on destination")
        return 0
    print("\n=== Step 8 — Refresh Materialized Views ===")
    success, msg, cmds, outs = ps.refresh_materialized_views()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 9 ------------------------------------------------------------------
def cmd_sync_sequences(args):
    """Step 9: Synchronize sequence values from source to destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc, cfg)
    if args.dry_run:
        print("[DRY-RUN] Would synchronize all sequences from source to destination")
        return 0
    print("\n=== Step 9 — Sync Sequences ===")
    success, msg, cmds, outs = ps.sync_sequences()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 10 -----------------------------------------------------------------
def cmd_terminate_replication(args):
    """Step 10: Terminate logical replication and deploy post-data schema."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would stop logical replication and deploy indexes/FKs")
        return 0
    
    print("\n=== Step 10 — Terminate Replication & Deploy Schema (Post-data) ===")
    
    # 1. Stop Replication
    success1, msg1, cmds1, outs1 = migrator.step10_terminate_replication()
    print_status(success1, f"Replication stop: {msg1}")
    
    if not success1:
        return 1
        
    # 2. Deploy post-data schema
    success2, msg2, cmds2, outs2 = migrator.step4b_migrate_schema_post_data()
    print_status(success2, f"Schema migration (post-data): {msg2}")
    
    all_cmds = (cmds1 or []) + (cmds2 or [])
    all_outs = (outs1 or []) + (outs2 or [])
    print_verbose_execution(args, all_cmds, all_outs)
    
    return 0 if success2 else 1


def cmd_migrate_schema_post_data(args):
    """Legacy alias for Step 10."""
    return cmd_terminate_replication(args)


# -- Step 11 ------------------------------------------------------------------
def cmd_sync_lobs(args):
    """Step 11: Synchronize Large Objects (LOBs/BLOBs) and update OID references."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would synchronize Large Objects (LOBs) and update OID references")
        return 0
    print("\n=== Step 11 — Synchronize Large Objects (LOBs) ===")
    success, msg, cmds, outs = migrator.sync_large_objects()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 12 -----------------------------------------------------------------
def cmd_enable_triggers(args):
    """Step 12: Enable all triggers on destination tables."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc, cfg)
    if args.dry_run:
        print("[DRY-RUN] Would enable triggers on all destination tables")
        return 0
    print("\n=== Step 12 — Enable Triggers ===")
    success, msg, cmds, outs = ps.enable_triggers()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


def cmd_disable_triggers(args):
    """Disable all triggers on destination tables (utility command)."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc, cfg)
    if args.dry_run:
        print("[DRY-RUN] Would disable triggers on all destination tables")
        return 0
    print("\n=== Disable Triggers ===")
    success, msg, cmds, outs = ps.disable_triggers()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 13 -----------------------------------------------------------------
def cmd_reassign_owner(args):
    """Step 13: Reassign ownership of all database objects on destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc, cfg)
    target_owner = getattr(args, 'owner', None) or cfg.get_dest_dict()['user']
    if args.dry_run:
        print(f"[DRY-RUN] Would reassign all objects to '{target_owner}' on destination")
        return 0
    print(f"\n=== Step 13 — Reassign Ownership to '{target_owner}' ===")
    success, msg, cmds, outs = ps.reassign_ownership(target_owner)
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 14 ------------------------------------------------------------------
def cmd_audit_objects(args):
    """Step 14: Compare object counts between source and destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    validator = Validator(sc, dc, cfg)
    print("\n=== Step 14 — Object Audit ===")
    success, msg, cmds, outs, report = validator.audit_objects()
    rows = [[r["type"], r["source"], r["dest"], r["status"]] for r in report]
    print_table(["Object Type", "Source", "Dest", "Status"], rows)
    print_verbose_execution(args, cmds, outs)
    has_diff = any(r["status"] != "OK" for r in report)
    return 1 if has_diff else 0


# -- Step 15 ------------------------------------------------------------------
def cmd_validate_rows(args):
    """Step 15: Compare row counts for every table."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    validator = Validator(sc, dc, cfg)
    print("\n=== Step 15 — Row Count Parity ===")
    success, msg, cmds, outs, report = validator.compare_row_counts(use_stats=args.use_stats)
    rows = [[r["table"], r["source"], r["dest"], r["diff"], r["status"]] for r in report]
    print_table(["Table", "Source", "Dest", "Diff", "Status"], rows)
    print(f"  {msg}")
    print_verbose_execution(args, cmds, outs)
    has_diff = any(r["status"] != "OK" for r in report)
    return 1 if has_diff else 0


# -- Step 16 ------------------------------------------------------------------
def cmd_cleanup(args):
    """Step 16: Drop subscription, publication, and replication slot."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        sub = cfg.get_replication()["subscription_name"]
        pub = cfg.get_replication()["publication_name"]
        print(f"[DRY-RUN] Would drop subscription '{sub}' and publication '{pub}'")
        return 0
    print("\n=== Step 16 — Cleanup Replication ===")
    success, msg, cmds, outs = migrator.step10_terminate_replication()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 17 ------------------------------------------------------------------
def cmd_setup_reverse(args):
    """Step 17: Setup reverse replication for rollback capability."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would setup reverse replication")
        return 0
    print("\n=== Step 17 — Setup REVERSE Replication (Rollback) ===")
    success, msg, cmds, outs = migrator.setup_reverse_replication()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Utilities ---------------------------------------------------------------

def cmd_wait_sync(args):
    """Utility: Wait for replication to be in 'streaming' state and fully synced."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    print("\n=== Waiting for replication sync ===")
    success, msg, _, _ = migrator.wait_for_sync(timeout=300, show_progress=True)
    print_status(success, msg)
    return 0 if success else 1


def cmd_cleanup_reverse(args):
    """Cleanup reverse replication objects."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    print("\n=== Cleanup REVERSE Replication (Rollback) ===")
    success, msg, cmds, outs = migrator.cleanup_reverse_replication()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


def cmd_tui(args):
    """Launch the interactive Textual TUI."""
    from src.main import MigratorApp
    app = MigratorApp(args.config)
    app.run()
    return 0


def cmd_generate_config(args):
    """Generate a sample config_migrator.ini file."""
    output = args.output if hasattr(args, "output") and args.output else "config_migrator.sample.ini"
    generate_sample_config(output)
    return 0
