import os
import logging
import argparse
import threading
import readline
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt, Confirm

from src.config import Config
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator
from src.cli.helpers import build_clients, setup_results_dir, generate_sample_config
from src.cli.pipelines import cmd_init_replication, cmd_post_migration
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
from src.db import pretty_size

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



class WizardModel:
    def __init__(self, config_path: str, database: Optional[str] = None):
        self.config_path = config_path
        self.database = database
        self.dry_run = False
        self.history: Dict[str, str] = {}
        self.cfg: Optional[Config] = None
        self.sc: Optional[Any] = None
        self.dc: Optional[Any] = None
        self.checker: Optional[DBChecker] = None
        self.migrator: Optional[Migrator] = None
        self.post_sync: Optional[PostSync] = None
        self.validator: Optional[Validator] = None
        self.reporter = ReportGenerator()
        self.results_dir = setup_results_dir()

    def init_config(self) -> bool:
        if not os.path.exists(self.config_path):
            return False
        self.cfg = Config(self.config_path, self.database)
        if self.database:
            self.cfg.set_override_db(self.database)
        return True

    def generate_default_config(self, out_path: str):
        generate_sample_config(out_path)
        self.config_path = out_path

    def init_clients(self) -> bool:
        if not self.cfg:
            return False
        try:
            self.sc, self.dc = build_clients(self.cfg)
            self.checker = DBChecker(self.sc, self.dc, self.cfg)
            self.migrator = Migrator(self.cfg)
            self.post_sync = PostSync(self.sc, self.dc, self.cfg)
            self.validator = Validator(self.sc, self.dc, self.cfg)
            return True
        except Exception as e:
            logging.error(f"Could not connect: {e}")
            return False

    def detect_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {"source": False, "dest": False, "publication": None,
                 "subscription": None, "sync_done": False, "repl_active": False,
                 "schema_pre": False, "schema_post": False}
        if not self.sc or not self.dc or not self.checker or not self.cfg or not self.migrator:
            return state
        try:
            conn = self.checker.check_connectivity()
            state["source"] = conn.get("source", False)
            state["dest"] = conn.get("dest", False)

            if state["source"]:
                pub = self.cfg.get_replication().get('publication_name', 'migrator_pub')
                res = self.sc.execute_query("SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete FROM pg_publication WHERE pubname = %s", (pub,))
                if res:
                    r = res[0]
                    opts = []
                    if r.get('puballtables'):
                        opts.append("all_tables")
                    if r.get('pubinsert'):
                        opts.append("insert")
                    if r.get('pubupdate'):
                        opts.append("update")
                    if r.get('pubdelete'):
                        opts.append("delete")
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
                    if r.get("subbinary"):
                        opts.append("binary")
                    if r.get("substream") and r.get("substream") != 'f':
                        opts.append(f"stream={r['substream']}")
                    state["subscription"] = True
                    state["subscription_name"] = r['subname']
                    state["subscription_opts"] = ", ".join(opts) if opts else ""
                else:
                    state["subscription"] = False
                    state["subscription_name"] = None
                    state["subscription_opts"] = ""
                filter_sys = "n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname !~ '^pg_toast'"
                
                state["schema_pre"] = False
                if state["source"] and state["dest"]:
                    q_pre = f"SELECT count(*) as cnt FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid WHERE {filter_sys} AND c.relkind IN ('r', 'v', 'S')"
                    try:
                        src_pre = self.sc.execute_query(q_pre)
                        dst_pre = self.dc.execute_query(q_pre)
                        if src_pre and dst_pre:
                            s_cnt = src_pre[0]['cnt']
                            d_cnt = dst_pre[0]['cnt']
                            if s_cnt == d_cnt and s_cnt > 0:
                                state["schema_pre"] = True
                            elif s_cnt == 0:
                                state["schema_pre"] = True
                    except Exception:
                        pass
                
                state["schema_post"] = False
                if state["source"] and state["dest"]:
                    q_idx_count = f"SELECT count(*) as cnt FROM pg_index i JOIN pg_class c ON i.indrelid = c.oid JOIN pg_namespace n ON c.relnamespace = n.oid WHERE {filter_sys} AND not i.indisprimary AND not i.indisunique"
                    q_fk_count = f"SELECT count(*) as cnt FROM pg_constraint c JOIN pg_namespace n ON c.connamespace = n.oid WHERE {filter_sys} AND c.contype IN ('f', 'c')"
                    try:
                        src_idx = self.sc.execute_query(q_idx_count)
                        dst_idx = self.dc.execute_query(q_idx_count)
                        src_fk = self.sc.execute_query(q_fk_count)
                        dst_fk = self.dc.execute_query(q_fk_count)
                        if src_idx and dst_idx and src_fk and dst_fk:
                            s_idx_cnt = src_idx[0]['cnt']
                            d_idx_cnt = dst_idx[0]['cnt']
                            s_fk_cnt = src_fk[0]['cnt']
                            d_fk_cnt = dst_fk[0]['cnt']
                            
                            if s_idx_cnt == d_idx_cnt and s_fk_cnt == d_fk_cnt and (s_idx_cnt > 0 or s_fk_cnt > 0):
                                state["schema_post"] = True
                            elif s_idx_cnt == 0 and s_fk_cnt == 0:
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
            logging.error(f"State detection error: {e}")
        return state

    def update_history_from_state(self, state: dict):
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
            self.history.setdefault("10", "OK")
            if not state.get("subscription") and not state.get("publication"):
                self.history.setdefault("16", "OK")

    def get_next_step(self, state: dict):
        migration_ids = [s["id"] for s in STEPS if isinstance(s["id"], str) and not s["id"].startswith(("U", "P"))]
        for sid in migration_ids:
            if sid not in self.history:
                return ID_TO_STEP[sid]
        return None

    def generate_report(self):
        for sid, status in self.history.items():
            step = ID_TO_STEP.get(sid, {})
            self.reporter.add_step(sid, step.get("name", sid), status, step.get("desc", ""))
        path = os.path.join(self.results_dir, "report_wizard.html")
        return self.reporter.generate_html(path)

class WizardView:
    def __init__(self):
        self.console = Console()

    def show_banner(self, database, config_path, dry_run):
        self.console.clear()
        self.console.print(Panel.fit(
            "[bold cyan]╔═══════════════════════════════════════════════╗\n"
            "║   PostgreSQL Logical Migrator — Wizard Mode   ║\n"
            "╚═══════════════════════════════════════════════╝[/bold cyan]\n"
            f"  Database : [green]{database or '—'}[/green]    "
            f"Config : [green]{config_path}[/green]    "
            f"Dry-run : [{'green' if dry_run else 'dim'}]{dry_run}[/]",
            border_style="blue",
        ))

    def show_roadmap(self, history):
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

            status = history.get(step["id"], "")
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

        self.console.print(table)

    def show_help_menu(self):
        self.console.print(Panel(
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

    def display_state(self, state: dict, cfg, config_path):
        table = Table(title="[bold]Live Environment State[/bold]", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Status")
        table.add_column("Details", style="dim")

        def _s(ok, label_ok, label_ko="Missing"):
            return f"[green]{label_ok}[/]" if ok else f"[yellow]{label_ko}[/]"

        src = cfg.get_source_dict() if cfg else {}
        dst = cfg.get_dest_dict() if cfg else {}
        src_detail = (f"{src.get('host')}:{src.get('port')}  "
                      f"user={src.get('user')}  db={src.get('database')}") if src else ""
        dst_detail = (f"{dst.get('host')}:{dst.get('port')}  "
                      f"user={dst.get('user')}  db={dst.get('database')}") if dst else ""

        table.add_row("Configuration", "[green]Loaded[/green]", config_path)
        table.add_row("Source DB", _s(state.get("source"), "Connected", "Disconnected"), src_detail)
        table.add_row("Destination DB", _s(state.get("dest"), "Connected", "Disconnected"), dst_detail)
        
        pub_status = state.get("publication_name") or "Missing"
        table.add_row("Publication", _s(state.get("publication"), pub_status), state.get("publication_opts", ""))
        
        sub_status = state.get("subscription_name") or "Missing"
        table.add_row("Subscription", _s(state.get("subscription"), sub_status), state.get("subscription_opts", ""))
        
        lag_detail = f"Lag: {state.get('repl_lag', 'Unknown')}" if state.get("repl_active") else ""
        table.add_row("Replication Active", _s(state.get("repl_active"), "Yes", "No"), lag_detail)
        
        sync_detail = ""
        if "sync_stats" in state:
            s = state["sync_stats"]
            sync_detail = f"{s.get('completed_tables', 0)}/{s.get('total_tables', 0)} tables ({s.get('percent_tables', 0)}%) | {s.get('bytes_copied_pretty', '0 B')}/{s.get('total_source_pretty', '0 B')} ({s.get('percent_bytes', 0)}%)"
        table.add_row("Initial Sync", _s(state.get("sync_done"), "Complete", "Pending / Not started"), sync_detail)
        
        table.add_row("Schema Pre-data", _s(state.get("schema_pre"), "Deployed", "Not deployed"), "")
        table.add_row("Schema Post-data", _s(state.get("schema_post"), "Deployed", "Not deployed"), "")
        self.console.print(table)

    def show_repl_status_inline(self, progress, sub_info_str=None):
        if progress and progress.get('tables'):
            summary = progress["summary"]
            tables = progress["tables"]

            pct_bytes = summary.get('percent_bytes', 0)
            pct_tables = summary.get('percent_tables', 0)
            completed = summary.get('completed_tables', 0)
            total_t = summary.get('total_tables', 0)
            copied_pretty = summary.get('bytes_copied_pretty', '0 B')
            total_pretty = summary.get('total_source_pretty', '0 B')

            self.console.print(
                f"  [bold cyan]📊 Sync Progress[/bold cyan]: "
                f"[bold]{pct_bytes}%[/bold] bytes ({copied_pretty}/{total_pretty})  "
                f"Tables: [bold]{completed}/{total_t}[/bold] ready ({pct_tables}%)"
            )

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
                table.add_row(str(t.get('table_name', '?')), f"[{color}]{state_str}[/{color}]", prog_str, f"{t.get('percent', 0)}%")

            if len(tables) > 15:
                table.add_row(f"… +{len(tables) - 15} more", "", "", "")

            self.console.print(table)
        elif sub_info_str:
            self.console.print(sub_info_str)
        else:
            self.console.print("  [dim]⏳ Subscription not yet created…[/dim]")
            
        self.console.print("  [dim italic](Ctrl+C → return to prompt)[/]")


class MigrationWizard:
    def __init__(self, config_path: str, database: Optional[str] = None):
        self.model = WizardModel(config_path, database)
        self.view = WizardView()

    def run(self):
        if not self.model.init_config():
            self.view.console.print(f"[yellow]Config file '{self.model.config_path}' not found.[/yellow]")
            if Confirm.ask("Generate a default configuration file?", default=True):
                out = Prompt.ask("Output path", default=self.model.config_path)
                self.model.generate_default_config(out)
                self.view.console.print(f"[green]Config written to {out}[/green]")
                self.model.init_config()
                
        self._select_database()
        if not self.model.init_clients():
            self.view.console.print("[yellow]Could not connect clients.[/yellow]")
            
        self._setup_readline()
        self.view.show_banner(self.model.database, self.model.config_path, self.model.dry_run)
        self.view.show_roadmap(self.model.history)
        self.view.show_help_menu()
        
        with self.view.console.status("[bold green]Detecting environment state…"):
            state = self.model.detect_state()
            self.model.update_history_from_state(state)
        self.view.display_state(state, self.model.cfg, self.model.config_path)

        while True:
            try:
                raw = input("\n\033[1;33mwizard>\033[0m ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not raw:
                raw = "n"

            if raw in ("q", "quit", "exit"):
                if self.model.history:
                    if Confirm.ask("Generate HTML report before leaving?", default=True):
                        self._generate_report()
                self._save_readline_history()
                self.view.console.print("[dim]Goodbye.[/dim]")
                break

            elif raw in ("n", "next"):
                state = self.model.detect_state()
                step = self.model.get_next_step(state)
                if step:
                    self._execute_step(step)
                else:
                    self.view.console.print("[green]All 17 migration steps completed![/green]")

            elif raw in ("m", "map", "roadmap"):
                self.view.show_roadmap(self.model.history)

            elif raw in ("s", "status"):
                with self.view.console.status("[bold green]Detecting environment state…"):
                    state = self.model.detect_state()
                    self.model.update_history_from_state(state)
                self.view.display_state(state, self.model.cfg, self.model.config_path)

            elif raw in ("c", "config"):
                self._menu_configure()

            elif raw in ("d", "dry-run", "dry"):
                self.model.dry_run = not self.model.dry_run
                self.view.console.print(f"Dry-run mode: [bold]{'ON' if self.model.dry_run else 'OFF'}[/bold]")

            elif raw in ("r", "report"):
                self._generate_report()

            elif raw in ("h", "help", "?"):
                self.view.show_help_menu()

            else:
                step = self._resolve_input(raw)
                if step:
                    self._execute_step(step)
                else:
                    self.view.console.print(f"[red]Unknown command: '{raw}'. Type 'h' for help.[/red]")

        self._save_readline_history()

    def _select_database(self):
        if self.model.database:
            return
        try:
            dbs = self.model.cfg.get_databases()
        except Exception:
            dbs = []
        if not dbs:
            self.model.database = Prompt.ask("Database name", default="postgres")
        elif len(dbs) == 1:
            self.model.database = dbs[0]
        else:
            self.view.console.print("[bold]Available databases:[/bold]")
            for i, d in enumerate(dbs, 1):
                self.view.console.print(f"  {i}. {d}")
            while True:
                choice = Prompt.ask("Select database (name or number)", default="1")
                if choice.isdigit() and 1 <= int(choice) <= len(dbs):
                    self.model.database = dbs[int(choice) - 1]
                    break
                elif choice in dbs:
                    self.model.database = choice
                    break
                else:
                    self.view.console.print(f"[red]Unknown database '{choice}'. Use a number or exact name.[/red]")
        self.model.cfg.set_override_db(self.model.database)

    def _menu_configure(self):
        self.view.console.print(Panel("[bold]Configuration Assistant[/bold]", border_style="cyan"))
        if not os.path.exists(self.model.config_path):
            if Confirm.ask("No config found. Generate one?", default=True):
                out = Prompt.ask("Output path", default=self.model.config_path)
                self.model.generate_default_config(out)
                self.view.console.print(f"[green]Config written to {out}[/green]")
            self.model.init_config()

        def _prompt_section(section, label):
            getter = self.model.cfg.get_source_dict if section == "source" else self.model.cfg.get_dest_dict
            try:
                existing = getter()
            except Exception:
                existing = {}
            data = {}
            data['host'] = Prompt.ask(f"{label} host", default=existing.get('host', ''))
            data['port'] = Prompt.ask(f"{label} port", default=str(existing.get('port', 5432)))
            data['user'] = Prompt.ask(f"{label} user", default=existing.get('user', 'postgres'))
            data['password'] = Prompt.ask(f"{label} password", password=True, default=existing.get('password', ''))
            data['database'] = Prompt.ask(f"{label} database", default=existing.get('database', ''))
            self.model.cfg.update_section(section, data)

        if Confirm.ask("Configure Source?", default=True):
            _prompt_section("source", "Source")
        if Confirm.ask("Configure Destination?", default=True):
            _prompt_section("destination", "Destination")
        if Confirm.ask("Configure Replication?", default=True):
            existing = self.model.cfg.get_replication()
            data = {}
            data['target_schema'] = Prompt.ask("Target schema(s)", default=existing.get('target_schema', 'public'))
            data['publication_name'] = Prompt.ask("Publication name", default=existing.get('publication_name', 'migrator_pub'))
            data['subscription_name'] = Prompt.ask("Subscription name", default=existing.get('subscription_name', 'migrator_sub'))
            self.model.cfg.update_section("replication", data)

        if Confirm.ask(f"Save to {self.model.config_path}?", default=True):
            os.makedirs(os.path.dirname(os.path.abspath(self.model.config_path)), exist_ok=True)
            self.model.cfg.save()
            self.view.console.print("[green]Configuration saved.[/green]")
            self.model.init_clients()

    def _build_args(self, **extra):
        return argparse.Namespace(
            config=self.model.config_path, database=self.model.database,
            results_dir=self.model.results_dir, loglevel="INFO",
            dry_run=self.model.dry_run, verbose=False, use_stats=False,
            sync_delay=3600, drop_dest=False, wait=True,
            owner=None, output="config_migrator.sample.ini",
            log_file=None, **extra
        )

    def _execute_step(self, step: dict):
        self.view.console.print(f"\n[bold blue]━━━ Step {step['id']}: {step['name']} ━━━[/bold blue]")
        self.view.console.print(f"[dim]{step['desc']}[/dim]")

        if step.get("destructive") and step.get("warn"):
            self.view.console.print(f"[bold yellow]⚠  {step['warn']}[/bold yellow]")

        if self.model.dry_run:
            self.view.console.print(f"[dim][DRY-RUN] Would execute: {step['cmd']}[/dim]")
            self.model.history[step["id"]] = "SKIP"
            return

        if step["cmd"] not in ("repl-progress", "check", "diagnose", "params", "audit-objects", "stop-repl", "start-repl"):
            if not Confirm.ask(f"Execute [cyan]{step['cmd']}[/cyan]?", default=True):
                self.model.history[step["id"]] = "SKIP"
                return

        args = self._prepare_args(step)
        if args is None:
            self.model.history[step["id"]] = "SKIP"
            return

        result = {"rc": None, "error": None}
        def _worker():
            try:
                result["rc"] = self._dispatch(step, args)
            except Exception:
                import traceback
                result["error"] = traceback.format_exc()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        poll_interval = 5
        elapsed = 0.0
        try:
            while t.is_alive():
                t.join(timeout=0.5)
                elapsed += 0.5
                if t.is_alive() and elapsed >= poll_interval:
                    elapsed = 0.0
                    self._show_repl_status_polling()
        except KeyboardInterrupt:
            self.model.history[step["id"]] = "RUNNING"
            self.view.console.print(f"\n[yellow]⏎ Step {step['id']} is still running in background. Use [cyan]s[/cyan] to check state later.[/yellow]")
            return

        if result["error"]:
            self.model.history[step["id"]] = "FAIL"
            self.view.console.print(f"[bold red]Error: {result['error']}[/bold red]")
            logging.error(f"Wizard step {step['id']} error: {result['error']}", exc_info=True)
        else:
            rc = result["rc"] or 0
            status = "OK" if rc == 0 else "FAIL"
            self.model.history[step["id"]] = status
            color = "green" if rc == 0 else "red"
            self.view.console.print(f"[{color}]Step {step['id']} → {status}[/{color}]")

    def _show_repl_status_polling(self):
        progress = None
        try:
            progress = self.model.get_initial_copy_progress()
        except Exception:
            pass
        
        sub_info_str = None
        if not progress and self.model.dc:
            try:
                sub_name = self.model.cfg.get_replication().get('subscription_name', 'migrator_sub')
                sub_rows = self.model.dc.execute_query("SELECT subname, subenabled FROM pg_subscription WHERE subname = %s", (sub_name,))
                if sub_rows:
                    enabled = sub_rows[0].get('subenabled', False)
                    rel_rows = self.model.dc.execute_query(
                        "SELECT srsubstate, count(*) as cnt FROM pg_subscription_rel sr JOIN pg_subscription s ON s.oid = sr.srsubid WHERE s.subname = %s GROUP BY srsubstate", (sub_name,))
                    state_map = {'i': 'init', 'd': 'copy', 'f': 'finalize', 's': 'sync', 'r': 'ready'}
                    parts = [f"{state_map.get(r.get('srsubstate', '?'), r.get('srsubstate', '?'))}={r.get('cnt', 0)}" for r in (rel_rows or [])]
                    state_str = " | ".join(parts) if parts else "no tables"
                    en_str = "enabled" if enabled else "disabled"
                    sub_info_str = f"  [dim][repl-status] sub={sub_name} [{en_str}] tables: {state_str}[/dim]"
            except Exception as e:
                sub_info_str = f"  [dim][repl-status] Status unavailable: {type(e).__name__}[/dim]"

        self.view.show_repl_status_inline(progress, sub_info_str)

    def _prepare_args(self, step: dict):
        cmd = step["cmd"]
        args = self._build_args()

        try:
            if cmd == "migrate-schema-pre-data":
                args.drop_dest = Confirm.ask("Drop destination DB first? (--drop-dest)", default=False)
            elif cmd == "migrate-schema-post-data":
                args.drop_dest = False
            elif cmd == "reassign-owner":
                default_user = "postgres"
                if self.model.cfg:
                    default_user = self.model.cfg.get_dest_dict().get('user', 'postgres')
                args.owner = Prompt.ask("Target owner role", default=default_user)
            elif cmd == "generate-config":
                args.output = Prompt.ask("Output path", default="config_migrator.sample.ini")
            elif cmd == "init-replication":
                args.drop_dest = Confirm.ask("Drop destination first?", default=False)
                args.wait = Confirm.ask("Wait for initial sync?", default=True)
            return args
        except EOFError:
            return None

    def _dispatch(self, step: dict, args) -> int:
        cmd = step["cmd"]

        if cmd == "init-replication":
            return cmd_init_replication(args)
        if cmd == "post-migration":
            return cmd_post_migration(args)

        dispatch_map = {
            "check": cmd_check, "diagnose": cmd_diagnose, "params": cmd_params,
            "migrate-schema-pre-data": cmd_migrate_schema_pre_data,
            "migrate-schema-post-data": cmd_migrate_schema_post_data,
            "setup-pub": cmd_setup_pub, "setup-sub": cmd_setup_sub,
            "repl-progress": cmd_progress, "refresh-matviews": cmd_refresh_matviews,
            "sync-sequences": cmd_sync_sequences, "terminate-repl": cmd_terminate_replication,
            "sync-lobs": cmd_sync_lobs, "sync-unlogged": cmd_sync_unlogged,
            "enable-triggers": cmd_enable_triggers, "reassign-owner": cmd_reassign_owner,
            "audit-objects": cmd_audit_objects, "validate-rows": cmd_validate_rows,
            "cleanup": cmd_cleanup, "setup-reverse": cmd_setup_reverse,
            "wait-sync": cmd_wait_sync, "cleanup-reverse": cmd_cleanup_reverse,
            "generate-config": cmd_generate_config,
            "stop-repl": cmd_stop_repl, "start-repl": cmd_start_repl,
        }

        func = dispatch_map.get(cmd)
        if not func:
            self.view.console.print(f"[red]No handler for '{cmd}'[/red]")
            return 1
        return func(args) or 0

    def _generate_report(self):
        out = self.model.generate_report()
        self.view.console.print(f"[green]Report generated: {out}[/green]")

    def _resolve_input(self, raw: str) -> Optional[dict]:
        if raw.upper() in ID_TO_STEP:
            return ID_TO_STEP[raw.upper()]
        if raw in ID_TO_STEP:
            return ID_TO_STEP[raw]
        if raw in CMD_TO_STEP:
            return CMD_TO_STEP[raw]
        return None

    def _setup_readline(self):
        self._completions = list(dict.fromkeys(
            ["next", "map", "status", "config", "dry-run", "report", "help", "quit"]
            + [s["id"] for s in STEPS] + [s["id"].lower() for s in STEPS] + [s["cmd"] for s in STEPS]
        ))
        def completer(text, state):
            matches = [w for w in self._completions if w.startswith(text.lower())]
            return matches[state] if state < len(matches) else None
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" ")
        self._history_file = os.path.join(os.path.expanduser("~"), ".pg_migrator_wizard_history")
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

def cmd_wizard(args):
    wizard = MigrationWizard(args.config, getattr(args, "database", None))
    wizard.run()
    return 0
