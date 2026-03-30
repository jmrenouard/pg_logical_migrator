import argparse
import logging
import sys
import os
import shutil
import time
import datetime
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual import work
from textual.widgets import Header, Footer, RichLog, Button, Label, Static, Checkbox
from textual.containers import Horizontal, Vertical, VerticalScroll
from src.config import Config
from src.db import PostgresClient
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator

class MigratorApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    Header {
        background: #1a252f;
        color: #ecf0f1;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }
    Footer {
        background: #1a252f;
        color: #95a5a6;
    }
    #main_container {
        layout: horizontal;
        height: 1fr;
    }
    #sidebar {
        width: 38;
        background: #2c3e50;
        padding: 0 1;
        border-right: tall #3498db;
    }
    #content {
        width: 1fr;
        padding: 1;
        background: #1e272e;
    }
    Button {
        width: 100%;
        margin-bottom: 0;
        height: 3;
        min-height: 3;
        text-style: bold;
    }
    Checkbox {
        width: 100%;
        margin-bottom: 0;
        color: #ecf0f1;
        background: #34495e;
    }
    .section_label {
        color: #3498db;
        text-style: bold;
        text-align: center;
        background: #2c3e50;
        width: 100%;
        padding: 0;
        margin-top: 1;
    }
    #step_1 { background: #2980b9; color: white; }
    #step_2 { background: #2980b9; color: white; }
    #step_3 { background: #2980b9; color: white; }
    #cmd_apply_params { background: #2471a3; color: white; }
    #step_4 { background: #e67e22; color: white; }
    #step_5 { background: #e67e22; color: white; }
    #step_6 { background: #e67e22; color: white; }
    #step_7 { background: #27ae60; color: white; }
    #step_8 { background: #8e44ad; color: white; }
    #step_10 { background: #8e44ad; color: white; }
    #step_11 { background: #8e44ad; color: white; }
    #step_12 { background: #c0392b; color: white; text-style: bold; }
    #step_13 { background: #f39c12; color: black; }
    #step_14 { background: #f39c12; color: black; }
    #cmd_disable_triggers { background: #7d3c98; color: white; }
    #cmd_init { background: #16a085; color: white; text-style: bold; }
    #cmd_post { background: #16a085; color: white; text-style: bold; }
    #cmd_generate_config { background: #566573; color: white; }

    #log_area {
        height: 1fr;
        background: #0d1117;
        color: #58d68d;
        border: solid #3498db;
    }
    #result_scroll {
        height: 1fr;
        background: #1e272e;
        border: solid #3498db;
    }
    #result_area {
        padding: 1;
        color: #ecf0f1;
    }
    """

    def __init__(self, config_path):
        super().__init__()
        self.config = Config(config_path)
        self.source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        self.dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        self.checker = DBChecker(self.source_client, self.dest_client)
        self.migrator = Migrator(self.config)
        self.post_sync = PostSync(self.source_client, self.dest_client)
        self.validator = Validator(self.source_client, self.dest_client)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main_container"):
            with VerticalScroll(id="sidebar"):
                yield Label("── OPTIONS ──", classes="section_label")
                yield Checkbox("Drop Dest Schema", id="opt_drop_dest")
                yield Checkbox("Verbose Mode", id="opt_verbose")

                yield Label("── MIGRATION STEPS ──", classes="section_label")
                yield Button("1. Check Connectivity", id="step_1")
                yield Button("2. Run Diagnostics", id="step_2")
                yield Button("3. Verify Parameters", id="step_3")
                yield Button("➤ Apply Parameters", id="cmd_apply_params")
                yield Button("4. Copy Schema", id="step_4")
                yield Button("5. Setup Publication", id="step_5")
                yield Button("6. Setup Subscription", id="step_6")
                yield Button("7. Replication Status", id="step_7")
                yield Button("8/9. Sync Sequences", id="step_8")
                yield Button("10. Enable Triggers", id="step_10")
                yield Button("➤ Disable Triggers", id="cmd_disable_triggers")
                yield Button("11. Refresh MatViews", id="step_11")
                yield Button("13. Object Audit", id="step_13")
                yield Button("14. Row Parity", id="step_14")
                yield Button("12. STOP / CLEANUP", id="step_12")

                yield Label("── AUTOMATION ──", classes="section_label")
                yield Button("▶ Init Replication", id="cmd_init")
                yield Button("▶ Post Migration", id="cmd_post")
                yield Button("⚙ Generate Config", id="cmd_generate_config")

            with Vertical(id="content"):
                with VerticalScroll(id="result_scroll"):
                    yield Static(id="result_area")
                yield RichLog(id="log_area", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "PostgreSQL Logical Migrator"
        self.log_area = self.query_one("#log_area", RichLog)
        self.result_area = self.query_one("#result_area")
        self.verbose = False
        self.log_area.write("[bold green]✔ TUI Initialized. Ready for migration.[/bold green]")

    def _log_detail(self, label: str, cmds, outs):
        """Write SQL commands and their outputs/results into the log panel (verbose mode only)."""
        if not self.verbose:
            return
        if cmds:
            self.log_area.write(f"── {label} Commands ──")
            for i, cmd in enumerate(cmds):
                self.log_area.write(f"  SQL> {cmd}")
                if outs and i < len(outs):
                    out_str = str(outs[i]).strip()
                    if out_str:
                        for line in out_str.splitlines():
                            self.log_area.write(f"       → {line}")
        else:
            self.log_area.write(f"── {label}: (no commands recorded) ──")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "opt_verbose":
            self.verbose = event.checkbox.value
            state = "enabled" if self.verbose else "disabled"
            self.log_area.write(f"[dim]ℹ Verbose mode {state}.[/dim]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.log_area.write("")
        self.log_area.write(f"▶ Running {event.button.label}...")
        try:
            if event.button.id == "step_1":
                res = self.checker.check_connectivity()
                src_ok = res['source']
                dst_ok = res['dest']
                status = f"Source: {'CONNECTED' if src_ok else 'FAILED'}\nDest: {'CONNECTED' if dst_ok else 'FAILED'}"
                color = "green" if src_ok and dst_ok else "red"
                self.result_area.update(Panel(status, title="[Step 1] Connectivity", border_style=color))
                self.log_area.write(f"  Source → {'OK' if src_ok else 'FAIL'}  |  Dest → {'OK' if dst_ok else 'FAIL'}")

            elif event.button.id == "step_2":
                res = self.checker.check_problematic_objects()
                diag = f"No PK tables: {len(res['no_pk'])}\nLarge Objects: {res['large_objects']}\nIdentity cols: {len(res['identities'])}\nUnowned Seqs: {len(res['unowned_seqs'])}\nUnlogged: {len(res.get('unlogged_tables', []))}\nTemp: {len(res.get('temp_tables', []))}\nForeign: {len(res.get('foreign_tables', []))}"
                self.result_area.update(Panel(diag, title="[Step 2] Diagnostics", border_style="yellow"))
                self.log_area.write(f"  Tables without PK: {len(res['no_pk'])}")
                for t in res['no_pk']:
                    self.log_area.write(f"    - {t['schema_name']}.{t['table_name']}")
                self.log_area.write(f"  Large Objects: {res['large_objects']}")
                self.log_area.write(f"  Identity Columns: {len(res['identities'])}")
                self.log_area.write(f"  Unowned Sequences: {len(res['unowned_seqs'])}")
                for s in res['unowned_seqs']:
                    self.log_area.write(f"    - {s['schema_name']}.{s['seq_name']}")
                self.log_area.write(f"  Unlogged Tables: {len(res.get('unlogged_tables', []))}")
                for t in res.get('unlogged_tables', []):
                    self.log_area.write(f"    - {t['schema_name']}.{t['table_name']}")
                self.log_area.write(f"  Temp Tables: {len(res.get('temp_tables', []))}")
                for t in res.get('temp_tables', []):
                    self.log_area.write(f"    - {t['schema_name']}.{t['table_name']}")
                self.log_area.write(f"  Foreign Tables: {len(res.get('foreign_tables', []))}")
                for t in res.get('foreign_tables', []):
                    self.log_area.write(f"    - {t['schema_name']}.{t['table_name']}")

            elif event.button.id == "step_3":
                res = self.checker.check_replication_params(apply_source=False, apply_dest=False)
                table = Table(title="PG Parameters")
                table.add_column("Instance", style="magenta")
                table.add_column("Param", style="cyan")
                table.add_column("Current")
                table.add_column("Expected")
                table.add_column("Status")
                for label in ["source", "dest"]:
                    if label in res:
                        for p in res[label]:
                            restart = " (PENDING RESTART)" if p.get('pending_restart') else ""
                            actual_display = f"{p['actual']}{restart}"
                            table.add_row(label.upper(), p['parameter'], actual_display, p['expected'], p['status'])
                            self.log_area.write(f"  [{label.upper()}] {p['parameter']}: {actual_display} (expected: {p['expected']}) → {p['status']}")
                self.result_area.update(table)

            elif event.button.id == "cmd_apply_params":
                res = self.checker.check_replication_params(apply_source=True, apply_dest=True)
                table = Table(title="Applied PG Parameters")
                table.add_column("Instance", style="magenta")
                table.add_column("Param", style="cyan")
                table.add_column("Current")
                table.add_column("Expected")
                table.add_column("Status")
                for label in ["source", "dest"]:
                    if label in res:
                        for p in res[label]:
                            restart = " (PENDING RESTART)" if p.get('pending_restart') else ""
                            actual_display = f"{p['actual']}{restart}"
                            table.add_row(label.upper(), p['parameter'], actual_display, p['expected'], p['status'])
                            self.log_area.write(f"  [{label.upper()}] {p['parameter']}: {actual_display} (expected: {p['expected']}) → {p['status']}")
                self.result_area.update(table)

            elif event.button.id == "step_4":
                drop_dest = self.query_one("#opt_drop_dest", Checkbox).value
                success, msg, cmds, outs = self.migrator.step4_migrate_schema(drop_dest=drop_dest)
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 4] Schema Migration", border_style=color))
                self._log_detail("Schema Migration", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_5":
                success, msg, cmds, outs = self.migrator.step5_setup_source()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 5] Source Pub", border_style=color))
                self._log_detail("Publication Setup", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_6":
                self.log_area.write(f"  [Background] Running '{event.button.label}' (this may take a while as it syncs initial data)...")
                self._do_step_6_async(str(event.button.label))
                return  # Skip the print at the end of the method

            elif event.button.id == "step_7":
                status = self.migrator.get_replication_status()
                pub_rows = status.get("publisher", [])
                sub_rows = status.get("subscriber", [])
                slot_rows = status.get("slots", [])
                full_sub_rows = status.get("full_sub", [])
                pub_info_rows = status.get("publications", [])

                if not pub_rows and not sub_rows and not slot_rows and not full_sub_rows and not pub_info_rows:
                    self.result_area.update(Panel("No active publisher, subscriber, or replication slots found.", title="Replication Status", border_style="red"))
                    self.log_area.write("  No active publisher, subscriber, or replication slots found.")
                else:
                    info_lines = []
                    if pub_rows:
                        info_lines.append("[bold cyan]PUBLISHER:[/bold cyan]")
                        self.log_area.write("  [PUBLISHER]")
                        for r in pub_rows:
                            for k, v in r.items():
                                line = f"  {k}: {v}"
                                info_lines.append(line)
                                self.log_area.write(line)
                    if sub_rows:
                        if info_lines: info_lines.append("")
                        info_lines.append("[bold cyan]SUBSCRIBER:[/bold cyan]")
                        self.log_area.write("  [SUBSCRIBER]")
                        for r in sub_rows:
                            for k, v in r.items():
                                line = f"  {k}: {v}"
                                info_lines.append(line)
                                self.log_area.write(line)
                    if slot_rows:
                        if info_lines: info_lines.append("")
                        info_lines.append("[bold cyan]SLOTS:[/bold cyan]")
                        self.log_area.write("  [SLOTS]")
                        for r in slot_rows:
                            for k, v in r.items():
                                line = f"  {k}: {v}"
                                info_lines.append(line)
                                self.log_area.write(line)
                    if full_sub_rows:
                        if info_lines: info_lines.append("")
                        info_lines.append("[bold cyan]PG_STAT_SUBSCRIPTION:[/bold cyan]")
                        self.log_area.write("  [PG_STAT_SUBSCRIPTION]")
                        for r in full_sub_rows:
                            for k, v in r.items():
                                line = f"  {k}: {v}"
                                info_lines.append(line)
                                self.log_area.write(line)
                    if pub_info_rows:
                        if info_lines: info_lines.append("")
                        info_lines.append("[bold cyan]PUBLICATIONS:[/bold cyan]")
                        self.log_area.write("  [PUBLICATIONS]")
                        for r in pub_info_rows:
                            for k, v in r.items():
                                line = f"  {k}: {v}"
                                info_lines.append(line)
                                self.log_area.write(line)

                    self.result_area.update(Panel("\n".join(info_lines), title="Replication Status", border_style="green"))

            elif event.button.id == "step_8":
                success, msg, cmds, outs = self.post_sync.sync_sequences()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 8/9] Sync Sequences", border_style=color))
                self._log_detail("Sync Sequences", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_10":
                success, msg, cmds, outs = self.post_sync.enable_triggers()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 10] Enable Triggers", border_style=color))
                self._log_detail("Enable Triggers", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "cmd_disable_triggers":
                success, msg, cmds, outs = self.post_sync.disable_triggers()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Utility] Disable Triggers", border_style=color))
                self._log_detail("Disable Triggers", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_11":
                success, msg, cmds, outs = self.post_sync.refresh_materialized_views()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 11] Refresh MatViews", border_style=color))
                self._log_detail("Refresh MatViews", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_13":
                s, m, c, o, rep = self.validator.audit_objects()
                table = Table(title="Object Audit")
                table.add_column("Type")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep:
                    table.add_row(r['type'], str(r['source']), str(r['dest']), r['status'])
                    self.log_area.write(f"  {r['type']}: src={r['source']} dst={r['dest']} → {r['status']}")
                self.result_area.update(table)
                self._log_detail("Object Audit", c, o)

            elif event.button.id == "step_14":
                s, m, c, o, rep = self.validator.compare_row_counts()
                table = Table(title="Row Parity")
                table.add_column("Table")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Diff")
                table.add_column("Status")
                for r in rep:
                    table.add_row(r['table'], str(r['source']), str(r['dest']), str(r['diff']), r['status'])
                    self.log_area.write(f"  {r['table']}: src={r['source']} dst={r['dest']} diff={r['diff']} → {r['status']}")
                self.result_area.update(table)
                self._log_detail("Row Parity", c, o)
                self.log_area.write(f"  Summary: {m}")

            elif event.button.id == "step_12":
                success, msg, cmds, outs = self.migrator.step12_terminate_replication()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 12] Cleanup", border_style=color))
                self._log_detail("Cleanup", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "cmd_generate_config":
                out_path = "config_migrator.sample.ini"
                import textwrap
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
                with open(out_path, "w") as fh:
                    fh.write(content)
                msg = f"Sample configuration written to {out_path}"
                self.result_area.update(Panel(msg, title="[Utility] Generate Config", border_style="green"))
                self.log_area.write(f"  Result: OK — {msg}")

            elif event.button.id == "cmd_init":
                self.log_area.write(f"  [Background] Running '{event.button.label}'...")
                self._do_init_async(str(event.button.label))
                return

            elif event.button.id == "cmd_post":
                self.log_area.write(f"  [Background] Running '{event.button.label}'...")
                self._do_post_async(str(event.button.label))
                return

            self.log_area.write(f"✔ {event.button.label} completed.")

        except Exception as e:
            self.log_area.write(f"✘ ERROR: {str(e)}")
            logging.error(f"[LOCAL] Error in TUI: {e}", exc_info=True)
            self.result_area.update(Panel(f"An error occurred: {e}", title="Error", border_style="red"))

    @work(exclusive=True, thread=True)
    def _do_step_6_async(self, label: str):
        try:
            success, msg, cmds, outs = self.migrator.step6_setup_destination()
            
            def update_ui():
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 6] Dest Sub", border_style=color))
                self._log_detail("Subscription Setup", cmds, outs)
                self.log_area.write(f"  Result: {'OK' if success else 'FAIL'} — {msg}")
                self.log_area.write(f"✔ {label} completed.")
                
            self.call_from_thread(update_ui)
            
        except Exception as e:
            def err_ui():
                self.log_area.write(f"✘ ERROR in Step 6: {str(e)}")
            self.call_from_thread(err_ui)
            logging.error(f"[LOCAL] Error in TUI step 6: {e}", exc_info=True)

    @work(exclusive=True, thread=True)
    def _do_init_async(self, label: str):
        def log_msg(msg):
            self.call_from_thread(self.log_area.write, msg)
        def update_ui(title, msg, color):
            self.call_from_thread(self.result_area.update, Panel(msg, title=title, border_style=color))
            
        try:
            log_msg("--- Starting Init Replication Pipeline ---")
            
            # Step 1
            res = self.checker.check_connectivity()
            if not (res['source'] and res['dest']):
                 log_msg("✘ Connectivity check failed. Source or Dest is unreachable. Aborting.")
                 update_ui("Init Replication Failed", "Connectivity check failed.", "red")
                 return
            log_msg("✔ Step 1: Connectivity check passed.")
            
            # Step 2
            diag = self.checker.check_problematic_objects()
            has_warnings = len(diag["no_pk"]) > 0 or diag["large_objects"] > 0 or len(diag.get("unlogged_tables", [])) > 0 or len(diag.get("temp_tables", [])) > 0 or len(diag.get("foreign_tables", [])) > 0
            log_msg(f"{'⚠' if has_warnings else '✔'} Step 2: Diagnostics run (Warnings present: {has_warnings})")
            
            # Step 3
            params = self.checker.check_replication_params()
            params_ok = True
            for plabel in ["source", "dest"]:
                 if params.get(plabel):
                     for r in params[plabel]:
                         if r['status'] != 'OK': params_ok = False
            log_msg(f"{'✔' if params_ok else '✘'} Step 3: Parameters check (OK: {params_ok})")
            
            # Step 4
            drop_dest = False
            try:
                opt = self.query_one("#opt_drop_dest", Checkbox)
                drop_dest = opt.value
            except Exception:
                pass
            s, m, c, o = self.migrator.step4_migrate_schema(drop_dest=drop_dest)
            if not s:
                 log_msg(f"✘ Schema migration failed: {m}")
                 update_ui("Init Replication Failed", m, "red")
                 return
            log_msg("✔ Step 4: Schema migration completed.")
            
            # Step 5
            s, m, c, o = self.migrator.step5_setup_source()
            if not s:
                 log_msg(f"✘ Source setup failed: {m}")
                 update_ui("Init Replication Failed", m, "red")
                 return
            log_msg("✔ Step 5: Source setup completed.")
            
            # Step 6
            s, m, c, o = self.migrator.step6_setup_destination()
            if not s:
                 log_msg(f"✘ Destination setup failed: {m}")
                 update_ui("Init Replication Failed", m, "red")
                 return
            log_msg("✔ Step 6: Destination setup completed.")
            
            log_msg("▶ Waiting 10s for initial table synchronization...")
            time.sleep(10)
            
            # Validation
            s1, m1, c1, o1, r1 = self.validator.audit_objects()
            log_msg(f"  - Object Audit: {'OK' if s1 else 'FAIL'}")
            s2, m2, c2, o2, r2 = self.validator.compare_row_counts()
            log_msg(f"  - Row Parity: {'OK' if s2 else 'FAIL'}")
            log_msg("✔ Steps 13/14: Validation completed.")
            
            log_msg(f"[bold green]✔ {label} completed successfully.[/bold green]")
            update_ui("Init Replication", "Initialization steps finished.", "green")
            
        except Exception as e:
            def err_ui():
                self.log_area.write(f"✘ ERROR in Init Pipeline: {str(e)}")
            self.call_from_thread(err_ui)
            logging.error(f"[LOCAL] Error in TUI Init Pipeline: {e}", exc_info=True)

    @work(exclusive=True, thread=True)
    def _do_post_async(self, label: str):
        def log_msg(msg):
            self.call_from_thread(self.log_area.write, msg)
        def update_ui(title, msg, color):
            self.call_from_thread(self.result_area.update, Panel(msg, title=title, border_style=color))
            
        try:
            log_msg("--- Starting Post Migration Pipeline ---")
            
            # Step 1
            res = self.checker.check_connectivity()
            if not (res['source'] and res['dest']):
                 log_msg("✘ Connectivity check failed. Source or Dest is unreachable. Aborting.")
                 update_ui("Post Migration Failed", "Connectivity check failed.", "red")
                 return
            log_msg("✔ Step 1: Connectivity check passed.")
            
            # Step 12
            s, m, c, o = self.migrator.step12_terminate_replication()
            log_msg(f"  - Cleanup: {'OK' if s else 'FAIL'} - {m}")
            log_msg("✔ Step 12: Cleanup completed.")
            
            # Post-sync
            s1, m1, c1, o1 = self.post_sync.refresh_materialized_views()
            log_msg(f"  - Refresh MatViews: {'OK' if s1 else 'FAIL'} - {m1}")
            s2, m2, c2, o2 = self.post_sync.sync_sequences()
            log_msg(f"  - Sync Sequences: {'OK' if s2 else 'FAIL'} - {m2}")
            s3, m3, c3, o3 = self.post_sync.enable_triggers()
            log_msg(f"  - Enable Triggers: {'OK' if s3 else 'FAIL'} - {m3}")
            log_msg("✔ Steps 8/9/10: Post-sync completed.")
            
            # Validation
            s1, m1, c1, o1, r1 = self.validator.audit_objects()
            log_msg(f"  - Object Audit: {'OK' if s1 else 'FAIL'}")
            s2, m2, c2, o2, r2 = self.validator.compare_row_counts()
            log_msg(f"  - Row Parity: {'OK' if s2 else 'FAIL'}")
            log_msg("✔ Steps 13/14: Validation completed.")
            
            log_msg(f"[bold green]✔ {label} completed successfully.[/bold green]")
            update_ui("Post Migration", "All post migration steps finished.", "green")
            
        except Exception as e:
            def err_ui():
                self.log_area.write(f"✘ ERROR in Post Pipeline: {str(e)}")
            self.call_from_thread(err_ui)
            logging.error(f"[LOCAL] Error in TUI Post Pipeline: {e}", exc_info=True)

def setup_results_dir():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = os.path.join("RESULTS", timestamp)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def main():
    parser = argparse.ArgumentParser(description="PostgreSQL Logical Migrator")
    parser.add_argument("--config", default="config_migrator.ini", help="Path to config .ini file")
    args = parser.parse_args()

    app = MigratorApp(args.config)
    app.run()

if __name__ == "__main__":
    main()
