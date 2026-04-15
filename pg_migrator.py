#!/usr/bin/env python3
# ============================================================================
# pg_logical_migrator
# PostgreSQL Logical Migrator CLI Tool
# ============================================================================
import argparse
import sys
import textwrap
import logging

# Ensure src/ is importable
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

__version__ = "1.3.1"

from src.cli.pipelines import cmd_init_replication, cmd_post_migration
from src.cli.commands import (
    cmd_check, cmd_diagnose, cmd_params,
    cmd_migrate_schema_pre_data, cmd_migrate_schema_post_data,
    cmd_setup_pub, cmd_setup_sub, cmd_repl_status, cmd_repl_progress,
    cmd_sync_sequences, cmd_enable_triggers, cmd_disable_triggers,
    cmd_refresh_matviews, cmd_reassign_owner,
    cmd_audit_objects, cmd_validate_rows, cmd_cleanup, cmd_setup_reverse,
    cmd_cleanup_reverse, cmd_tui, cmd_generate_config
)
from src.cli.helpers import setup_logging
import src.db as _db_module

def build_parser() -> argparse.ArgumentParser:
    """Build the complete argument parser with subcommands."""

    # ---- Top-level parser ---------------------------------------------------
    parser = argparse.ArgumentParser(
        prog="pg_migrator.py",
        description=textwrap.dedent("""\
            ╔══════════════════════════════════════════════════════════╗
            ║  pg_logical_migrator — PostgreSQL Logical Migrator CLI  ║
            ╚══════════════════════════════════════════════════════════╝

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
        help="Step 2  — Pre-migration diagnostics (PK, LOBs, sequences)",
        description="Scan the source database for objects that may block logical replication.",
    )
    p_diag.set_defaults(func=cmd_diagnose)

    # Step 3 — params
    p_params = sub.add_parser(
        "params",
        parents=[global_parser],
        help="Step 3  — Verify replication parameters (wal_level, etc.)",
        description="Check that wal_level, max_replication_slots, max_wal_senders are correct.",
    )
    p_params.set_defaults(func=cmd_params)

    # Step 4a — migrate-schema-pre-data
    p_schema_pre = sub.add_parser(
        "migrate-schema-pre-data",
        parents=[global_parser],
        help="Step 4a — Copy schema pre-data from source to destination",
        description="Run pg_dump -s --section=pre-data on source and pipe into psql on destination.",
    )
    p_schema_pre.set_defaults(func=cmd_migrate_schema_pre_data)
    p_schema_pre.add_argument(
        "--drop-dest",
        action="store_true",
        default=False,
        help="Drop and recreate destination database before migration",
    )

    # Step 5 — setup-pub
    p_pub = sub.add_parser(
        "setup-pub",
        parents=[global_parser],
        help="Step 5  — Create publication on source",
        description="DROP + CREATE PUBLICATION on the source.",
    )
    p_pub.set_defaults(func=cmd_setup_pub)

    # Step 6 — setup-sub
    p_sub = sub.add_parser(
        "setup-sub",
        parents=[global_parser],
        help="Step 6  — Create subscription on destination",
        description="DROP + CREATE SUBSCRIPTION on the destination pointing to the source publication.",
    )
    p_sub.set_defaults(func=cmd_setup_sub)

    # Step 7 — repl-status
    p_repl = sub.add_parser(
        "repl-status",
        parents=[global_parser],
        help="Step 7  — Show replication status",
        description="Query pg_stat_subscription to display current replication state.",
    )
    p_repl.set_defaults(func=cmd_repl_status)

    # repl-progress
    p_prog = sub.add_parser(
        "repl-progress",
        parents=[global_parser],
        help="Monitor progress of initial data copy",
        description="Show individual table sync states and active COPY progress.",
    )
    p_prog.set_defaults(func=cmd_repl_progress)

    # Step 8 — refresh-matviews
    p_mv = sub.add_parser(
        "refresh-matviews",
        parents=[global_parser],
        help="Step 8  — Refresh materialized views on destination",
        description="REFRESH MATERIALIZED VIEW for every materialized view on the destination.",
    )
    p_mv.set_defaults(func=cmd_refresh_matviews)

    # Step 9/10 — sync-sequences
    p_seq = sub.add_parser(
        "sync-sequences",
        parents=[global_parser],
        help="Steps 9/10 — Synchronize sequence values",
        description="Read current sequence values from source and apply them on destination.",
    )
    p_seq.set_defaults(func=cmd_sync_sequences)

    # Step 11 — enable-triggers
    p_trig = sub.add_parser(
        "enable-triggers",
        parents=[global_parser],
        help="Step 11 — Enable all triggers on destination",
        description="ALTER TABLE … ENABLE TRIGGER ALL on every user table in the destination.",
    )
    p_trig.set_defaults(func=cmd_enable_triggers)

    # Step 12 — migrate-schema-post-data
    p_schema_post = sub.add_parser(
        "migrate-schema-post-data",
        parents=[global_parser],
        help="Step 12 — Copy schema post-data from source to destination",
        description="Run pg_dump -s --section=post-data on source and pipe into psql on destination.",
    )
    p_schema_post.set_defaults(func=cmd_migrate_schema_post_data)

    # Step 13 — reassign-owner
    p_owner = sub.add_parser(
        "reassign-owner",
        parents=[global_parser],
        help="Step 13 — Reassign ownership of all objects on destination",
        description="ALTER … OWNER TO for every object (database, schemas, tables, views, matviews, sequences, functions, types) on the destination.",
    )
    p_owner.add_argument(
        "--owner",
        metavar="ROLE",
        default=None,
        help="Target owner role (default: destination user from config)",
    )
    p_owner.set_defaults(func=cmd_reassign_owner)

    # Step 14 — audit-objects
    p_audit = sub.add_parser(
        "audit-objects",
        parents=[global_parser],
        help="Step 14 — Compare object counts (tables, views, indexes, sequences, functions)",
        description="Count objects on both databases and show differences.",
    )
    p_audit.set_defaults(func=cmd_audit_objects)

    # Step 15 — validate-rows
    p_rows = sub.add_parser(
        "validate-rows",
        parents=[global_parser],
        help="Step 15 — Compare row counts per table",
        description="SELECT COUNT(*) on every table in both source and destination.",
    )
    p_rows.set_defaults(func=cmd_validate_rows)

    # Step 16 — cleanup
    p_clean = sub.add_parser(
        "cleanup",
        parents=[global_parser],
        help="Step 16 — Drop subscription, publication, and replication slot",
        description="Destructive cleanup: removes all replication objects. Run AFTER validation.",
    )
    p_clean.set_defaults(func=cmd_cleanup)

    # Step 17 — setup-reverse
    p_rev = sub.add_parser(
        "setup-reverse",
        parents=[global_parser],
        help="Step 17 — Setup reverse replication for rollback",
        description="Creates publication on destination and subscription on source to sync changes back.",
    )
    p_rev.set_defaults(func=cmd_setup_reverse)

    # cleanup-reverse
    p_cln_rev = sub.add_parser(
        "cleanup-reverse",
        parents=[global_parser],
        help="Cleanup reverse replication objects",
        description="Removes reverse publication (on DEST) and reverse subscription (on SOURCE).",
    )
    p_cln_rev.set_defaults(func=cmd_cleanup_reverse)

    # init-replication
    p_init = sub.add_parser(
        "init-replication",
        parents=[global_parser],
        help="Initialize replication and update elements WITHOUT stopping replication",
        description="Runs schema migration, setups pub/sub, syncs objects and validates. Leaves replication active.",
    )
    p_init.set_defaults(func=cmd_init_replication)
    p_init.add_argument("--drop-dest", action="store_true", default=False, help="Drop and recreate destination database before migration")
    p_init.add_argument("--no-wait", action="store_true", default=False, help="Do not wait for initial synchronization to complete")

    # post-migration
    p_post = sub.add_parser(
        "post-migration",
        parents=[global_parser],
        help="Stop replication and update elements on destination",
        description="Terminates replication, refreshes matviews, sequences, triggers, then validates.",
    )
    p_post.set_defaults(func=cmd_post_migration)

    # TUI — interactive mode
    p_tui = sub.add_parser(
        "tui",
        parents=[global_parser],
        help="Launch the interactive Terminal UI (Textual)",
        description="Full-screen TUI dashboard for supervised step-by-step migration.",
    )
    p_tui.set_defaults(func=cmd_tui)

    # Generate config file
    p_gen = sub.add_parser(
        "generate-config",
        parents=[global_parser],
        help="Generate a sample configuration file",
        description="Write a sample config_migrator.ini to disk.",
    )
    p_gen.add_argument(
        "-o", "--output",
        default="config_migrator.sample.ini",
        metavar="FILE",
        help="Output path for generated config (default: config_migrator.sample.ini)",
    )
    p_gen.set_defaults(func=cmd_generate_config)

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
