from datetime import datetime
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual import work, on
from textual.widgets import Header, Footer, Button, Label, Static, Checkbox, TabbedContent, TabPane, ListView, ListItem, Select, Input
from textual.containers import Horizontal, Vertical, VerticalScroll, Container, Grid

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
    
    #config_form {
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-rows: auto;
        padding: 1;
    }
    #config_form Input {
        margin: 1;
    }

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
        self.databases = self.config.get_databases()
        if '*' in self.databases:
            import os
            # Determine actual DBs from the source connection
            sc = PostgresClient(self.config.get_source_conn())
            res = sc.execute_query("SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';")
            self.databases = [row['datname'] for row in res]
            sc.close()
            
        # Default to first DB
        self.current_db = self.databases[0] if self.databases else None
        self._init_backend_for_db(self.current_db)
        self.history_data = []

    def _init_backend_for_db(self, db_name):
        import os
        if db_name:
            os.environ['PG_MIGRATOR_OVERRIDE_DB'] = db_name
            self.config.set_override_db(db_name)
        
        # Cleanup old connections if they exist
        if hasattr(self, 'source_client') and self.source_client:
            self.source_client.close()
        if hasattr(self, 'dest_client') and self.dest_client:
            self.dest_client.close()
            
        self.source_client = PostgresClient(
            self.config.get_source_conn(db_name), label=f"SOURCE {db_name}")
        self.dest_client = PostgresClient(
            self.config.get_dest_conn(db_name), label=f"DESTINATION {db_name}")
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main_layout"):
            with Vertical(id="center_pane"):
                with Horizontal(id="options_bar"):
                    db_options = [("ALL DATABASES", "ALL")] + [(db, db) for db in self.databases]
                    yield Select(db_options, value="ALL" if len(self.databases) > 1 else self.databases[0], id="opt_database")
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
                                yield Button("UNLOGGED Sync", id="step_11b", classes="btn-final")
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
                        with TabPane("⚙️ Config Gen"):
                            with VerticalScroll():
                                yield Label("Generate an environment-specific config file", classes="pane_header")
                                with Grid(id="config_form"):
                                    yield Input(placeholder="Source Host (e.g. localhost)", value="localhost", id="gen_src_host")
                                    yield Input(placeholder="Source Port (e.g. 5432)", value="5432", id="gen_src_port")
                                    yield Input(placeholder="Source User", value="postgres", id="gen_src_user")
                                    yield Input(placeholder="Source Password", password=True, id="gen_src_pass")
                                    
                                    yield Input(placeholder="Dest Host", value="localhost", id="gen_dest_host")
                                    yield Input(placeholder="Dest Port", value="5433", id="gen_dest_port")
                                    yield Input(placeholder="Dest User", value="postgres", id="gen_dest_user")
                                    yield Input(placeholder="Dest Password", password=True, id="gen_dest_pass")
                                    
                                    yield Input(placeholder="Databases (comma separated or *)", value="*", id="gen_databases")
                                    yield Input(placeholder="Output Filename", value="config_custom.ini", id="gen_filename")
                                with Horizontal(classes="btn_group"):
                                    yield Button("Generate Config", id="cmd_generate_config", classes="btn-auto")

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
            selected_db = self.query_one("#opt_database", Select).value
            dbs_to_run = self.databases if selected_db == "ALL" else [selected_db]
            
            # Use threads for ALL runs to avoid blocking TUI or refactor into single action
            # For simplicity, we loop synchronously for fast steps, async for pipelines
            
            # Since many methods return UI components, if ALL is selected we might just show the last one,
            # or a summary. For now, we update display per DB.
            if len(dbs_to_run) > 1 and btn_id not in ("cmd_init", "cmd_post", "cmd_progress"):
                self.update_display(Panel(f"Running '{label}' on {len(dbs_to_run)} databases sequentially... Check terminal logs for detailed progress.", title="Multi-DB Execution", border_style="yellow"), label)
                
            for db in dbs_to_run:
                self._init_backend_for_db(db)
                
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
                        f"[b]Step 11a: Sync Large Objects[/b]\n\n{m}",
                        style="green" if s else "red"))

            elif btn_id == "step_11b":
                s, m, c, o = self.migrator.sync_unlogged_tables()
                self.update_display(
                    Panel(
                        f"[b]Step 11b: Sync UNLOGGED Tables[/b]\n\n{m}",
                        style="green" if s else "red"))

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

            elif btn_id == "step_16":
                s, m, c, o = self.migrator.cleanup_reverse_replication()
                self.update_display(
                    Panel(
                        m,
                        title="Cleanup Reverse Replication",
                        border_style="green" if s else "red"),
                    label)

            elif btn_id == "step_17":
                s, m, c, o = self.migrator.setup_reverse_replication()
                self.update_display(
                    Panel(
                        m,
                        title="Setup Reverse Replication",
                        border_style="green" if s else "red"),
                    label)

            elif btn_id == "cmd_init":
                self._run_init_pipeline(dbs_to_run)
                return  # Skip the rest of the loop since the worker handles it

            elif btn_id == "cmd_post":
                self._run_post_pipeline(dbs_to_run)
                return  # Skip the rest of the loop since the worker handles it

            elif btn_id == "cmd_generate_config":
                self._generate_config_file()
                return

            # (Generic handler for other steps)
            elif btn_id.startswith("step_") or btn_id.startswith("cmd_"):
                self.update_display(
                    Panel(
                        f"Action '{label}' executed for DB {db}. (Check logs for details)",
                        title="Action"),
                    label)
                    
        except Exception as e:
            self.update_display(
                Panel(
                    f"[bold red]Error on {db}:[/] {e}",
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
    def _run_init_pipeline(self, dbs_to_run):
        label = "INIT PIPELINE"
        self.call_from_thread(
            self.update_display,
            Panel(
                f"Starting Automated Init Pipeline on {len(dbs_to_run)} DBs...",
                border_style="blue"),
            label)
        try:
            drop = self.query_one("#opt_drop_dest", Checkbox).value
            for db in dbs_to_run:
                self.call_from_thread(self._init_backend_for_db, db)
                self.call_from_thread(self.update_display, Panel(f"Processing DB: {db} (Init)"), label)
                self.migrator.step4a_migrate_schema_pre_data(drop_dest=drop)
                self.migrator.step5_setup_source()
                self.migrator.step6_setup_destination()
                self.migrator.wait_for_sync(show_progress=False)
                
            self.call_from_thread(
                self.update_display,
                Panel(
                    "Pipeline Completed Successfully for all DBs",
                    title=label,
                    border_style="green"),
                label)
        except Exception as e:
            self.call_from_thread(
                self.update_display,
                Panel(
                    f"Pipeline Failed on DB {db}: {e}",
                    title=label,
                    border_style="red"),
                label)

    @work(exclusive=True, thread=True)
    def _run_post_pipeline(self, dbs_to_run):
        label = "POST PIPELINE"
        self.call_from_thread(
            self.update_display,
            Panel(
                f"Starting Automated Post-Migration Pipeline (Phase 3 & 4) on {len(dbs_to_run)} DBs...",
                border_style="blue"),
            label)
        try:
            for db in dbs_to_run:
                self.call_from_thread(self._init_backend_for_db, db)
                self.call_from_thread(self.update_display, Panel(f"Processing DB: {db} (Post-Migration)"), label)

                # Phase 3: Finalize
                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 7: Waiting for final sync..."), label)
                self.migrator.wait_for_sync(show_progress=False)

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 8: Refreshing MatViews..."), label)
                self.post_sync.refresh_materialized_views()

                self.call_from_thread(
                    self.update_display,
                    Panel(f"[{db}] Step 9: Syncing Sequences..."),
                    label)
                self.post_sync.sync_sequences()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 10: Terminating Replication & Schema Post-Data..."), label)
                self.migrator.step10_terminate_replication()
                self.migrator.step4b_migrate_schema_post_data()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 11a: Syncing Large Objects (LOBs)..."), label)
                self.migrator.sync_large_objects()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 11b: Syncing UNLOGGED Tables..."), label)
                self.migrator.sync_unlogged_tables()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 12: Enabling Triggers..."), label)
                self.post_sync.enable_triggers()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 13: Reassigning Ownership..."), label)
                self.post_sync.reassign_ownership()

                # Phase 4: Validate
                self.call_from_thread(
                    self.update_display,
                    Panel(f"[{db}] Step 14: Auditing Objects..."),
                    label)
                self.validator.audit_objects()

                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 15: Comparing Row Parity..."), label)
                self.validator.compare_row_counts()

                from src.report import ReportGenerator
                self.call_from_thread(
                    self.update_display,
                    Panel(f"[{db}] Generating Final Report..."),
                    label)
                ReportGenerator(self.config).generate_html_report()

            self.call_from_thread(
                self.update_display,
                Panel(
                    "Post-Migration Pipeline Completed Successfully for all DBs",
                    title=label,
                    border_style="green"),
                label)
        except Exception as e:
            self.call_from_thread(
                self.update_display,
                Panel(
                    f"Pipeline Failed on DB {db}: {e}",
                    title=label,
                    border_style="red"),
                label)

    def _generate_config_file(self):
        import textwrap
        try:
            src_host = self.query_one("#gen_src_host", Input).value
            src_port = self.query_one("#gen_src_port", Input).value
            src_user = self.query_one("#gen_src_user", Input).value
            src_pass = self.query_one("#gen_src_pass", Input).value
            
            dest_host = self.query_one("#gen_dest_host", Input).value
            dest_port = self.query_one("#gen_dest_port", Input).value
            dest_user = self.query_one("#gen_dest_user", Input).value
            dest_pass = self.query_one("#gen_dest_pass", Input).value
            
            databases = self.query_one("#gen_databases", Input).value
            filename = self.query_one("#gen_filename", Input).value
            
            if not filename:
                filename = "config_custom.ini"
                
            content = textwrap.dedent(f"""\
                [source]
                host = {src_host}
                port = {src_port}
                user = {src_user}
                password = {src_pass}

                [destination]
                host = {dest_host}
                port = {dest_port}
                user = {dest_user}
                password = {dest_pass}

                [replication]
                publication_name = migrator_pub
                subscription_name = migrator_sub
                target_schema = public
                databases = {databases}
                loglevel = INFO
                log_file = pg_migrator.log
            """)
            
            with open(filename, "w") as fh:
                fh.write(content)
                
            self.update_display(
                Panel(
                    f"Configuration successfully generated to: {filename}",
                    title="Generate Config",
                    border_style="green"
                ),
                "Generate Config"
            )
        except Exception as e:
            self.update_display(
                Panel(
                    f"Failed to generate config: {e}",
                    title="Generate Config Error",
                    border_style="red"
                ),
                "Generate Config"
            )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config_migrator.ini")
    args = parser.parse_args()
    app = MigratorApp(args.config)
    app.run()


if __name__ == "__main__":
    main()
