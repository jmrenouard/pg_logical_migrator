import logging
import time
import textwrap
from rich.panel import Panel
from rich.table import Table
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
        background: #1e272e;
    }
    #main_container {
        height: 100%;
    }
    #sidebar {
        width: 35;
        background: #2c3e50;
        border-right: solid #3498db;
        padding: 1;
    }
    .section_label {
        background: #34495e;
        color: #ecf0f1;
        text-align: center;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
        padding: 0 1;
    }
    #lbl_schemas {
        color: #95a5a6;
        text-style: italic;
        text-align: center;
        padding: 0 1;
        margin-bottom: 1;
    }
    /* Buttons Colors by Phase */
    .btn-pre { background: #2980b9; color: white; }
    .btn-setup { background: #e67e22; color: white; }
    .btn-monitor { background: #d35400; color: white; }
    .btn-final { background: #8e44ad; color: white; }
    .btn-valid { background: #f39c12; color: black; }
    .btn-clean { background: #c0392b; color: white; text-style: bold; }
    .btn-auto { background: #16a085; color: white; text-style: bold; }

    #log_area {
        background: black;
        color: #00ff00;
        height: 40%;
        border-top: solid #3498db;
    }
    #result_scroll {
        background: #1e272e;
        height: 1fr;
        border: solid #3498db;
    }
    #result_area {
        color: #ecf0f1;
        padding: 1;
    }
    Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    def __init__(self, config_path):
        super().__init__()
        self.config = Config(config_path)
        self.source_client = PostgresClient(self.config.get_source_conn(), label="SOURCE")
        self.dest_client = PostgresClient(self.config.get_dest_conn(), label="DESTINATION")
        self.checker = DBChecker(self.source_client, self.dest_client, self.config)
        self.migrator = Migrator(self.config)
        self.post_sync = PostSync(self.source_client, self.dest_client, self.config)
        self.validator = Validator(self.source_client, self.dest_client, self.config)
        self.verbose = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main_container"):
            with VerticalScroll(id="sidebar"):
                yield Label("── CONFIG ──", classes="section_label")
                target_list = ", ".join(self.config.get_target_schemas())
                yield Label(f"Schemas: {target_list}", id="lbl_schemas")
                
                yield Label("── OPTIONS ──", classes="section_label")
                yield Checkbox("Drop Dest Schema", id="opt_drop_dest")
                yield Checkbox("Use Stats for Counts", id="opt_use_stats")
                yield Checkbox("Verbose Mode", id="opt_verbose")

                yield Label("── PRE-FLIGHT ──", classes="section_label")
                yield Button("1. Check Connectivity", id="step_1", classes="btn-pre")
                yield Button("2. Run Diagnostics", id="step_2", classes="btn-pre")
                yield Button("3. Verify Parameters", id="step_3", classes="btn-pre")
                yield Button("➤ Apply Parameters", id="cmd_apply_params", classes="btn-pre")

                yield Label("── REPLICATION SETUP ──", classes="section_label")
                yield Button("4. Copy Schema Pre-data", id="step_4", classes="btn-setup")
                yield Button("5. Setup Publication", id="step_5", classes="btn-setup")
                yield Button("6. Setup Subscription", id="step_6", classes="btn-setup")

                yield Label("── MONITORING ──", classes="section_label")
                yield Button("➤ Initial Copy Progress", id="cmd_progress", classes="btn-monitor")
                yield Button("7. Replication Status", id="step_7", classes="btn-monitor")

                yield Label("── FINALIZATION ──", classes="section_label")
                yield Button("8. Refresh MatViews", id="step_8", classes="btn-final")
                yield Button("9/10. Sync Sequences", id="step_9", classes="btn-final")
                yield Button("11. Enable Triggers", id="step_11", classes="btn-final")
                yield Button("➤ Disable Triggers", id="cmd_disable_triggers", classes="btn-final")
                yield Button("12. Copy Schema Post-data", id="step_12", classes="btn-final")
                yield Button("13. Reassign Ownership", id="step_13", classes="btn-final")

                yield Label("── VALIDATION & CLEANUP ──", classes="section_label")
                yield Button("14. Object Audit", id="step_14", classes="btn-valid")
                yield Button("15. Row Parity", id="step_15", classes="btn-valid")
                yield Button("16. STOP / CLEANUP", id="step_16", classes="btn-clean")
                yield Button("17. Setup Reverse Repl", id="step_17", classes="btn-clean")

                yield Label("── AUTOMATION ──", classes="section_label")
                yield Button("▶ Init Replication", id="cmd_init", classes="btn-auto")
                yield Button("▶ Post Migration", id="cmd_post", classes="btn-auto")
                yield Button("⚙ Generate Config", id="cmd_generate_config")

            with Vertical(id="content"):
                with VerticalScroll(id="result_scroll"):
                    yield Static(id="result_area")
                yield RichLog(id="log_area", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "PostgreSQL Logical Migrator"
        self.log_area = self.query_one("#log_area", RichLog)
        self.result_area = self.query_one("#result_area", Static)
        self.log_area.write("Welcome to PostgreSQL Logical Migrator TUI.")
        self.log_area.write(f"Config loaded: [bold cyan]{self.config.config_path}[/bold cyan]")

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
                
                # Add Size Analysis
                sizes = self.checker.get_database_size_analysis(self.source_client)
                table = None
                if sizes and sizes.get("database"):
                    table = Table(title="Top Tables by Size")
                    table.add_column("Table", style="cyan")
                    table.add_column("Data")
                    table.add_column("Index")
                    table.add_column("Total")
                    table.add_column("% DB")
                    for t in sizes.get("tables", [])[:15]:
                        table.add_row(
                            f"{t.get('schema_name', '')}.{t.get('table_name', '')}", 
                            t.get('data_pretty', ''), 
                            t.get('index_pretty', ''), 
                            t.get('total_pretty', ''),
                            f"{t.get('percent', 0)}%"
                        )
                
                if table:
                    diag_flat = diag.replace('\n', ' | ')
                    diag_title = f"Diagnostics: {diag_flat}"
                    self.result_area.update(Panel(table, title=diag_title, border_style="yellow"))
                else:
                    self.result_area.update(Panel(diag, title="[Step 2] Diagnostics", border_style="yellow"))

                self.log_area.write(f"  Diagnostics: {len(res['no_pk'])} No-PK, {res['large_objects']} LOBs, {len(res['unowned_seqs'])} Unowned Seqs.")

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
                            table.add_row(label.upper(), p['parameter'], f"{p['actual']}{restart}", p['expected'], p['status'])
                self.result_area.update(table)

            elif event.button.id == "cmd_apply_params":
                res = self.checker.check_replication_params(apply_source=True, apply_dest=True)
                self.result_area.update(Panel("Replication parameters applied to target instances.", title="Apply Parameters", border_style="green"))

            elif event.button.id == "step_4":
                drop_dest = self.query_one("#opt_drop_dest", Checkbox).value
                success, msg, cmds, outs = self.migrator.step4a_migrate_schema_pre_data(drop_dest=drop_dest)
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 4] Schema PRE-DATA", border_style=color))
                self._log_detail("Schema Pre-Data", cmds, outs)

            elif event.button.id == "step_5":
                success, msg, cmds, outs = self.migrator.step5_setup_source()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 5] Source Publication", border_style=color))
                self._log_detail("Publication Setup", cmds, outs)

            elif event.button.id == "step_6":
                self.log_area.write(f"  [Background] Running Step 6...")
                self._do_step_6_async(str(event.button.label))
                return

            elif event.button.id == "cmd_progress":
                progress = self.migrator.get_initial_copy_progress()
                if not progress or not progress.get("summary"):
                    self.result_area.update(Panel("Sync progress unavailable. Is replication active?", title="Progress", border_style="red"))
                else:
                    summ = progress.get("summary", {})
                    table = Table(title="Table Sync Progress")
                    table.add_column("Table", style="cyan")
                    table.add_column("State")
                    table.add_column("Progress (Bytes)")
                    table.add_column("%")
                    from src.db import pretty_size
                    for r in progress.get("tables", []):
                        state = r.get('state', '?')
                        color = "green" if state in ('r','s') else "yellow"
                        if state == 'd': color = "bold blue"
                        table.add_row(str(r.get('table_name')), f"[{color}]{state}[/{color}]",
                                      f"{pretty_size(r.get('bytes_copied', 0))} / {pretty_size(r.get('size_source', 0))}",
                                      f"{r.get('percent', 0)}%")
                    title = f"Bytes: {summ.get('percent_bytes', 0)}% | Tables: {summ.get('completed_tables')}/{summ.get('total_tables')}"
                    self.result_area.update(Panel(table, title=title, border_style="blue"))

            elif event.button.id == "step_7":
                status = self.migrator.get_replication_status()
                # Basic summary panel for Step 7
                lines = []
                for side in ["SOURCE", "DEST"]:
                    sub_active = len([s for s in status.get('subscriber', []) if s.get('side') == side])
                    pub_active = len([p for p in status.get('publisher', []) if p.get('side') == side])
                    lines.append(f"[bold]{side}:[/bold] {sub_active} Subscriptions, {pub_active} Replication slots")
                self.result_area.update(Panel("\n".join(lines), title="[Step 7] Replication Status", border_style="green"))

            elif event.button.id == "step_8":
                success, msg, cmds, outs = self.post_sync.refresh_materialized_views()
                self.result_area.update(Panel(msg, title="[Step 8] Refresh MatViews", border_style="green" if success else "red"))
                self._log_detail("MatViews", cmds, outs)

            elif event.button.id == "step_9":
                success, msg, cmds, outs = self.post_sync.sync_sequences()
                self.result_area.update(Panel(msg, title="[Step 9/10] Sync Sequences", border_style="green" if success else "red"))
                self._log_detail("Sequences", cmds, outs)

            elif event.button.id == "step_11":
                success, msg, cmds, outs = self.post_sync.enable_triggers()
                self.result_area.update(Panel(msg, title="[Step 11] Enable Triggers", border_style="green" if success else "red"))
                self._log_detail("Triggers", cmds, outs)

            elif event.button.id == "cmd_disable_triggers":
                success, msg, cmds, outs = self.post_sync.disable_triggers()
                self.result_area.update(Panel(msg, title="Disable Triggers", border_style="green" if success else "red"))

            elif event.button.id == "step_12":
                success, msg, cmds, outs = self.migrator.step4b_migrate_schema_post_data()
                self.result_area.update(Panel(msg, title="[Step 12] Schema POST-DATA", border_style="green" if success else "red"))
                self._log_detail("Schema Post-Data", cmds, outs)

            elif event.button.id == "step_13":
                target_owner = self.config.get_dest_dict().get('user', 'postgres')
                success, msg, cmds, outs = self.post_sync.reassign_ownership(target_owner)
                self.result_area.update(Panel(msg, title="[Step 13] Reassign Ownership", border_style="green" if success else "yellow"))
                self._log_detail("Ownership", cmds, outs)

            elif event.button.id == "step_14":
                s, m, c, o, rep = self.validator.audit_objects()
                table = Table(title="Object Audit")
                table.add_column("Type")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep:
                    table.add_row(r['type'], str(r['source']), str(r['dest']), r['status'])
                self.result_area.update(table)
                self._log_detail("Audit", c, o)

            elif event.button.id == "step_15":
                use_stats = self.query_one("#opt_use_stats", Checkbox).value
                s, m, c, o, rep = self.validator.compare_row_counts(use_stats=use_stats)
                table = Table(title=f"Row Parity ({'stats' if use_stats else 'count'})")
                table.add_column("Table")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep[:50]: # Cap display
                    table.add_row(r['table'], str(r['source']), str(r['dest']), r['status'])
                self.result_area.update(table)
                self.log_area.write(f"  Summary: {m}")

            elif event.button.id == "step_16":
                success, msg, cmds, outs = self.migrator.step12_terminate_replication()
                self.result_area.update(Panel(msg, title="[Step 16] Stop & Cleanup", border_style="green" if success else "red"))
                self._log_detail("Cleanup", cmds, outs)

            elif event.button.id == "step_17":
                success, msg, cmds, outs = self.migrator.setup_reverse_replication()
                self.result_area.update(Panel(msg, title="[Step 17] Setup Rollback", border_style="green" if success else "red"))
                self._log_detail("Rollback Setup", cmds, outs)

            elif event.button.id == "cmd_generate_config":
                self.result_area.update(Panel("Config generation not available from TUI. Use CLI: generate-config", title="Config", border_style="yellow"))

            elif event.button.id == "cmd_init":
                drop_dest = self.query_one("#opt_drop_dest", Checkbox).value
                use_stats = self.query_one("#opt_use_stats", Checkbox).value
                self._do_init_async(str(event.button.label), drop_dest, use_stats)
                return

            elif event.button.id == "cmd_post":
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
                self.result_area.update(Panel(msg, title="[Step 6] Dest Subscription", border_style="green" if success else "red"))
                self._log_detail("Sub Setup", cmds, outs)
                self.log_area.write(f"✔ {label} completed.")
            self.call_from_thread(update_ui)
        except Exception as e:
            self.call_from_thread(self.log_area.write, f"✘ ERROR: {e}")

    @work(exclusive=True, thread=True)
    def _do_init_async(self, label: str, drop_dest: bool, use_stats: bool):
        def log_msg(msg): self.call_from_thread(self.log_area.write, msg)
        try:
            log_msg("--- Starting Init Pipeline ---")
            self.checker.check_connectivity()
            self.migrator.step4a_migrate_schema_pre_data(drop_dest=drop_dest)
            self.migrator.step5_setup_source()
            self.migrator.step6_setup_destination()
            log_msg("▶ Waiting for initial sync...")
            self.migrator.wait_for_sync(timeout=3600, show_progress=False)
            self.validator.audit_objects()
            self.validator.compare_row_counts(use_stats=use_stats)
            log_msg("[bold green]✔ Init Pipeline completed.[/bold green]")
        except Exception as e:
            log_msg(f"✘ ERROR: {e}")

    @work(exclusive=True, thread=True)
    def _do_post_async(self, label: str):
        def log_msg(msg): self.call_from_thread(self.log_area.write, msg)
        try:
            log_msg("--- Starting Post Pipeline ---")
            self.migrator.wait_for_sync(timeout=3600, show_progress=False)
            self.migrator.step12_terminate_replication()
            self.migrator.step4b_migrate_schema_post_data()
            self.post_sync.refresh_materialized_views()
            self.post_sync.sync_sequences()
            self.post_sync.enable_triggers()
            self.post_sync.reassign_ownership(self.config.get_dest_dict().get('user', 'postgres'))
            log_msg("[bold green]✔ Post Pipeline completed.[/bold green]")
        except Exception as e:
            log_msg(f"✘ ERROR: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PostgreSQL Logical Migrator")
    parser.add_argument("--config", default="config_migrator.ini", help="Path to config .ini file")
    args = parser.parse_args()
    app = MigratorApp(args.config)
    app.run()

if __name__ == "__main__":
    main()
