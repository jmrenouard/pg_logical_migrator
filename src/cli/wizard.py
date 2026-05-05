import os
import sys
import logging
import argparse
import time
import threading
import readline
from typing import List, Optional, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich.columns import Columns
from rich import box

from src.config import Config
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator
from src.cli.helpers import build_clients, print_status, setup_results_dir

console = Console()

# ── Step/Command Registry ──────────────────────────────────────────────────
PHASES = [
    ("Preparation", "cyan"),
    ("Execution", "green"),
    ("Finalization", "yellow"),
    ("Validation & Cleanup", "magenta"),
    ("Utilities", "blue"),
    ("Pipelines", "red"),
]

STEPS = [
    # Phase 1 – Preparation
    {"id": "1",   "cmd": "check",                   "name": "Check Connectivity",         "phase": "Preparation",
     "desc": "Verify that source and destination PostgreSQL instances are reachable.",
     "destructive": False},
    {"id": "2",   "cmd": "diagnose",                "name": "Diagnose Objects",            "phase": "Preparation",
     "desc": "Scan for tables without PK, LOBs, sequences, unlogged tables, materialized views.",
     "destructive": False},
    {"id": "3",   "cmd": "params",                  "name": "Verify Replication Params",   "phase": "Preparation",
     "desc": "Confirm wal_level, max_replication_slots, max_worker_processes on both sides.",
     "destructive": False},
    {"id": "4",   "cmd": "migrate-schema-pre-data",  "name": "Schema (Pre-data)",          "phase": "Preparation",
     "desc": "Deploy schemas, tables, types, views via pg_dump --section=pre-data.",
     "destructive": True, "warn": "With --drop-dest this DROPS the destination DB first."},
    # Phase 2 – Execution
    {"id": "5",   "cmd": "setup-pub",               "name": "Setup Publication",           "phase": "Execution",
     "desc": "Create logical replication publication on the source database.",
     "destructive": False},
    {"id": "6",   "cmd": "setup-sub",               "name": "Setup Subscription",          "phase": "Execution",
     "desc": "Create subscription on destination and trigger initial COPY.",
     "destructive": False},
    {"id": "7",   "cmd": "repl-progress",            "name": "Monitor Progress",           "phase": "Execution",
     "desc": "Real-time tracking of table synchronization states and byte progress.",
     "destructive": False},
    # Phase 3 – Finalization
    {"id": "8",   "cmd": "refresh-matviews",         "name": "Refresh MatViews",           "phase": "Finalization",
     "desc": "REFRESH MATERIALIZED VIEW for every matview on the destination.",
     "destructive": False},
    {"id": "9",   "cmd": "sync-sequences",           "name": "Sync Sequences",             "phase": "Finalization",
     "desc": "Read current sequence values from source and apply on destination.",
     "destructive": False},
    {"id": "10",  "cmd": "terminate-repl",           "name": "Terminate Replication",       "phase": "Finalization",
     "desc": "Stop replication, drop subscription and publication.",
     "destructive": True, "warn": "Replication will be stopped permanently."},
    {"id": "10b", "cmd": "migrate-schema-post-data", "name": "Schema (Post-data) ⚠",       "phase": "Finalization",
     "desc": "Deploy indexes, FKs, and constraints.",
     "destructive": True, "warn": "Creates indexes and constraints on the destination."},
    {"id": "11a", "cmd": "sync-lobs",                "name": "Sync LOBs",                  "phase": "Finalization",
     "desc": "Migrate binary large objects (OIDs) and update table references.",
     "destructive": False},
    {"id": "11b", "cmd": "sync-unlogged",            "name": "Sync UNLOGGED Tables",       "phase": "Finalization",
     "desc": "Copy UNLOGGED tables via COPY (not replicated by logical replication).",
     "destructive": False},
    {"id": "12",  "cmd": "enable-triggers",          "name": "Enable Triggers",            "phase": "Finalization",
     "desc": "Restore application-level triggers on destination tables.",
     "destructive": False},
    {"id": "13",  "cmd": "reassign-owner",           "name": "Reassign Ownership",         "phase": "Finalization",
     "desc": "Set correct role owners for all database objects on destination.",
     "destructive": False},
    # Phase 4 – Validation & Cleanup
    {"id": "14",  "cmd": "audit-objects",            "name": "Audit Objects",              "phase": "Validation & Cleanup",
     "desc": "Structural parity check (tables, indexes, views, sequences).",
     "destructive": False},
    {"id": "15",  "cmd": "validate-rows",            "name": "Validate Row Counts",        "phase": "Validation & Cleanup",
     "desc": "Exhaustive row count comparison between source and destination.",
     "destructive": False},
    {"id": "16",  "cmd": "cleanup",                  "name": "Cleanup Replication",        "phase": "Validation & Cleanup",
     "desc": "Drop subscription, publication, and replication slots.",
     "destructive": True, "warn": "This permanently removes all replication objects."},
    {"id": "17",  "cmd": "setup-reverse",            "name": "Setup Reverse Replication",  "phase": "Validation & Cleanup",
     "desc": "Optional: setup reverse replication for rollback path.",
     "destructive": False},
    # Utilities

    {"id": "U2",  "cmd": "wait-sync",                "name": "Wait for Sync",             "phase": "Utilities",
     "desc": "Block until all tables are in 'ready' state (timeout configurable).",
     "destructive": False},
    {"id": "U3",  "cmd": "cleanup-reverse",          "name": "Cleanup Reverse Replication","phase": "Utilities",
     "desc": "Remove reverse replication objects (publication, subscription, slot).",
     "destructive": True, "warn": "Removes reverse replication objects permanently."},
    {"id": "U4",  "cmd": "generate-config",          "name": "Generate Sample Config",     "phase": "Utilities",
     "desc": "Write a sample config_migrator.ini file to disk.",
     "destructive": False},
    {"id": "U5",  "cmd": "stop-repl",                "name": "Stop Replication",           "phase": "Utilities",
     "desc": "Pause logical replication (DISABLE subscription).",
     "destructive": False},
    {"id": "U6",  "cmd": "start-repl",               "name": "Start Replication",          "phase": "Utilities",
     "desc": "Resume logical replication (ENABLE subscription).",
     "destructive": False},
    # Pipelines
    {"id": "P1",  "cmd": "init-replication",         "name": "Init Replication Pipeline",  "phase": "Pipelines",
     "desc": "Automated Phase 1 & 2: check → diagnose → params → schema → pub → sub → monitor.",
     "destructive": True, "warn": "Runs multiple steps automatically. Use --drop-dest with caution."},
    {"id": "P2",  "cmd": "post-migration",           "name": "Post-Migration Pipeline",   "phase": "Pipelines",
     "desc": "Automated Phase 3 & 4: matviews → sequences → terminate → LOBs → triggers → audit.",
     "destructive": True, "warn": "Terminates replication and finalizes migration."},
]

# Build lookup maps
CMD_TO_STEP = {}
ID_TO_STEP = {}
for _s in STEPS:
    CMD_TO_STEP[_s["cmd"]] = _s
    ID_TO_STEP[_s["id"]] = _s


class MigrationWizard:
    def __init__(self, config_path: str, database: Optional[str] = None):
        self.config_path = config_path
        self.database = database
        self.dry_run = False
        self.history: Dict[str, str] = {}  # step_id -> "OK" / "FAIL" / "SKIP"
        self.cfg = None
        self.sc = self.dc = None
        self.checker = self.migrator = self.post_sync = self.validator = None
        self.reporter = ReportGenerator()
        self.results_dir = setup_results_dir()

    # ── Initialization ─────────────────────────────────────────────────────
    def _init_config(self):
        if not os.path.exists(self.config_path):
            console.print(f"[yellow]Config file '{self.config_path}' not found.[/yellow]")
            if Confirm.ask("Generate a default configuration file?", default=True):
                self._run_generate_config()
        self.cfg = Config(self.config_path, self.database)

    def _init_clients(self):
        if not self.cfg:
            return
        try:
            self.sc, self.dc = build_clients(self.cfg)
            self.checker = DBChecker(self.sc, self.dc, self.cfg)
            self.migrator = Migrator(self.cfg)
            self.post_sync = PostSync(self.sc, self.dc, self.cfg)
            self.validator = Validator(self.sc, self.dc, self.cfg)
        except Exception as e:
            console.print(f"[yellow]Could not connect: {e}[/yellow]")

    def _select_database(self):
        if self.database:
            self.cfg.set_override_db(self.database)
            return
        try:
            dbs = self.cfg.get_databases()
        except Exception:
            dbs = []
        if not dbs:
            self.database = Prompt.ask("Database name", default="postgres")
        elif len(dbs) == 1:
            self.database = dbs[0]
        else:
            console.print("[bold]Available databases:[/bold]")
            for i, d in enumerate(dbs, 1):
                console.print(f"  {i}. {d}")
            while True:
                choice = Prompt.ask("Select database (name or number)", default="1")
                # Accept numeric index
                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(dbs):
                        self.database = dbs[idx - 1]
                        break
                    console.print(f"[red]Invalid index. Choose 1–{len(dbs)}.[/red]")
                # Accept exact name
                elif choice in dbs:
                    self.database = choice
                    break
                else:
                    console.print(f"[red]Unknown database '{choice}'. Use a number or exact name.[/red]")
        self.cfg.set_override_db(self.database)

    # ── Display ────────────────────────────────────────────────────────────
    def _banner(self):
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]╔═══════════════════════════════════════════════╗\n"
            "║   PostgreSQL Logical Migrator — Wizard Mode   ║\n"
            "╚═══════════════════════════════════════════════╝[/bold cyan]\n"
            f"  Database : [green]{self.database or '—'}[/green]    "
            f"Config : [green]{self.config_path}[/green]    "
            f"Dry-run : [{'green' if self.dry_run else 'dim'}]{self.dry_run}[/]",
            border_style="blue",
        ))

    def _show_roadmap(self):
        """Display the full step roadmap grouped by phase with status."""
        current_phase = None
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold",
                      title="[bold]Migration Roadmap[/bold]", expand=True)
        table.add_column("#", style="bold", width=4, justify="right")
        table.add_column("Command", style="cyan", width=24)
        table.add_column("Description", ratio=1)
        table.add_column("Status", width=8, justify="center")

        for step in STEPS:
            if step["phase"] != current_phase:
                current_phase = step["phase"]
                phase_color = dict(PHASES).get(current_phase, "white")
                table.add_row("", f"[bold {phase_color}]── {current_phase} ──[/]", "", "",
                              style=f"bold {phase_color}")

            status = self.history.get(step["id"], "")
            if status == "OK":
                st = "[green]✔ OK[/]"
            elif status == "FAIL":
                st = "[red]✘ FAIL[/]"
            elif status == "SKIP":
                st = "[dim]— skip[/]"
            elif status == "RUNNING":
                st = "[bold yellow]⟳ RUN[/]"
            else:
                st = "[dim]…[/dim]"

            warn = " ⚠" if step.get("destructive") else ""
            table.add_row(step["id"], step["cmd"], step["name"] + warn, st)

        console.print(table)

    def _show_help_menu(self):
        console.print(Panel(
            "[bold]Available actions:[/bold]\n\n"
            "  [cyan]<number>[/]  — Run step by ID (e.g. [cyan]5[/], [cyan]11a[/], [cyan]P1[/], [cyan]U2[/])\n"
            "  [cyan]<command>[/] — Run by CLI name (e.g. [cyan]setup-pub[/], [cyan]init-replication[/])\n"
            "  [cyan]n[/]ext      — Run the next logical step\n"
            "  [cyan]m[/]ap       — Show the full roadmap\n"
            "  [cyan]s[/]tatus    — Detect live environment state\n"
            "  [cyan]c[/]onfig    — Configure database connections\n"
            "  [cyan]d[/]ry-run   — Toggle dry-run mode\n"
            "  [cyan]r[/]eport    — Generate HTML report from history\n"
            "  [cyan]h[/]elp      — Show this help\n"
            "  [cyan]q[/]uit      — Exit wizard\n",
            title="[bold]Wizard Help[/]", border_style="blue"
        ))

    # ── State Detection ────────────────────────────────────────────────────
    def _detect_state(self) -> dict:
        state = {"source": False, "dest": False, "publication": None,
                 "subscription": None, "sync_done": False, "repl_active": False,
                 "schema_pre": False, "schema_post": False}
        if not self.sc or not self.dc:
            return state
        try:
            with console.status("[bold green]Detecting environment state…"):
                conn = self.checker.check_connectivity()
                state["source"] = conn.get("source", False)
                state["dest"] = conn.get("dest", False)

                if state["source"]:
                    pub = self.cfg.get_replication().get('publication_name', 'migrator_pub')
                    res = self.sc.execute_query("SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete FROM pg_publication WHERE pubname = %s", (pub,))
                    if res:
                        r = res[0]
                        opts = []
                        if r.get('puballtables'): opts.append("all_tables")
                        if r.get('pubinsert'): opts.append("insert")
                        if r.get('pubupdate'): opts.append("update")
                        if r.get('pubdelete'): opts.append("delete")
                        state["publication"] = True
                        state["publication_name"] = r['pubname']
                        state["publication_opts"] = ", ".join(opts) if opts else ""
                    else:
                        state["publication"] = False
                        state["publication_name"] = None
                        state["publication_opts"] = ""

                if state["dest"]:
                    sub = self.cfg.get_replication().get('subscription_name', 'migrator_sub')
                    res = self.dc.execute_query("SELECT subname, subenabled, subbinary, substream FROM pg_subscription WHERE subname = %s", (sub,))
                    if res:
                        r = res[0]
                        opts = []
                        opts.append("enabled" if r.get("subenabled") else "disabled")
                        if r.get("subbinary"): opts.append("binary")
                        if r.get("substream") and r.get("substream") != 'f': opts.append(f"stream={r['substream']}")
                        state["subscription"] = True
                        state["subscription_name"] = r['subname']
                        state["subscription_opts"] = ", ".join(opts) if opts else ""
                    else:
                        state["subscription"] = False
                        state["subscription_name"] = None
                        state["subscription_opts"] = ""
                    filter_sys = "n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname !~ '^pg_toast'"
                    
                    q_pre = f"SELECT 1 FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid WHERE {filter_sys} AND c.relkind = 'r' LIMIT 1"
                    res = self.dc.execute_query(q_pre)
                    state["schema_pre"] = len(res) > 0 if res else False
                    
                    q_fk = f"SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON c.connamespace = n.oid WHERE {filter_sys} AND c.contype = 'f' LIMIT 1"
                    res_fk = self.dc.execute_query(q_fk)
                    
                    state["schema_post"] = False
                    if state["source"] and state["dest"]:
                        q_idx_count = f"SELECT count(*) as cnt FROM pg_index i JOIN pg_class c ON i.indrelid = c.oid JOIN pg_namespace n ON c.relnamespace = n.oid WHERE {filter_sys} AND not i.indisprimary AND not i.indisunique"
                        try:
                            src_idx = self.sc.execute_query(q_idx_count)
                            dst_idx = self.dc.execute_query(q_idx_count)
                            if src_idx and dst_idx:
                                s_cnt = src_idx[0]['cnt']
                                d_cnt = dst_idx[0]['cnt']
                                if s_cnt == d_cnt and s_cnt > 0:
                                    state["schema_post"] = True
                                elif s_cnt == 0 and res_fk:
                                    state["schema_post"] = True
                        except Exception:
                            pass
                    
                    if self.history.get("14") == "FAIL":
                        state["schema_post"] = False

                    if state["subscription"]:
                        res = self.dc.execute_query(
                            "SELECT count(*) as active FROM pg_stat_subscription WHERE subname = %s", (sub,))
                        state["repl_active"] = res[0]['active'] > 0 if res else False
                        try:
                            progress_res = self.migrator.get_initial_copy_progress()
                            if progress_res:
                                summary = progress_res.get('summary', {})
                                state["sync_stats"] = summary
                                if summary.get("total_tables", 0) > 0 and summary.get("completed_tables", 0) == summary.get("total_tables", 0):
                                    state["sync_done"] = True
                        except Exception:
                            pass
                            
                # Get replication lag from source
                if state["source"] and state["subscription"]:
                    try:
                        sub = self.cfg.get_replication().get('subscription_name', 'migrator_sub')
                        lag_query = "SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag_size FROM pg_replication_slots WHERE slot_name = %s"
                        res_lag = self.sc.execute_query(lag_query, (sub,))
                        if res_lag:
                            state["repl_lag"] = res_lag[0]["lag_size"]
                    except Exception:
                        pass
        except Exception as e:
            console.print(f"[yellow]State detection error: {e}[/yellow]")
        return state

    def _display_state(self, state: dict):
        table = Table(title="[bold]Live Environment State[/bold]", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Status")
        table.add_column("Details", style="dim")

        def _s(ok, label_ok, label_ko="Missing"):
            return f"[green]{label_ok}[/]" if ok else f"[yellow]{label_ko}[/]"

        # Connection details from dict (not URI string)
        src = self.cfg.get_source_dict() if self.cfg else {}
        dst = self.cfg.get_dest_dict() if self.cfg else {}
        src_detail = (f"{src.get('host', '?')}:{src.get('port', '5432')}  "
                      f"user={src.get('user', '?')}  db={src.get('database', '?')}")
        dst_detail = (f"{dst.get('host', '?')}:{dst.get('port', '5432')}  "
                      f"user={dst.get('user', '?')}  db={dst.get('database', '?')}")

        table.add_row("Configuration", "[green]Loaded[/green]", self.config_path)
        table.add_row("Source DB", _s(state["source"], "Connected", "Disconnected"), src_detail)
        table.add_row("Destination DB", _s(state["dest"], "Connected", "Disconnected"), dst_detail)
        
        pub_status = state.get("publication_name") or "Missing"
        table.add_row("Publication", _s(state["publication"], pub_status), state.get("publication_opts", ""))
        
        sub_status = state.get("subscription_name") or "Missing"
        table.add_row("Subscription", _s(state["subscription"], sub_status), state.get("subscription_opts", ""))
        
        lag_detail = f"Lag: {state.get('repl_lag', 'Unknown')}" if state["repl_active"] else ""
        table.add_row("Replication Active", _s(state["repl_active"], "Yes", "No"), lag_detail)
        
        sync_detail = ""
        if "sync_stats" in state:
            s = state["sync_stats"]
            sync_detail = f"{s.get('completed_tables', 0)}/{s.get('total_tables', 0)} tables ({s.get('percent_tables', 0)}%) | {s.get('bytes_copied_pretty', '0 B')}/{s.get('total_source_pretty', '0 B')} ({s.get('percent_bytes', 0)}%)"
        table.add_row("Initial Sync", _s(state["sync_done"], "Complete", "Pending / Not started"), sync_detail)
        
        table.add_row("Schema Pre-data", _s(state["schema_pre"], "Deployed", "Not deployed"), "")
        table.add_row("Schema Post-data", _s(state["schema_post"], "Deployed", "Not deployed"), "")
        console.print(table)

    def _update_history_from_state(self, state: dict):
        """Auto-populate the roadmap for the first 6 steps based on live state."""
        if state.get("source") and state.get("dest"):
            self.history.setdefault("1", "OK")
            self.history.setdefault("2", "OK")
            self.history.setdefault("3", "OK")
            
        if state.get("schema_pre"):
            self.history.setdefault("4", "OK")
            
        if state.get("publication"):
            self.history.setdefault("5", "OK")
            
        if state.get("subscription"):
            self.history.setdefault("6", "OK")
            
        if state.get("sync_done"):
            self.history.setdefault("7", "OK")

        if state.get("schema_post"):
            # Step 10 terminates replication and deploys schema post-data.
            # If schema_post is deployed, step 10 is very likely completed.
            self.history.setdefault("10", "OK")
            # Step 16 cleans up subscription and publication.
            # If schema_post is true and they are missing, step 16 is completed.
            if not state.get("subscription") and not state.get("publication"):
                self.history.setdefault("16", "OK")


    # ── Next Step Logic ────────────────────────────────────────────────────
    def _get_next_step(self, state: dict):
        """Find the first migration step (1-17) not yet completed."""
        migration_ids = [s["id"] for s in STEPS if not s["id"].startswith(("U", "P"))]
        for sid in migration_ids:
            if sid not in self.history:
                return ID_TO_STEP[sid]
        return None

    # ── Step Execution ─────────────────────────────────────────────────────
    def _build_args(self, **extra):
        return argparse.Namespace(
            config=self.config_path, database=self.database,
            results_dir=self.results_dir, loglevel="INFO",
            dry_run=self.dry_run, verbose=False, use_stats=False,
            sync_delay=3600, drop_dest=False, wait=True,
            owner=None, output="config_migrator.sample.ini",
            log_file=None, **extra
        )

    def _run_step_by_id(self, step_id: str):
        step = ID_TO_STEP.get(step_id)
        if not step:
            console.print(f"[red]Unknown step ID: {step_id}[/red]")
            return
        self._execute_step(step)

    def _execute_step(self, step: dict):
        console.print(f"\n[bold blue]━━━ Step {step['id']}: {step['name']} ━━━[/bold blue]")
        console.print(f"[dim]{step['desc']}[/dim]")

        if step.get("destructive") and step.get("warn"):
            console.print(f"[bold yellow]⚠  {step['warn']}[/bold yellow]")

        if self.dry_run:
            console.print(f"[dim][DRY-RUN] Would execute: {step['cmd']}[/dim]")
            self.history[step["id"]] = "SKIP"
            return

        # Skip confirmation for purely informational utilities and read-only checks
        if step["cmd"] in ("repl-progress", "check", "diagnose", "params", "audit-objects", "stop-repl", "start-repl"):
            pass  # Run immediately without asking
        else:
            if not Confirm.ask(f"Execute [cyan]{step['cmd']}[/cyan]?", default=True):
                self.history[step["id"]] = "SKIP"
                return

        # Run dispatch in a thread so blocking operations don't lock the prompt
        result = {"rc": None, "error": None}

        def _worker():
            try:
                result["rc"] = self._dispatch(step)
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        poll_interval = 5  # seconds between status polls
        elapsed = 0.0

        try:
            while t.is_alive():
                t.join(timeout=0.5)
                elapsed += 0.5
                # Show live replication status every poll_interval seconds
                if t.is_alive() and elapsed >= poll_interval:
                    elapsed = 0.0
                    self._show_repl_status_inline()
        except KeyboardInterrupt:
            self.history[step["id"]] = "RUNNING"
            console.print(f"\n[yellow]⏎ Step {step['id']} is still running in background. "
                          f"Use [cyan]s[/cyan] to check state later.[/yellow]")
            return

        if result["error"]:
            self.history[step["id"]] = "FAIL"
            console.print(f"[bold red]Error: {result['error']}[/bold red]")
            logging.error(f"Wizard step {step['id']} error: {result['error']}", exc_info=True)
        else:
            rc = result["rc"] or 0
            status = "OK" if rc == 0 else "FAIL"
            self.history[step["id"]] = status
            color = "green" if rc == 0 else "red"
            console.print(f"[{color}]Step {step['id']} → {status}[/{color}]")

    def _show_repl_status_inline(self):
        """Display a rich replication progress table while waiting."""
        if not self.dc or not self.migrator:
            return
        try:
            sub_name = self.cfg.get_replication().get('subscription_name', 'migrator_sub')

            # Try to get detailed per-table progress (same as CLI cmd_progress)
            progress = None
            try:
                progress = self.migrator.get_initial_copy_progress()
            except Exception:
                pass

            if progress and progress.get('tables'):
                from src.db import pretty_size
                summary = progress["summary"]
                tables = progress["tables"]

                # Summary line
                pct_bytes = summary.get('percent_bytes', 0)
                pct_tables = summary.get('percent_tables', 0)
                completed = summary.get('completed_tables', 0)
                total_t = summary.get('total_tables', 0)
                copied_pretty = summary.get('bytes_copied_pretty', '0 B')
                total_pretty = summary.get('total_source_pretty', '0 B')

                console.print(
                    f"  [bold cyan]📊 Sync Progress[/bold cyan]: "
                    f"[bold]{pct_bytes}%[/bold] bytes ({copied_pretty}/{total_pretty})  "
                    f"Tables: [bold]{completed}/{total_t}[/bold] ready ({pct_tables}%)"
                )

                # Per-table table (compact, max 15 rows)
                state_labels = {'i': '⏳ init', 'd': '📥 copy', 'f': '🔄 finalize',
                                's': '🔁 sync', 'r': '✅ ready'}
                table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1),
                              header_style="bold dim", expand=False)
                table.add_column("Table", style="cyan", max_width=40)
                table.add_column("State", width=12)
                table.add_column("Progress", justify="right", width=22)
                table.add_column("%", justify="right", width=5)

                for t in tables[:15]:
                    st = t.get('state', '?')
                    state_str = state_labels.get(st, st)
                    if st == 'r':
                        color = "green"
                    elif st == 'd':
                        color = "bold blue"
                    else:
                        color = "yellow"
                    try:
                        prog_str = f"{pretty_size(t['bytes_copied'])} / {pretty_size(t['size_source'])}"
                    except Exception:
                        prog_str = "—"
                    table.add_row(
                        str(t.get('table_name', '?')),
                        f"[{color}]{state_str}[/{color}]",
                        prog_str,
                        f"{t.get('percent', 0)}%"
                    )

                if len(tables) > 15:
                    table.add_row(f"… +{len(tables) - 15} more", "", "", "")

                console.print(table)
            else:
                # Fallback: basic subscription info
                sub_rows = self.dc.execute_query(
                    "SELECT subname, subenabled FROM pg_subscription WHERE subname = %s",
                    (sub_name,)
                )
                if not sub_rows:
                    console.print("  [dim]⏳ Subscription not yet created…[/dim]")
                    return

                enabled = sub_rows[0].get('subenabled', False)
                rel_rows = self.dc.execute_query(
                    "SELECT srsubstate, count(*) as cnt "
                    "FROM pg_subscription_rel sr "
                    "JOIN pg_subscription s ON s.oid = sr.srsubid "
                    "WHERE s.subname = %s GROUP BY srsubstate",
                    (sub_name,)
                )
                state_map = {'i': 'init', 'd': 'copy', 'f': 'finalize',
                             's': 'sync', 'r': 'ready'}
                parts = []
                for r in (rel_rows or []):
                    st = r.get('srsubstate', '?')
                    cnt = r.get('cnt', 0)
                    parts.append(f"{state_map.get(st, st)}={cnt}")
                state_str = " | ".join(parts) if parts else "no tables"
                en_str = "enabled" if enabled else "disabled"
                console.print(f"  [dim][repl-status] sub={sub_name} [{en_str}] tables: {state_str}[/dim]")

            console.print("  [dim italic](Ctrl+C → return to prompt)[/dim]")
        except Exception:
            pass

    def _dispatch(self, step: dict) -> int:
        cmd = step["cmd"]
        args = self._build_args()

        # Steps that need special args
        if cmd == "migrate-schema-pre-data":
            drop = Confirm.ask("Drop destination DB first? (--drop-dest)", default=False)
            args.drop_dest = drop
        elif cmd == "migrate-schema-post-data":
            args.drop_dest = False

        if cmd == "reassign-owner":
            owner = Prompt.ask("Target owner role", default=self.cfg.get_dest_dict().get('user', 'postgres'))
            args.owner = owner

        if cmd == "generate-config":
            out = Prompt.ask("Output path", default="config_migrator.sample.ini")
            args.output = out

        if cmd == "init-replication":
            args.drop_dest = Confirm.ask("Drop destination first?", default=False)
            args.wait = Confirm.ask("Wait for initial sync?", default=True)

        # Import and dispatch to the real command function
        if cmd in ("init-replication", "post-migration"):
            from src.cli.pipelines import cmd_init_replication, cmd_post_migration
            func = cmd_init_replication if cmd == "init-replication" else cmd_post_migration
            return func(args)

        from src.cli.commands import (
            cmd_check, cmd_diagnose, cmd_params,
            cmd_migrate_schema_pre_data, cmd_terminate_replication, cmd_migrate_schema_post_data,
            cmd_setup_pub, cmd_setup_sub, cmd_progress, cmd_wait_sync,
            cmd_sync_sequences, cmd_enable_triggers, cmd_refresh_matviews,
            cmd_reassign_owner, cmd_audit_objects,
            cmd_validate_rows, cmd_cleanup, cmd_setup_reverse, cmd_cleanup_reverse,
            cmd_sync_lobs, cmd_sync_unlogged, cmd_generate_config,
            cmd_stop_repl, cmd_start_repl
        )

        dispatch_map = {
            "check": cmd_check, "diagnose": cmd_diagnose, "params": cmd_params,
            "migrate-schema-pre-data": cmd_migrate_schema_pre_data,
            "migrate-schema-post-data": cmd_migrate_schema_post_data,
            "setup-pub": cmd_setup_pub, "setup-sub": cmd_setup_sub,
            "repl-progress": cmd_progress,
            "refresh-matviews": cmd_refresh_matviews,
            "sync-sequences": cmd_sync_sequences,
            "terminate-repl": cmd_terminate_replication,
            "sync-lobs": cmd_sync_lobs, "sync-unlogged": cmd_sync_unlogged,
            "enable-triggers": cmd_enable_triggers,
            "reassign-owner": cmd_reassign_owner,
            "audit-objects": cmd_audit_objects, "validate-rows": cmd_validate_rows,
            "cleanup": cmd_cleanup, "setup-reverse": cmd_setup_reverse,
            "wait-sync": cmd_wait_sync, "cleanup-reverse": cmd_cleanup_reverse,
            "generate-config": cmd_generate_config,
            "stop-repl": cmd_stop_repl, "start-repl": cmd_start_repl,
        }

        func = dispatch_map.get(cmd)
        if not func:
            console.print(f"[red]No handler for '{cmd}'[/red]")
            return 1
        return func(args) or 0

    def _run_generate_config(self):
        from src.cli.helpers import generate_sample_config
        out = Prompt.ask("Output path", default=self.config_path)
        generate_sample_config(out)
        self.config_path = out
        console.print(f"[green]Config written to {out}[/green]")

    # ── Config Editor ──────────────────────────────────────────────────────
    def _menu_configure(self):
        console.print(Panel("[bold]Configuration Assistant[/bold]", border_style="cyan"))

        if not os.path.exists(self.config_path):
            if Confirm.ask("No config found. Generate one?", default=True):
                self._run_generate_config()
            self.cfg = Config(self.config_path, self.database)

        if Confirm.ask("Configure Source?", default=True):
            self._prompt_section("source", "Source")
        if Confirm.ask("Configure Destination?", default=True):
            self._prompt_section("destination", "Destination")
        if Confirm.ask("Configure Replication?", default=True):
            existing = self.cfg.get_replication()
            data = {}
            data['target_schema'] = Prompt.ask("Target schema(s)", default=existing.get('target_schema', 'public'))
            data['publication_name'] = Prompt.ask("Publication name", default=existing.get('publication_name', 'migrator_pub'))
            data['subscription_name'] = Prompt.ask("Subscription name", default=existing.get('subscription_name', 'migrator_sub'))
            self.cfg.update_section("replication", data)

        if Confirm.ask(f"Save to {self.config_path}?", default=True):
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            self.cfg.save()
            console.print("[green]Configuration saved.[/green]")
            self._init_clients()

    def _prompt_section(self, section, label):
        getter = self.cfg.get_source_dict if section == "source" else self.cfg.get_dest_dict
        try:
            existing = getter()
        except Exception:
            existing = {}
        data = {}
        data['host'] = Prompt.ask(f"{label} host", default=existing.get('host', 'localhost'))
        data['port'] = Prompt.ask(f"{label} port", default=existing.get('port', '5432'))
        data['user'] = Prompt.ask(f"{label} user", default=existing.get('user', 'postgres'))
        data['password'] = Prompt.ask(f"{label} password", password=True, default=existing.get('password', ''))
        data['database'] = Prompt.ask(f"{label} database", default=existing.get('database', 'postgres'))
        self.cfg.update_section(section, data)

    # ── Report ─────────────────────────────────────────────────────────────
    def _generate_report(self):
        for sid, status in self.history.items():
            step = ID_TO_STEP.get(sid, {})
            self.reporter.add_step(sid, step.get("name", sid), status, step.get("desc", ""))
        path = os.path.join(self.results_dir, "report_wizard.html")
        out = self.reporter.generate_html(path)
        console.print(f"[green]Report generated: {out}[/green]")

    # ── Resolve Input ──────────────────────────────────────────────────────
    def _resolve_input(self, raw: str) -> Optional[dict]:
        raw = raw.strip()
        # Direct ID match
        if raw.upper() in ID_TO_STEP:
            return ID_TO_STEP[raw.upper()]
        if raw in ID_TO_STEP:
            return ID_TO_STEP[raw]
        # Command name match
        if raw in CMD_TO_STEP:
            return CMD_TO_STEP[raw]
        return None

    # ── Readline Setup ─────────────────────────────────────────────────────
    def _setup_readline(self):
        """Configure readline with history and tab-completion."""
        # Build completion word list: actions + step IDs + command names
        self._completions = (
            ["next", "map", "status", "config", "dry-run", "report", "help", "quit"]
            + [s["id"] for s in STEPS]
            + [s["id"].lower() for s in STEPS]
            + [s["cmd"] for s in STEPS]
        )
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for w in self._completions:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        self._completions = unique

        def completer(text, state):
            matches = [w for w in self._completions if w.startswith(text.lower())]
            return matches[state] if state < len(matches) else None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" ")

        # Persistent history file
        self._history_file = os.path.join(
            os.path.expanduser("~"), ".pg_migrator_wizard_history"
        )
        try:
            readline.read_history_file(self._history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(500)

    def _save_readline_history(self):
        try:
            readline.write_history_file(self._history_file)
        except Exception:
            pass

    # ── Main Loop ──────────────────────────────────────────────────────────
    def run(self):
        self._init_config()
        self._select_database()
        self._init_clients()
        self._setup_readline()

        self._banner()
        self._show_roadmap()
        self._show_help_menu()
        
        # Automatically show status on load
        try:
            state = self._detect_state()
            self._update_history_from_state(state)
            self._display_state(state)
        except Exception as e:
            console.print(f"[dim yellow]Could not auto-detect state: {e}[/dim yellow]")

        while True:
            try:
                raw = input("\n\033[1;33mwizard>\033[0m ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not raw:
                raw = "n"

            if raw in ("q", "quit", "exit"):
                if self.history:
                    if Confirm.ask("Generate HTML report before leaving?", default=True):
                        self._generate_report()
                self._save_readline_history()
                console.print("[dim]Goodbye.[/dim]")
                break

            elif raw in ("n", "next"):
                state = self._detect_state()
                step = self._get_next_step(state)
                if step:
                    self._execute_step(step)
                else:
                    console.print("[green]All 17 migration steps completed![/green]")

            elif raw in ("m", "map", "roadmap"):
                self._show_roadmap()

            elif raw in ("s", "status"):
                state = self._detect_state()
                self._update_history_from_state(state)
                self._display_state(state)

            elif raw in ("c", "config"):
                self._menu_configure()

            elif raw in ("d", "dry-run", "dry"):
                self.dry_run = not self.dry_run
                console.print(f"Dry-run mode: [bold]{'ON' if self.dry_run else 'OFF'}[/bold]")

            elif raw in ("r", "report"):
                self._generate_report()

            elif raw in ("h", "help", "?"):
                self._show_help_menu()

            else:
                step = self._resolve_input(raw)
                if step:
                    self._execute_step(step)
                else:
                    console.print(f"[red]Unknown command: '{raw}'. Type 'h' for help.[/red]")

        self._save_readline_history()


def cmd_wizard(args):
    wizard = MigrationWizard(args.config, getattr(args, "database", None))
    wizard.run()
    return 0
