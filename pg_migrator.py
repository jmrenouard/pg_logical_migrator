#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# pg_migrator.py — PostgreSQL Logical Migrator CLI
# =============================================================================
# Main entry point for the pg_logical_migrator tool.
# This script provides a comprehensive command-line interface with
# subcommands for every migration step, plus global options for
# configuration, logging, and reporting.
#
# Usage:
#   python pg_migrator.py --help
#   python pg_migrator.py <command> [options]
#
# Author:  Jean-Marie Renouard
# License: MIT
# =============================================================================

import argparse
import datetime
import json
import logging
import os
import sys
import textwrap
import time

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Ensure src/ is importable from project root
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.config import Config
from src.db import PostgresClient
from src import db as _db_module
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator


# ============================================================================
# Helpers
# ============================================================================

def setup_logging(level: str = "INFO", log_file: str = None):
    """Configure root logger with console + optional file handler."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def setup_results_dir(base: str = None) -> str:
    """Create and return a timestamped results directory."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if base:
        results_dir = base
    else:
        results_dir = os.path.join("RESULTS", timestamp)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir


def build_clients(config: Config):
    """Return (source_client, dest_client) from a Config object."""
    sc = PostgresClient(config.get_source_conn(), label="SOURCE")
    dc = PostgresClient(config.get_dest_conn(), label="DESTINATION")
    return sc, dc


def print_status(success: bool, message: str):
    """Pretty-print a step result to stdout."""
    tag = "\033[32m[OK]\033[0m" if success else "\033[31m[FAIL]\033[0m"
    print(f"  {tag}  {message}")


def print_table(headers: list, rows: list):
    """Print a simple ASCII table to stdout."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print()
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print()


def print_verbose_execution(args, cmds, outs=None):
    """If verbose is enabled, print commands and outputs to stdout."""
    if not getattr(args, "verbose", False) or not cmds:
        return
    print("\n  [VERBOSE] Executed Commands and Results:")
    outs = outs or []
    for i, c in enumerate(cmds):
        print(f"    CMD: {str(c).strip()}")
        if i < len(outs) and outs[i]:
            out_str = str(outs[i]).strip()
            lines = out_str.split("\n")
            if len(lines) > 10:
                print(f"    OUT: {lines[0]}")
                print(f"         ... ({len(lines)-2} lines hidden) ...")
                print(f"         {lines[-1]}")
            else:
                for idx, line in enumerate(lines):
                    prefix = "    OUT: " if idx == 0 else "         "
                    print(f"{prefix}{line}")
    print()


def generate_sample_config(path: str):
    """Write a sample config_migrator.ini to *path*."""
    content = textwrap.dedent("""\
        [source]
        host = localhost
        port = 5432
        user = postgres
        password = secret
        database = source_db

        [destination]
        host = localhost
        port = 5433
        user = postgres
        password = secret
        database = dest_db

        [replication]
        publication_name = migrator_pub
        subscription_name = migrator_sub
        target_schema = public
        loglevel = INFO
        log_file = pg_migrator.log
    """)
    with open(path, "w") as fh:
        fh.write(content)
    print(f"Sample configuration written to: {path}")


# ============================================================================
# Individual command handlers
# ============================================================================

# -- Step 1 ------------------------------------------------------------------
def cmd_check(args):
    """Step 1: Check connectivity to source and destination databases."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc)
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
    checker = DBChecker(sc)
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
    return 0


# -- Step 3 ------------------------------------------------------------------
def cmd_params(args):
    """Step 3: Verify replication parameters on source and destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc)
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
def cmd_migrate_schema(args):
    """Step 4: Copy schema from source to destination (pg_dump -s | psql)."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        print("[DRY-RUN] Would execute schema migration (pg_dump -s | psql)")
        if args.drop_dest:
            print("[DRY-RUN]  -> WITH --drop-dest (would drop destination DB first)")
        return 0
    print("\n=== Step 4 — Schema Migration ===")
    success, msg, cmds, outs = migrator.step4_migrate_schema(drop_dest=args.drop_dest)
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
def cmd_repl_status(args):
    """Step 7: Show logical replication status."""
    from rich.console import Console
    from rich.table import Table

    cfg = Config(args.config)
    migrator = Migrator(cfg)
    console = Console()
    console.print("\n[bold blue]=== Step 7 — Replication Status ===[/bold blue]")
    status = migrator.get_replication_status()
    
    pub_rows = status.get("publisher", [])
    sub_rows = status.get("subscriber", [])
    slot_rows = status.get("slots", [])
    full_sub_rows = status.get("full_sub", [])
    pub_info_rows = status.get("publications", [])
    pub_tables_rows = status.get("pub_tables", [])

    if not any([pub_rows, sub_rows, slot_rows, full_sub_rows, pub_info_rows, pub_tables_rows]):
        console.print("[yellow]  No active publisher, subscriber, or replication slots found.[/yellow]")
        return 1

    def print_rich_table(title, rows):
        if not rows:
            return
        table = Table(title=title, show_header=True, header_style="bold magenta")
        keys = list(rows[0].keys())
        for key in keys:
            table.add_column(str(key), style="cyan", overflow="fold")
        for r in rows:
            table.add_row(*[str(v) for v in r.values()])
        console.print(table)

    if pub_rows:
        print_rich_table("[SOURCE] PUBLISHER (pg_stat_replication)", pub_rows)

    if sub_rows:
        print_rich_table("[DEST] SUBSCRIBER (pg_stat_subscription snippet)", sub_rows)

    if slot_rows:
        print_rich_table("[SOURCE] SLOTS (pg_replication_slots)", slot_rows)

    if full_sub_rows:
        print_rich_table("[DEST] PG_STAT_SUBSCRIPTION", full_sub_rows)

    if pub_info_rows:
        print_rich_table("[SOURCE] PUBLICATIONS (pg_publication)", pub_info_rows)

    if pub_tables_rows:
        print_rich_table("[SOURCE] PUBLICATION TABLES (pg_publication_tables)", pub_tables_rows)

    return 0


# -- Step 8 / 9 / 10 ---------------------------------------------------------
def cmd_sync_sequences(args):
    """Steps 8-9: Synchronize sequence values from source to destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc)
    if args.dry_run:
        print("[DRY-RUN] Would synchronize all sequences from source to destination")
        return 0
    print("\n=== Steps 8/9 — Sync Sequences ===")
    success, msg, cmds, outs = ps.sync_sequences()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


def cmd_enable_triggers(args):
    """Step 10: Enable all triggers on destination tables."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc)
    if args.dry_run:
        print("[DRY-RUN] Would enable triggers on all destination tables")
        return 0
    print("\n=== Step 10 — Enable Triggers ===")
    success, msg, cmds, outs = ps.enable_triggers()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


def cmd_disable_triggers(args):
    """Disable all triggers on destination tables (utility command)."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc)
    if args.dry_run:
        print("[DRY-RUN] Would disable triggers on all destination tables")
        return 0
    print("\n=== Disable Triggers ===")
    success, msg, cmds, outs = ps.disable_triggers()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 11 ------------------------------------------------------------------
def cmd_refresh_matviews(args):
    """Step 11: Refresh materialized views on destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc)
    if args.dry_run:
        print("[DRY-RUN] Would refresh all materialized views on destination")
        return 0
    print("\n=== Step 11 — Refresh Materialized Views ===")
    success, msg, cmds, outs = ps.refresh_materialized_views()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Reassign Ownership -------------------------------------------------------
def cmd_reassign_owner(args):
    """Reassign ownership of all database objects on destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    ps = PostSync(sc, dc)
    target_owner = getattr(args, 'owner', None) or cfg.get_dest_dict()['user']
    if args.dry_run:
        print(f"[DRY-RUN] Would reassign all objects to '{target_owner}' on destination")
        return 0
    print(f"\n=== Reassign Ownership to '{target_owner}' ===")
    success, msg, cmds, outs = ps.reassign_ownership(target_owner)
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Step 13 ------------------------------------------------------------------
def cmd_audit_objects(args):
    """Step 13: Compare object counts between source and destination."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    validator = Validator(sc, dc)
    print("\n=== Step 13 — Object Audit ===")
    success, msg, cmds, outs, report = validator.audit_objects()
    rows = [[r["type"], r["source"], r["dest"], r["status"]] for r in report]
    print_table(["Object Type", "Source", "Dest", "Status"], rows)
    print_verbose_execution(args, cmds, outs)
    has_diff = any(r["status"] != "OK" for r in report)
    return 1 if has_diff else 0


# -- Step 14 ------------------------------------------------------------------
def cmd_validate_rows(args):
    """Step 14: Compare row counts for every table."""
    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    validator = Validator(sc, dc)
    print("\n=== Step 14 — Row Count Parity ===")
    success, msg, cmds, outs, report = validator.compare_row_counts()
    rows = [[r["table"], r["source"], r["dest"], r["diff"], r["status"]] for r in report]
    print_table(["Table", "Source", "Dest", "Diff", "Status"], rows)
    print(f"  {msg}")
    print_verbose_execution(args, cmds, outs)
    has_diff = any(r["status"] != "OK" for r in report)
    return 1 if has_diff else 0


# -- Step 12 ------------------------------------------------------------------
def cmd_cleanup(args):
    """Step 12: Drop subscription, publication, and replication slot."""
    cfg = Config(args.config)
    migrator = Migrator(cfg)
    if args.dry_run:
        sub = cfg.get_replication()["subscription_name"]
        pub = cfg.get_replication()["publication_name"]
        print(f"[DRY-RUN] Would drop subscription '{sub}' and publication '{pub}'")
        return 0
    print("\n=== Step 12 — Cleanup Replication ===")
    success, msg, cmds, outs = migrator.step12_terminate_replication()
    print_status(success, msg)
    print_verbose_execution(args, cmds, outs)
    return 0 if success else 1


# -- Removed auto pipeline to favor init-replication & post-migration ---
def cmd_init_replication(args):
    """Initialize replication WITHOUT terminating it."""
    results_dir = setup_results_dir(args.results_dir)
    log_file = os.path.join(results_dir, "pg_migrator.log")
    setup_logging(args.loglevel, log_file)

    cfg = Config(args.config)
    sc, dc = build_clients(cfg)
    checker = DBChecker(sc, dc)
    migrator = Migrator(cfg)
    post_sync = PostSync(sc, dc)
    validator = Validator(sc, dc)
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
            ("4",  "Schema Migration (pg_dump -s | psql)"),
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

        # Step 4 — Schema
        print("[Step  4] Schema migration...")
        s, m, c, o = migrator.step4_migrate_schema(drop_dest=args.drop_dest)
        reporter.add_step("4", "Schema Migration", "OK" if s else "FAIL", m, commands=c, outputs=o)
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

        # Sync Delay
        print(f"[  wait ] Sleeping {sync_delay}s for initial table sync...")
        time.sleep(sync_delay)

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
        s2, m2, c2, o2, r2 = validator.compare_row_counts()
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
        report_path = os.path.join(results_dir, "migration_report.html")
        out = reporter.generate_html(report_path)
        print(f"\n  HTML report : {out}")

    except Exception as e:
        print(f"\n\033[31mFATAL ERROR: {e}\033[0m")
        logging.critical(f"Fatal error: {e}", exc_info=True)
        reporter.add_step("FATAL", "Exception", "ERROR", str(e))
        report_path = os.path.join(results_dir, "migration_report_error.html")
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
    checker = DBChecker(sc, dc)
    migrator = Migrator(cfg)
    post_sync = PostSync(sc, dc)
    validator = Validator(sc, dc)
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

        # Step 12 — Cleanup (Stop replication)
        print("[Step 12] Cleanup replication...")
        s, m, c, o = migrator.step12_terminate_replication()
        reporter.add_step("12", "Cleanup", "OK" if s else "FAIL", m, commands=c, outputs=o)
        print_status(s, m)

        # Step 8/9/10/11 — Post-Sync
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
        s2, m2, c2, o2, r2 = validator.compare_row_counts()
        parity_detail_lines = [f"{'Table':<45} {'Source':>10} {'Dest':>10} {'Diff':>8} {'Status':>8}"]
        parity_detail_lines.append("-" * 85)
        for row in r2:
            parity_detail_lines.append(f"{row['table']:<45} {str(row['source']):>10} {str(row['dest']):>10} {str(row['diff']):>8} {row['status']:>8}")
        parity_details = "\n".join(parity_detail_lines)
        reporter.add_step("14", "Row Parity", "OK" if s2 else "FAIL", m2,
                          details=parity_details, commands=c2, outputs=o2)
        print_status(s2, m2)

        # Generate report
        report_path = os.path.join(results_dir, "migration_report.html")
        out = reporter.generate_html(report_path)
        print(f"\n  HTML report : {out}")



    except Exception as e:
        print(f"\n\033[31mFATAL ERROR: {e}\033[0m")
        logging.critical(f"Fatal error: {e}", exc_info=True)
        reporter.add_step("FATAL", "Exception", "ERROR", str(e))
        report_path = os.path.join(results_dir, "migration_report_error.html")
        reporter.generate_html(report_path)
        exit_code = 2

    print(f"\n  Log file    : {log_file}")
    print(f"  Results dir : {results_dir}")
    return exit_code


# -- TUI mode ----------------------------------------------------------------
def cmd_tui(args):
    """Launch the interactive Textual TUI."""
    from src.main import MigratorApp
    app = MigratorApp(args.config)
    app.run()
    return 0


# -- Generate sample config --------------------------------------------------
def cmd_generate_config(args):
    """Generate a sample config_migrator.ini file."""
    output = args.output if hasattr(args, "output") and args.output else "config_migrator.sample.ini"
    generate_sample_config(output)
    return 0


# ============================================================================
# CLI argument parser
# ============================================================================

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
        default=10,
        metavar="SECONDS",
        help="Seconds to wait after subscription creation for initial sync (default: 10)",
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

    # Step 4 — migrate-schema
    p_schema = sub.add_parser(
        "migrate-schema",
        parents=[global_parser],
        help="Step 4  — Copy schema from source to destination",
        description="Run pg_dump -s on source and pipe into psql on destination.",
    )
    p_schema.set_defaults(func=cmd_migrate_schema)
    p_schema.add_argument(
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
        description="DROP + CREATE PUBLICATION FOR ALL TABLES on the source.",
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

    # Step 8/9 — sync-sequences
    p_seq = sub.add_parser(
        "sync-sequences",
        parents=[global_parser],
        help="Steps 8/9 — Synchronize sequence values",
        description="Read current sequence values from source and apply them on destination.",
    )
    p_seq.set_defaults(func=cmd_sync_sequences)

    # Step 10 — enable-triggers
    p_trig = sub.add_parser(
        "enable-triggers",
        parents=[global_parser],
        help="Step 10 — Enable all triggers on destination",
        description="ALTER TABLE … ENABLE TRIGGER ALL on every user table in the destination.",
    )
    p_trig.set_defaults(func=cmd_enable_triggers)

    # (utility) — disable-triggers
    p_dtrig = sub.add_parser(
        "disable-triggers",
        parents=[global_parser],
        help="Utility — Disable all triggers on destination",
        description="ALTER TABLE … DISABLE TRIGGER ALL on every user table in the destination.",
    )
    p_dtrig.set_defaults(func=cmd_disable_triggers)

    # Step 11 — refresh-matviews
    p_mv = sub.add_parser(
        "refresh-matviews",
        parents=[global_parser],
        help="Step 11 — Refresh materialized views on destination",
        description="REFRESH MATERIALIZED VIEW for every materialized view on the destination.",
    )
    p_mv.set_defaults(func=cmd_refresh_matviews)

    # Reassign ownership
    p_owner = sub.add_parser(
        "reassign-owner",
        parents=[global_parser],
        help="Reassign ownership of all objects on destination",
        description="ALTER … OWNER TO for every object (database, schemas, tables, views, matviews, sequences, functions, types) on the destination.",
    )
    p_owner.add_argument(
        "--owner",
        metavar="ROLE",
        default=None,
        help="Target owner role (default: destination user from config)",
    )
    p_owner.set_defaults(func=cmd_reassign_owner)

    # Step 13 — audit-objects
    p_audit = sub.add_parser(
        "audit-objects",
        parents=[global_parser],
        help="Step 13 — Compare object counts (tables, views, indexes, sequences, functions)",
        description="Count objects on both databases and show differences.",
    )
    p_audit.set_defaults(func=cmd_audit_objects)

    # Step 14 — validate-rows
    p_rows = sub.add_parser(
        "validate-rows",
        parents=[global_parser],
        help="Step 14 — Compare row counts per table",
        description="SELECT COUNT(*) on every table in both source and destination.",
    )
    p_rows.set_defaults(func=cmd_validate_rows)

    # Step 12 — cleanup
    p_clean = sub.add_parser(
        "cleanup",
        parents=[global_parser],
        help="Step 12 — Drop subscription, publication, and replication slot",
        description="Destructive cleanup: removes all replication objects. Run AFTER validation.",
    )
    p_clean.set_defaults(func=cmd_cleanup)

    # -- Removed auto command --

    # init-replication
    p_init = sub.add_parser(
        "init-replication",
        parents=[global_parser],
        help="Initialize replication and update elements WITHOUT stopping replication",
        description="Runs schema migration, setups pub/sub, syncs objects and validates. Leaves replication active.",
    )
    p_init.set_defaults(func=cmd_init_replication)
    p_init.add_argument("--drop-dest", action="store_true", default=False, help="Drop and recreate destination database before migration")

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


# ============================================================================
# Entry point
# ============================================================================

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
