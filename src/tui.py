from datetime import datetime
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual import work, on
from textual.widgets import Header, Footer, Button, Label, Static, Checkbox, TabbedContent, TabPane, ListView, ListItem
from textual.containers import Horizontal, Vertical, VerticalScroll, Container

from src.config import Config
from src.db import PostgresClient
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator


class HistoryItem(ListItem):
    """An item in the history list that stores its result for recall."""

    def __init__(self, label: str, result_renderable):
        super().__init__(
            Label(f"{datetime.now().strftime('%H:%M:%S')} - {label}"))
        self.result_renderable = result_renderable
        self.action_label = label


class MigratorApp(App):
    CSS = """
    Screen {
        background: #1e272e;
    }
    #main_layout {
        height: 100%;
    }
    #center_pane {
        width: 1fr;
        border-right: solid #3498db;
    }
    #history_pane {
        width: 35;
        background: #2c3e50;
    }
    .pane_header {
        background: #3498db;
        color: white;
        text-align: center;
        text-style: bold;
        padding: 0 1;
    }
    #action_area {
        height: auto;
        border-bottom: tall #3498db;
        background: #2f3640;
    }
    #display_area {
        height: 1fr;
        padding: 1;
    }
    #options_bar {
        height: 3;
        background: #353b48;
        padding: 0 1;
        align: center middle;
    }
    #options_bar Checkbox {
        margin-right: 2;
    }
    TabbedContent {
        height: auto;
    }
    TabPane {
        height: auto;
        padding: 0;
    }
    .btn_group {
        layout: horizontal;
        height: auto;
        align: center middle;
    }
    Button {
        margin: 0 1;
        min-width: 18;
    }
    /* Buttons Colors */
    .btn-pre { background: #2980b9; }
    .btn-setup { background: #e67e22; }
    .btn-final { background: #8e44ad; }
    .btn-valid { background: #f39c12; color: black; }
    .btn-clean { background: #c0392b; }
    .btn-auto { background: #16a085; }

    ListView {
        background: #2c3e50;
        color: #ecf0f1;
    }
    ListView > ListItem:hover {
        background: #34495e;
    }
    ListView > ListItem.--highlight {
        background: #3498db;
    }
    """

    def __init__(self, config_path):
        super().__init__()
        self.config = Config(config_path)
        self.source_client = PostgresClient(
            self.config.get_source_conn(), label="SOURCE")
        self.dest_client = PostgresClient(
            self.config.get_dest_conn(), label="DESTINATION")
        self.checker = DBChecker(
            self.source_client,
            self.dest_client,
            self.config)
        self.migrator = Migrator(self.config)
        self.post_sync = PostSync(
            self.source_client,
            self.dest_client,
            self.config)
        self.validator = Validator(
            self.source_client,
            self.dest_client,
            self.config)
        self.history_data = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main_layout"):
            with Vertical(id="center_pane"):
                with Horizontal(id="options_bar"):
                    yield Checkbox("Drop Dest", id="opt_drop_dest")
                    yield Checkbox("Use Stats", id="opt_use_stats")
                    yield Checkbox("Verbose", id="opt_verbose")
                    target_list = ", ".join(self.config.get_target_schemas())
                    yield Label(f" [dim]Schemas: {target_list}[/dim]")

                with Container(id="action_area"):
                    with TabbedContent():
                        with TabPane("1. Prepare"):
                            with Horizontal(classes="btn_group"):
                                yield Button("Check", id="step_1", classes="btn-pre")
                                yield Button("Diagnose", id="step_2", classes="btn-pre")
                                yield Button("Parameters", id="step_3", classes="btn-pre")
                                yield Button("Apply Params", id="cmd_apply_params", classes="btn-pre")
                        with TabPane("2. Replicate"):
                            with Horizontal(classes="btn_group"):
                                yield Button("Schema Pre", id="step_4", classes="btn-setup")
                                yield Button("Setup Pub", id="step_5", classes="btn-setup")
                                yield Button("Setup Sub", id="step_6", classes="btn-setup")
                                yield Button("Progress", id="cmd_progress", classes="btn-setup")
                        with TabPane("3. Finalize"):
                            with Horizontal(classes="btn_group"):
                                yield Button("MatViews", id="step_8", classes="btn-final")
                                yield Button("Sequences", id="step_9", classes="btn-final")
                                yield Button("Schema Post", id="step_10", classes="btn-final")
                                yield Button("LOBs Sync", id="step_11", classes="btn-final")
                                yield Button("Triggers", id="step_12", classes="btn-final")
                                yield Button("Ownership", id="step_13", classes="btn-final")
                        with TabPane("4. Audit"):
                            with Horizontal(classes="btn_group"):
                                yield Button("Objects", id="step_14", classes="btn-valid")
                                yield Button("Row Parity", id="step_15", classes="btn-valid")
                                yield Button("Cleanup", id="step_16", classes="btn-clean")
                                yield Button("Reverse", id="step_17", classes="btn-clean")
                        with TabPane("🚀 AUTOMATION"):
                            with Horizontal(classes="btn_group"):
                                yield Button("INIT PIPELINE", id="cmd_init", classes="btn-auto")
                                yield Button("POST PIPELINE", id="cmd_post", classes="btn-auto")

                with VerticalScroll(id="display_area"):
                    yield Static(id="main_display")

            with Vertical(id="history_pane"):
                yield Label("ACTION HISTORY", classes="pane_header")
                yield ListView(id="history_list")

        yield Footer()

    def on_mount(self) -> None:
        self.title = "pg_logical_migrator"
        self.sub_title = f"Config: {self.config.config_path}"
        self.display_widget = self.query_one("#main_display", Static)
        self.history_list = self.query_one("#history_list", ListView)
        self.update_display(
            Panel(
                "Welcome! Select an action above to begin.",
                title="Dashboard",
                border_style="cyan"))

    def update_display(self, renderable, label=None):
        """Update the main display and add to history if it's a new action."""
        self.display_widget.update(renderable)
        if label:
            item = HistoryItem(label, renderable)
            self.history_list.append(item)
            self.history_list.index = len(self.history_list) - 1

    @on(ListView.Selected)
    def recall_history(self, event: ListView.Selected):
        if isinstance(event.item, HistoryItem):
            self.display_widget.update(event.item.result_renderable)

    @on(Button.Pressed)
    def handle_buttons(self, event: Button.Pressed):
        btn_id = event.button.id
        label = str(event.button.label)

        try:
            if btn_id == "step_1":
                res = self.checker.check_connectivity()
                src_ok = '[green]OK[/]' if res['source'] else '[red]FAIL[/]'
                dst_ok = '[green]OK[/]' if res['dest'] else '[red]FAIL[/]'
                status = f"Source: {src_ok}\nDest: {dst_ok}"
                self.update_display(
                    Panel(
                        Text.from_markup(status),
                        title="Connectivity"),
                    label)

            elif btn_id == "step_2":
                res = self.checker.check_problematic_objects()
                # Basic diagnostic table
                table = Table(title="Diagnostics Summary")
                table.add_column("Object Type", style="cyan")
                table.add_column("Count", justify="right")
                table.add_row("Tables without PK", str(len(res['no_pk'])))
                table.add_row(
                    "Large Objects (LOBs)", str(
                        res['large_objects']))
                table.add_row("Unowned Sequences", str(
                    len(res['unowned_seqs'])))
                table.add_row("Unlogged Tables", str(
                    len(res.get('unlogged_tables', []))))
                self.update_display(table, label)

            elif btn_id == "step_3":
                res = self.checker.check_replication_params()
                table = Table(title="PostgreSQL Parameters")
                table.add_column("Instance")
                table.add_column("Parameter")
                table.add_column("Value")
                table.add_column("Status")
                for side in ["source", "dest"]:
                    for p in res.get(side, []):
                        color = "green" if p['status'] == "OK" else "red"
                        table.add_row(side.upper(),
                                      p['parameter'],
                                      p['actual'],
                                      f"[{color}]{p['status']}[/]")
                self.update_display(table, label)

            elif btn_id == "step_4":
                drop = self.query_one("#opt_drop_dest", Checkbox).value
                s, m, c, o = self.migrator.step4a_migrate_schema_pre_data(
                    drop_dest=drop)
                self.update_display(
                    Panel(
                        m,
                        title="Schema Pre-Data",
                        border_style="green" if s else "red"),
                    label)

            elif btn_id == "step_5":
                s, m, c, o = self.migrator.step5_setup_source()
                self.update_display(Panel(m, title="Setup Publication"), label)

            elif btn_id == "step_6":
                self.update_display(
                    Panel(
                        "Starting subscription creation in background...",
                        title="Subscription"),
                    label)
                self._run_sub_async()

            elif btn_id == "cmd_progress":
                progress = self.migrator.get_initial_copy_progress()
                if not progress:
                    self.update_display(
                        Panel(
                            "No active replication progress found.",
                            border_style="yellow"),
                        label)
                else:
                    table = Table(title="Sync Progress")
                    table.add_column("Table")
                    table.add_column("State")
                    table.add_column("Progress")
                    for t in progress['tables']:
                        table.add_row(t['table_name'],
                                      t['state'], f"{t['percent']}%")
                    self.update_display(table, label)

            elif btn_id == "step_8":
                s, m, c, o = self.post_sync.refresh_materialized_views()
                self.update_display(Panel(m, title="MatViews Refresh"), label)

            elif btn_id == "step_9":
                s, m, c, o = self.post_sync.sync_sequences()
                self.update_display(Panel(m, title="Sequences Sync"), label)

            elif btn_id == "step_10":
                s, m, c, o = self.migrator.step10_terminate_replication()
                self.update_display(
                    Panel(
                        m,
                        title="Terminate Replication"),
                    label)
                s2, m2, c2, o2 = self.migrator.step4b_migrate_schema_post_data()
                self.update_display(Panel(m2, title="Schema Post-Data"), label)

            elif btn_id == "step_11":
                s, m, c, o = self.migrator.sync_large_objects()
                self.update_display(
                    Panel(
                        m,
                        title="LOBs Sync",
                        border_style="green" if s else "red"),
                    label)

            elif btn_id == "step_12":
                s, m, c, o = self.post_sync.enable_triggers()
                self.update_display(Panel(m, title="Enable Triggers"), label)

            elif btn_id == "step_13":
                s, m, c, o = self.post_sync.reassign_ownership()
                self.update_display(
                    Panel(
                        m,
                        title="Reassign Ownership"),
                    label)

            elif btn_id == "step_14":
                s, m, c, o, rep = self.validator.audit_objects()
                table = Table(title="Object Audit")
                table.add_column("Type")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep:
                    table.add_row(
                        r['type'], str(
                            r['source']), str(
                            r['dest']), r['status'])
                self.update_display(table, label)

            elif btn_id == "step_15":
                use_stats = self.query_one("#opt_use_stats", Checkbox).value
                s, m, c, o, rep = self.validator.compare_row_counts(
                    use_stats=use_stats)
                table = Table(title="Row Count Parity")
                table.add_column("Table")
                table.add_column("Diff")
                table.add_column("Status")
                for r in rep[:40]:
                    color = "green" if r['status'] == "OK" else "red"
                    table.add_row(r['table'], str(r['diff']),
                                  f"[{color}]{r['status']}[/]")
                self.update_display(table, label)

            elif btn_id == "cmd_init":
                self._run_init_pipeline()

            elif btn_id == "cmd_post":
                self._run_post_pipeline()

            # (Generic handler for other steps)
            elif btn_id.startswith("step_") or btn_id.startswith("cmd_"):
                self.update_display(
                    Panel(
                        f"Action '{label}' executed. (Check logs for details)",
                        title="Action"),
                    label)

        except Exception as e:
            self.update_display(
                Panel(
                    f"[bold red]Error:[/] {e}",
                    title="Exception"),
                label)

    @work(exclusive=True, thread=True)
    def _run_sub_async(self):
        label = "Step 6: Sub"
        try:
            s, m, c, o = self.migrator.step6_setup_destination()
            self.call_from_thread(
                self.update_display,
                Panel(
                    m,
                    title="Subscription Result",
                    border_style="green" if s else "red"),
                label)
        except Exception as e:
            self.call_from_thread(
                self.update_display,
                Panel(
                    f"Pipeline Failed: {e}",
                    title=label,
                    border_style="red"),
                label)

    @work(exclusive=True, thread=True)
    def _run_init_pipeline(self):
        label = "INIT PIPELINE"
        self.call_from_thread(
            self.update_display,
            Panel(
                "Starting Automated Init Pipeline...",
                border_style="blue"),
            label)
        try:
            drop = self.query_one("#opt_drop_dest", Checkbox).value
            self.migrator.step4a_migrate_schema_pre_data(drop_dest=drop)
            self.migrator.step5_setup_source()
            self.migrator.step6_setup_destination()
            self.migrator.wait_for_sync(show_progress=False)
            self.call_from_thread(
                self.update_display,
                Panel(
                    "Pipeline Completed Successfully",
                    title=label,
                    border_style="green"),
                label)
        except Exception as e:
            self.call_from_thread(
                self.update_display,
                Panel(
                    f"Pipeline Failed: {e}",
                    title=label,
                    border_style="red"),
                label)

    @work(exclusive=True, thread=True)
    def _run_post_pipeline(self):
        label = "POST PIPELINE"
        self.call_from_thread(
            self.update_display,
            Panel(
                "Starting Automated Post-Migration Pipeline (Phase 3 & 4)...",
                border_style="blue"),
            label)
        try:
            # Phase 3: Finalize
            self.call_from_thread(self.update_display, Panel(
                "Step 7: Waiting for final sync..."), label)
            self.migrator.wait_for_sync(show_progress=False)

            self.call_from_thread(self.update_display, Panel(
                "Step 8: Refreshing MatViews..."), label)
            self.post_sync.refresh_materialized_views()

            self.call_from_thread(
                self.update_display,
                Panel("Step 9: Syncing Sequences..."),
                label)
            self.post_sync.sync_sequences()

            self.call_from_thread(self.update_display, Panel(
                "Step 10: Terminating Replication & Schema Post-Data..."), label)
            self.migrator.step10_terminate_replication()
            self.migrator.step4b_migrate_schema_post_data()

            self.call_from_thread(self.update_display, Panel(
                "Step 11: Syncing Large Objects (LOBs)..."), label)
            self.migrator.sync_large_objects()

            self.call_from_thread(self.update_display, Panel(
                "Step 12: Enabling Triggers..."), label)
            self.post_sync.enable_triggers()

            self.call_from_thread(self.update_display, Panel(
                "Step 13: Reassigning Ownership..."), label)
            self.post_sync.reassign_ownership()

            # Phase 4: Validate
            self.call_from_thread(
                self.update_display,
                Panel("Step 14: Auditing Objects..."),
                label)
            self.validator.audit_objects()

            self.call_from_thread(self.update_display, Panel(
                "Step 15: Comparing Row Parity..."), label)
            self.validator.compare_row_counts()

            from src.report import ReportGenerator
            self.call_from_thread(
                self.update_display,
                Panel("Generating Final Report..."),
                label)
            ReportGenerator(self.config).generate_html_report()

            self.call_from_thread(
                self.update_display,
                Panel(
                    "Post-Migration Pipeline Completed Successfully",
                    title=label,
                    border_style="green"),
                label)
        except Exception as e:
            self.call_from_thread(
                self.update_display,
                Panel(
                    f"Pipeline Failed: {e}",
                    title=label,
                    border_style="red"),
                label)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config_migrator.ini")
    args = parser.parse_args()
    app = MigratorApp(args.config)
    app.run()


if __name__ == "__main__":
    main()
