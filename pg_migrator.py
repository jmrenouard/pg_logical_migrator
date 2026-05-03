#!/usr/bin/env python3
# ============================================================================
# pg_logical_migrator
# PostgreSQL Logical Migrator CLI Tool
# ============================================================================
import src.db as _db_module
from src.cli.helpers import setup_logging
from src.cli.commands import (
    cmd_check, cmd_diagnose, cmd_params,
    cmd_migrate_schema_pre_data, cmd_terminate_replication,
    cmd_setup_pub, cmd_setup_sub, cmd_progress, cmd_wait_sync,
    cmd_sync_sequences, cmd_enable_triggers, cmd_refresh_matviews,
    cmd_reassign_owner, cmd_audit_objects,
    cmd_validate_rows, cmd_cleanup, cmd_setup_reverse, cmd_cleanup_reverse,
    cmd_sync_lobs, cmd_sync_unlogged, cmd_tui, cmd_generate_config
)
from src.cli.pipelines import cmd_init_replication, cmd_post_migration
import argparse
import sys
import textwrap
import logging

# Ensure src/ is importable
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

__version__ = "1.4.0"


def build_parser() -> argparse.ArgumentParser:
    """Build the complete argument parser with subcommands."""

    # ---- Top-level parser ---------------------------------------------------
    parser = argparse.ArgumentParser(
        prog="pg_migrator.py",
        description=textwrap.dedent("""\
            ╔═══════════════════════════════════════════════════════════╗
            ║   pg_logical_migrator — PostgreSQL Logical Migrator CLI   ║
            ╚═══════════════════════════════════════════════════════════╝

            Automate PostgreSQL database migrations using logical
            replication.  Run individual steps or the full pipeline.
        """),
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s check                          # Test connectivity
              %(prog)s diagnose                       # Pre-flight diagnostics
              %(prog)s init-replication --drop-dest   # Initialize replication, drop existing DB
              %(prog)s post-migration                 # Finalize replication
              %(prog)s tui                            # Interactive TUI mode
              %(prog)s validate-rows --config prod.ini
              %(prog)s generate-config --output my.ini
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ---- Global options -----------------------------------------------------
    global_parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    global_parser.add_argument(
        "-c", "--config",
        default="config_migrator.ini",
        metavar="FILE",
        help="Path to the .ini configuration file (default: config_migrator.ini)",
    )
    global_parser.add_argument(
        "--results-dir",
        metavar="DIR",
        help="Directory for storing results and reports (default: RESULTS/<timestamp>)",
    )
    global_parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    global_parser.add_argument(
        "--log-file",
        metavar="FILE",
        help="Path to the log file (default: pg_migrator.log or RESULTS/<ts>/pg_migrator.log)",
    )
    global_parser.add_argument(
        "--sync-delay",
        type=int,
        default=3600,
        metavar="SECONDS",
        help="Max seconds to wait for initial sync to complete (default: 3600)",
    )
    global_parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be done without executing any changes",
    )
    global_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Verbose mode: print every SQL command, result, and error to stderr",
    )
    global_parser.add_argument(
        "--use-stats",
        action="store_true",
        default=False,
        help="Use pg_stat_user_tables for row counts (estimation) instead of COUNT(*) (exact)",
    )

    # ---- Subcommands --------------------------------------------------------
    sub = parser.add_subparsers(
        dest="command",
        title="Available Commands",
        description="Use '%(prog)s <command> --help' for per-command help.",
        metavar="<command>",
    )

    # Step 1 — check
    p_check = sub.add_parser(
        "check",
        parents=[global_parser],
        help="Step 1  — Check connectivity to source and destination",
        description="Verify that both PostgreSQL instances are reachable.",
    )
    p_check.set_defaults(func=cmd_check)

    # Step 2 — diagnose
    p_diag = sub.add_parser(
        "diagnose",
        parents=[global_parser],
        help="Step 2  — Database diagnostics and compatibility scan",
        description="Scan for Primary Keys, LOBs, Sequences, Unlogged tables, and Materialized Views.",
    )
    p_diag.set_defaults(func=cmd_diagnose)

    # Step 3 — params
    p_params = sub.add_parser(
        "params",
        parents=[global_parser],
        help="Step 3  — Verify PostgreSQL replication parameters",
        description="Confirm mandatory settings (wal_level, slots, workers) on both instances.",
    )
    p_params.set_defaults(func=cmd_params)

    # Step 4 — migrate-schema-pre-data
    p_schema_pre = sub.add_parser(
        "migrate-schema-pre-data",
        parents=[global_parser],
        help="Step 4  — Schema (pre-data): Deploy base structures",
        description="Deploy schemas, tables, types, and views from source to destination.",
    )
    p_schema_pre.add_argument(
        "--drop-dest",
        action="store_true",
        default=False,
        help="Drop and recreate destination database before migration")
    p_schema_pre.set_defaults(func=cmd_migrate_schema_pre_data)

    # --- Phase 2: Execution ---

    # Step 5 — setup-pub
    p_pub = sub.add_parser(
        "setup-pub",
        parents=[global_parser],
        help="Step 5  — Setup publication on source database",
        description="Create logical replication publication for the target schemas.",
    )
    p_pub.set_defaults(func=cmd_setup_pub)

    # Step 6 — setup-sub
    p_sub = sub.add_parser(
        "setup-sub",
        parents=[global_parser],
        help="Step 6  — Setup subscription on destination database",
        description="Create logical replication subscription and trigger initial data copy.",
    )
    p_sub.set_defaults(func=cmd_setup_sub)

    # Step 7 — repl-progress
    p_prog = sub.add_parser(
        "repl-progress",
        parents=[global_parser],
        help="Step 7  — Monitor initial data copy progress",
        description="Interactive monitor showing individual table sync states and COPY progress.",
    )
    p_prog.set_defaults(func=cmd_progress)

    # --- Phase 3: Finalization ---

    # Step 8 — refresh-matviews
    p_mv = sub.add_parser(
        "refresh-matviews",
        parents=[global_parser],
        help="Step 8  — Refresh materialized views on destination",
        description="REFRESH MATERIALIZED VIEW for every materialized view on the destination.",
    )
    p_mv.set_defaults(func=cmd_refresh_matviews)

    # Step 9 — sync-sequences
    p_seq = sub.add_parser(
        "sync-sequences",
        parents=[global_parser],
        help="Step 9  — Synchronize sequence values",
        description="Read current sequence values from source and apply them on destination.",
    )
    p_seq.set_defaults(func=cmd_sync_sequences)

    # Step 10 — terminate-repl
    p_term = sub.add_parser(
        "terminate-repl",
        parents=[global_parser],
        help="Step 10 — Terminate replication & Schema (post-data)",
        description="Stop logical replication and deploy indexes, FKs, and constraints.",
    )
    p_term.set_defaults(func=cmd_terminate_replication)

    # Step 11 — sync-lobs
    p_lob = sub.add_parser(
        "sync-lobs",
        parents=[global_parser],
        help="Step 11a — Synchronize Large Objects (LOBs)",
        description="Manually migrate binary data (OIDs) and update table references.",
    )
    p_lob.set_defaults(func=cmd_sync_lobs)

    # Step 11b — sync-unlogged
    p_unl = sub.add_parser(
        "sync-unlogged",
        parents=[global_parser],
        help="Step 11b — Synchronize UNLOGGED tables",
        description="Manually copy UNLOGGED tables using COPY.",
    )
    p_unl.set_defaults(func=cmd_sync_unlogged)

    # Step 12 — enable-triggers
    p_trig = sub.add_parser(
        "enable-triggers",
        parents=[global_parser],
        help="Step 12 — Enable all triggers on destination",
        description="Restore application-level trigger logic on the target database.",
    )
    p_trig.set_defaults(func=cmd_enable_triggers)

    # Step 13 — reassign-owner
    p_owner = sub.add_parser(
        "reassign-owner",
        parents=[global_parser],
        help="Step 13 — Reassign object ownership",
        description="Set correct role owners for all database objects on the destination.",
    )
    p_owner.add_argument(
        "--owner",
        metavar="ROLE",
        default=None,
        help="Target owner role (default: destination user)")
    p_owner.set_defaults(func=cmd_reassign_owner)

    # --- Phase 4: Validation & Cleanup ---

    # Step 14 — audit-objects
    p_audit = sub.add_parser(
        "audit-objects",
        parents=[global_parser],
        help="Step 14 — Perform structural object audit",
        description="Verify parity of tables, indexes, views, and sequences between databases.",
    )
    p_audit.set_defaults(func=cmd_audit_objects)

    # Step 15 — validate-rows
    p_rows = sub.add_parser(
        "validate-rows",
        parents=[global_parser],
        help="Step 15 — Perform row count parity validation",
        description="Compare row counts for all replicated tables to ensure data consistency.",
    )
    p_rows.set_defaults(func=cmd_validate_rows)

    # Step 16 — cleanup
    p_clean = sub.add_parser(
        "cleanup",
        parents=[global_parser],
        help="Step 16 — Decommission replication objects",
        description="Destructive cleanup: removes subscription, publication, and slots.",
    )
    p_clean.set_defaults(func=cmd_cleanup)

    # Step 17 — setup-reverse
    p_rev = sub.add_parser(
        "setup-reverse",
        parents=[global_parser],
        help="Step 17 — Setup reverse replication (Rollback path)",
        description="Prepare a path to sync changes back from destination to source.",
    )
    p_rev.set_defaults(func=cmd_setup_reverse)

    # --- Utilities ---

    # progress
    p_p = sub.add_parser(
        "progress",
        parents=[global_parser],
        help="Utility: Quick replication status check")
    p_p.set_defaults(func=cmd_progress)

    # wait-sync
    p_w = sub.add_parser(
        "wait-sync",
        parents=[global_parser],
        help="Utility: Wait for replication synchronization")
    p_w.set_defaults(func=cmd_wait_sync)

    # cleanup-reverse
    p_cr = sub.add_parser(
        "cleanup-reverse",
        parents=[global_parser],
        help="Utility: Cleanup reverse replication objects")
    p_cr.set_defaults(func=cmd_cleanup_reverse)

    # generate-config
    p_gen = sub.add_parser(
        "generate-config",
        parents=[global_parser],
        help="Utility: Generate sample configuration file")
    p_gen.add_argument(
        "-o",
        "--output",
        default="config_migrator.sample.ini",
        help="Output path")
    p_gen.set_defaults(func=cmd_generate_config)

    # --- Automated Pipelines ---

    p_init = sub.add_parser(
        "init-replication",
        parents=[global_parser],
        help="Automated Phase 1 & 2 (Init replication)")
    p_init.add_argument(
        "--drop-dest",
        action="store_true",
        help="Drop destination first")
    p_init.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for initial sync")
    p_init.set_defaults(func=cmd_init_replication)

    p_post = sub.add_parser(
        "post-migration",
        parents=[global_parser],
        help="Automated Phase 3 & 4 (Cutover & Validation)")
    p_post.set_defaults(func=cmd_post_migration)

    p_tui = sub.add_parser(
        "tui",
        parents=[global_parser],
        help="Launch interactive Terminal UI dashboard")
    p_tui.set_defaults(func=cmd_tui)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Setup logging with global options
    log_file = getattr(args, "log_file", None)
    setup_logging(getattr(args, "loglevel", "INFO"), log_file)

    # Enable verbose diagnostic output
    if getattr(args, "verbose", False):
        _db_module.VERBOSE = True

    # Dispatch to the selected subcommand
    try:
        rc = args.func(args)
        sys.exit(rc)
    except FileNotFoundError as e:
        print(f"\033[31mError: {e}\033[0m", file=sys.stderr)
        print("  → Use 'pg_migrator.py generate-config' to create a sample config file.",
              file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.critical(f"Unhandled exception: {e}", exc_info=True)
        print(f"\033[31mFatal error: {e}\033[0m", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
