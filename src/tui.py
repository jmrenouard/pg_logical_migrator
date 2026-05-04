import time
from datetime import datetime
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group
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
        padding: 1;
        height: auto;
    }
    .form_row {
        layout: horizontal;
        height: 3;
        margin-bottom: 1;
    }
    .form_row Label {
        width: 14;
        content-align: left middle;
    }
    .form_row Input {
        width: 1fr;
        min-width: 10;
        margin-right: 1;
    }
    .form_row Select {
        width: 1fr;
        min-width: 20;
        margin-right: 1;
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
            try:
                sc = PostgresClient(self.config.get_source_conn())
                res = sc.execute_query("SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';")
                self.databases = [row['datname'] for row in res]
                sc.close()
            except Exception as e:
                # If connection fails, we fall back to a safe default or empty list
                # This allows the user to fix the config in the TUI
                import logging
                logging.error(f"Failed to fetch databases from source: {e}")
                self.databases = ['postgres']
            
        # Default to first DB
        self.current_db = self.databases[0] if self.databases else 'postgres'
        self._init_backend_for_db(self.current_db)
        self.history_data = []

    def _init_backend_for_db(self, db_name):
        if db_name:
            self.config.set_override_db(db_name)
        
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
                    if self.databases:
                        db_options = [(db, db) for db in self.databases]
                        db_val = self.databases[0]
                    else:
                        db_options = [("None", "")]
                        db_val = ""
                    yield Select(db_options, value=db_val, id="opt_database")
                    yield Checkbox("Use Stats", id="opt_use_stats")
                    target_list = ", ".join(self.config.get_target_schemas())
                    yield Label(f" [dim]Schemas: {target_list}[/dim]")

                with Container(id="action_area"):
                    with TabbedContent():
                        with TabPane("1. Prepare"):
                            with Horizontal(classes="btn_group"):
                                yield Button("Config", id="step_show_config", classes="btn-pre")
                                yield Button("Drop Dest", id="step_drop_dest", classes="btn-pre")
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
                                with Vertical(id="config_form"):
                                    with Horizontal(classes="form_row"):
                                        yield Label("Source:")
                                        yield Input(placeholder="Host", value="localhost", id="gen_src_host")
                                        yield Input(placeholder="Port", value="5432", id="gen_src_port")
                                        yield Input(placeholder="User", value="postgres", id="gen_src_user")
                                        yield Input(placeholder="Password", password=True, id="gen_src_pass")
                                    
                                    with Horizontal(classes="form_row"):
                                        yield Label("Dest:")
                                        yield Input(placeholder="Host", value="localhost", id="gen_dest_host")
                                        yield Input(placeholder="Port", value="5433", id="gen_dest_port")
                                        yield Input(placeholder="User", value="postgres", id="gen_dest_user")
                                        yield Input(placeholder="Password", password=True, id="gen_dest_pass")
                                    
                                    with Horizontal(classes="form_row"):
                                        yield Label("Databases:")
                                        yield Input(placeholder="Databases (* or comma-separated)", value="*", id="gen_databases")
                                        yield Label("Schemas:")
                                        yield Input(placeholder="Schemas (* or comma-separated)", value="public", id="gen_target_schema")
                                    with Horizontal(classes="form_row"):
                                        yield Label("Out Config:")
                                        yield Input(placeholder="Output Filename", value="config_migrator.ini", id="gen_filename")
                                        yield Label("Log Level:")
                                        yield Input(placeholder="Log Level (INFO, DEBUG)", value="INFO", id="gen_loglevel")
                                with Horizontal(classes="btn_group"):
                                    yield Button("Generate Config", id="cmd_generate_config", classes="btn-auto")

                        with TabPane("💻 SQL Shell"):
                            with VerticalScroll():
                                yield Label("Execute SQL Queries on Source or Destination", classes="pane_header")
                                with Horizontal(classes="form_row"):
                                    yield Label("Target:")
                                    yield Select([("Source", "source"), ("Destination", "dest")], value="source", id="sql_target_select")
                                yield Input(placeholder="Enter SQL Query (e.g. SELECT version();)", id="sql_query_input")
                                with Horizontal(classes="btn_group"):
                                    yield Button("Execute SQL", id="cmd_execute_sql", classes="btn-auto")

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

    def _format_action_result(self, db, label, success, msg, cmds=None, outputs=None):
        
        status_table = Table(title=f"[{db}] {label}")
        status_table.add_column("Status", style="green" if success else "red")
        status_table.add_column("Message")
        status_table.add_row("OK" if success else "ERROR", str(msg))
        
        renderables = [status_table]
        
        if cmds and isinstance(cmds, list):
            cmd_table = Table(title="Executed Commands & Results")
            cmd_table.add_column("Command", style="cyan")
            cmd_table.add_column("Output")
            if not outputs:
                outputs = [""] * len(cmds)
            for c, o in zip(cmds, outputs):
                cmd_table.add_row(str(c), str(o) if o else "Executed")
            renderables.append(cmd_table)
            
        return Group(*renderables)

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
            dbs_to_run = [selected_db] if selected_db else []
            
            if not dbs_to_run:
                self.update_display(Panel("No database selected.", border_style="red"), label)
                return
                
            for db in dbs_to_run:
                self._init_backend_for_db(db)
                
                if btn_id == "step_show_config":
                    table = Table(title=f"[{db}] Configuration")
                    table.add_column("Property", style="cyan")
                    table.add_column("Value")
                    
                    table.add_row("Config File", str(self.config.config_path))
                    table.add_row("Databases", str(self.config.get_databases()))
                    table.add_row("Target Schemas", str(self.config.get_target_schemas(db)))
                    table.add_row("Log Level", str(self.config.config.get('replication', 'loglevel', fallback='INFO')))
                    
                    src_dict = self.config.get_source_dict()
                    src_pass = "***" if src_dict.get('password') else "None"
                    table.add_row("Source Connection", f"{src_dict.get('user')}@{src_dict.get('host')}:{src_dict.get('port')}/{db} (pw: {src_pass})")
                    
                    dst_dict = self.config.get_dest_dict()
                    dst_pass = "***" if dst_dict.get('password') else "None"
                    table.add_row("Dest Connection", f"{dst_dict.get('user')}@{dst_dict.get('host')}:{dst_dict.get('port')}/{db} (pw: {dst_pass})")
                    
                    status_res = self._format_action_result(db, "Show Config", True, "Configuration loaded.")
                    self.update_display(Group(status_res, table), label)

                elif btn_id == "step_1":
                    res = self.checker.check_connectivity()
                    success = res['source'] and res['dest']
                    src_ok = '[green]OK[/]' if res['source'] else '[red]FAIL[/]'
                    dst_ok = '[green]OK[/]' if res['dest'] else '[red]FAIL[/]'
                    msg = f"Source: {src_ok} | Dest: {dst_ok}"
                    self.update_display(self._format_action_result(db, "Check Connectivity", success, msg), label)

                elif btn_id == "step_2":
                    res = self.checker.check_problematic_objects()
                    table = Table(title="Diagnostics Summary")
                    table.add_column("Object Type", style="cyan")
                    table.add_column("Count", justify="right")
                    table.add_row("Tables without PK", str(len(res['no_pk'])))
                    table.add_row("Large Objects (LOBs)", str(res['large_objects']))
                    table.add_row("Unowned Sequences", str(len(res['unowned_seqs'])))
                    table.add_row("Unlogged Tables", str(len(res.get('unlogged_tables', []))))
                    
                    status_res = self._format_action_result(db, "Diagnose Objects", True, "Diagnostics completed.")
                    renderables = [status_res, table]
                    
                    if res.get('top_tables'):
                        top_table = Table(title="Top 5 Tables by Estimated Rows")
                        top_table.add_column("Schema")
                        top_table.add_column("Table Name")
                        top_table.add_column("Estimated Rows", justify="right")
                        for t in res['top_tables']:
                            top_table.add_row(t['schema_name'], t['table_name'], f"{t['estimated_count']:,}")
                        renderables.append(top_table)
                        
                    self.update_display(Group(*renderables), label)

                elif btn_id in ("step_3", "cmd_apply_params"):
                    apply = (btn_id == "cmd_apply_params")
                    res = self.checker.check_replication_params(apply_source=apply, apply_dest=apply)
                    table = Table(title="PostgreSQL Parameters")
                    table.add_column("Instance")
                    table.add_column("Parameter")
                    table.add_column("Value")
                    table.add_column("Status")
                    all_ok = True
                    for side in ["source", "dest"]:
                        for p in res.get(side, []):
                            color = "green" if p['status'] == "OK" else "yellow" if p['status'] == "PENDING RESTART" else "red"
                            if p['status'] == "FAIL":
                                all_ok = False
                            table.add_row(side.upper(), p['parameter'], str(p['actual']), f"[{color}]{p['status']}[/]")
                    
                    action_name = "Apply Parameters" if apply else "Check Parameters"
                    msg = "Parameters checked/applied." if all_ok else "Some parameters failed or require restart."
                    status_res = self._format_action_result(db, action_name, all_ok, msg)
                    self.update_display(Group(status_res, table), label)

                elif btn_id == "step_drop_dest":
                    s, m, c, o = self.migrator.drop_recreate_dest_db()
                    self.update_display(self._format_action_result(db, "Drop Dest Database", s, m, c, o), label)

                elif btn_id == "step_4":
                    s, m, c, o = self.migrator.step4a_migrate_schema_pre_data(drop_dest=False)
                    self.update_display(self._format_action_result(db, "Schema Pre-Data", s, m, c, o), label)

                elif btn_id == "step_5":
                    s, m, c, o = self.migrator.step5_setup_source()
                    self.update_display(self._format_action_result(db, "Setup Publication", s, m, c, o), label)

                elif btn_id == "step_6":
                    self.update_display(
                        Panel(
                            "Starting subscription creation in background...",
                            title="Subscription"),
                        label=None) # Don't log this to history
                    self._run_sub_async(db)

                elif btn_id == "cmd_progress":
                    progress = self.migrator.get_initial_copy_progress()
                    if not progress:
                        self.update_display(self._format_action_result(db, "Sync Progress", False, "No active replication progress found."), label)
                    else:
                        table = Table(title=f"[{db}] Sync Progress")
                        table.add_column("Table")
                        table.add_column("State")
                        table.add_column("Progress")
                        for t in progress['tables']:
                            table.add_row(t['table_name'], t['state'], f"{t['percent']}%")
                        status_res = self._format_action_result(db, "Sync Progress", True, "Progress fetched.")
                        self.update_display(Group(status_res, table), label)

                elif btn_id == "step_8":
                    s, m, c, o = self.post_sync.refresh_materialized_views()
                    self.update_display(self._format_action_result(db, "MatViews Refresh", s, m, c, o), label)

                elif btn_id == "step_9":
                    s, m, c, o = self.post_sync.sync_sequences()
                    self.update_display(self._format_action_result(db, "Sequences Sync", s, m, c, o), label)

                elif btn_id == "step_10":
                    s, m, c, o = self.migrator.step10_terminate_replication()
                    self.update_display(self._format_action_result(db, "Terminate Replication", s, m, c, o), f"{label} (Terminate)")
                    
                    s2, m2, c2, o2 = self.migrator.step4b_migrate_schema_post_data()
                    self.update_display(self._format_action_result(db, "Schema Post-Data", s2, m2, c2, o2), f"{label} (Schema Post)")

                elif btn_id == "step_11":
                    s, m, c, o = self.migrator.sync_large_objects()
                    self.update_display(self._format_action_result(db, "Sync Large Objects", s, m, c, o), label)

                elif btn_id == "step_11b":
                    s, m, c, o = self.migrator.sync_unlogged_tables()
                    self.update_display(self._format_action_result(db, "Sync UNLOGGED Tables", s, m, c, o), label)

                elif btn_id == "step_12":
                    s, m, c, o = self.post_sync.enable_triggers()
                    self.update_display(self._format_action_result(db, "Enable Triggers", s, m, c, o), label)

                elif btn_id == "step_13":
                    s, m, c, o = self.post_sync.reassign_ownership()
                    self.update_display(self._format_action_result(db, "Reassign Ownership", s, m, c, o), label)

                elif btn_id == "step_14":
                    s, m, c, o, rep = self.validator.audit_objects()
                    table = Table(title=f"[{db}] Object Audit")
                    table.add_column("Type")
                    table.add_column("Source")
                    table.add_column("Dest")
                    table.add_column("Status")
                    for r in rep:
                        table.add_row(r['type'], str(r['source']), str(r['dest']), r['status'])
                    res = self._format_action_result(db, "Audit Results", s, m, c, o)
                    self.update_display(Group(res, table), label)

                elif btn_id == "step_15":
                    use_stats = self.query_one("#opt_use_stats", Checkbox).value
                    s, m, c, o, rep = self.validator.compare_row_counts(use_stats=use_stats)
                    table = Table(title=f"[{db}] Row Count Parity")
                    table.add_column("Table")
                    table.add_column("Diff")
                    table.add_column("Status")
                    for r in rep[:40]:
                        color = "green" if r['status'] == "OK" else "red"
                        table.add_row(r['table'], str(r['diff']), f"[{color}]{r['status']}[/]")
                    res = self._format_action_result(db, "Parity Results", s, m, c, o)
                    self.update_display(Group(res, table), label)

                elif btn_id == "step_16":
                    s, m, c, o = self.migrator.cleanup_reverse_replication()
                    self.update_display(self._format_action_result(db, "Cleanup Reverse Replication", s, m, c, o), label)

                elif btn_id == "step_17":
                    s, m, c, o = self.migrator.setup_reverse_replication()
                    self.update_display(self._format_action_result(db, "Setup Reverse Replication", s, m, c, o), label)

                elif btn_id == "cmd_init":
                    self._run_init_pipeline(dbs_to_run)
                    return  # Skip the rest of the loop since the worker handles it

                elif btn_id == "cmd_post":
                    self._run_post_pipeline(dbs_to_run)
                    return  # Skip the rest of the loop since the worker handles it

                elif btn_id == "cmd_generate_config":
                    self._generate_config_file()
                    return

                elif btn_id == "cmd_execute_sql":
                    self._execute_sql_shell(dbs_to_run)
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
    def _run_sub_async(self, db: str):
        label = "Step 6: Sub"
        try:
            s, m, c, o = self.migrator.step6_setup_destination()
            self.call_from_thread(
                self.update_display,
                self._format_action_result(db, "Subscription Result", s, m, c, o),
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
            for db in dbs_to_run:
                self._init_backend_for_db(db)
                self.call_from_thread(self.update_display, Panel(f"Processing DB: {db} (Init)"), None)
                
                s, m, c, o = self.migrator.step4a_migrate_schema_pre_data(drop_dest=False)
                self.call_from_thread(self.update_display, self._format_action_result(db, "Schema Pre-Data", s, m, c, o), f"[{db}] Step 4")
                time.sleep(1.5)
                
                s, m, c, o = self.migrator.step5_setup_source()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Setup Source", s, m, c, o), f"[{db}] Step 5")
                time.sleep(1.5)
                
                s, m, c, o = self.migrator.step6_setup_destination()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Setup Destination", s, m, c, o), f"[{db}] Step 6")
                time.sleep(1.5)
                
                self.call_from_thread(self.update_display, Panel(f"[{db}] Step 7: Waiting for final sync..."), None)
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
            db = "Unknown"
            for db in dbs_to_run:
                self._init_backend_for_db(db)
                self.call_from_thread(self.update_display, Panel(f"Processing DB: {db} (Post-Migration)"), label)

                # Phase 3: Finalize
                self.call_from_thread(self.update_display, Panel(
                    f"[{db}] Step 7: Waiting for final sync..."), None)
                self.migrator.wait_for_sync(show_progress=False)

                s, m, c, o = self.post_sync.refresh_materialized_views()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Refresh MatViews", s, m, c, o), f"[{db}] Step 8")
                time.sleep(1.5)

                s, m, c, o = self.post_sync.sync_sequences()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Sync Sequences", s, m, c, o), f"[{db}] Step 9")
                time.sleep(1.5)

                s, m, c, o = self.migrator.step10_terminate_replication()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Terminate Replication", s, m, c, o), f"[{db}] Step 10a")
                time.sleep(1.5)
                
                s, m, c, o = self.migrator.step4b_migrate_schema_post_data()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Schema Post-Data", s, m, c, o), f"[{db}] Step 10b")
                time.sleep(1.5)

                s, m, c, o = self.migrator.sync_large_objects()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Sync Large Objects", s, m, c, o), f"[{db}] Step 11a")
                time.sleep(1.5)

                s, m, c, o = self.migrator.sync_unlogged_tables()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Sync UNLOGGED Tables", s, m, c, o), f"[{db}] Step 11b")
                time.sleep(1.5)

                s, m, c, o = self.post_sync.enable_triggers()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Enable Triggers", s, m, c, o), f"[{db}] Step 12")
                time.sleep(1.5)

                s, m, c, o = self.post_sync.reassign_ownership()
                self.call_from_thread(self.update_display, self._format_action_result(db, "Reassign Ownership", s, m, c, o), f"[{db}] Step 13")
                time.sleep(1.5)

                # Phase 4: Validate
                s, m, c, o, rep = self.validator.audit_objects()
                table = Table(title=f"[{db}] Object Audit")
                table.add_column("Type")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep:
                    table.add_row(r['type'], str(r['source']), str(r['dest']), r['status'])
                res = self._format_action_result(db, "Audit Results", s, m, c, o)
                self.call_from_thread(self.update_display, Group(res, table), f"[{db}] Step 14")

                s, m, c, o, rep = self.validator.compare_row_counts(use_stats=True)
                table = Table(title=f"[{db}] Row Count Parity")
                table.add_column("Table")
                table.add_column("Diff")
                table.add_column("Status")
                for r in rep[:40]:
                    color = "green" if r['status'] == "OK" else "red"
                    table.add_row(r['table'], str(r['diff']), f"[{color}]{r['status']}[/]")
                res = self._format_action_result(db, "Parity Results", s, m, c, o)
                self.call_from_thread(self.update_display, Group(res, table), f"[{db}] Step 15")

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
            target_schema = self.query_one("#gen_target_schema", Input).value
            loglevel = self.query_one("#gen_loglevel", Input).value
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
                target_schema = {target_schema}
                databases = {databases}
                loglevel = {loglevel}
                log_file = pg_migrator.log
            """)
            
            with open(filename, "w") as fh:
                fh.write(content)
                
            try:
                from src.config import Config
                self.config = Config(filename)
                self.sub_title = f"Config: {self.config.config_path}"
                reload_msg = f"\n[green]Config reloaded successfully from {filename}.[/green]"
            except Exception as e:
                reload_msg = f"\n[red]Failed to reload config from {filename}: {e}[/red]"
                
            self.update_display(
                Panel(
                    f"Configuration successfully generated to: {filename}{reload_msg}",
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

    @work(exclusive=True, thread=True)
    def _execute_sql_shell(self, dbs_to_run):
        label = "Execute SQL"
        try:
            target = self.query_one("#sql_target_select", Select).value
            query = self.query_one("#sql_query_input", Input).value
            
            if not query:
                self.call_from_thread(self.update_display, Panel("No query provided.", title=label, border_style="red"), label)
                return
                
            self.call_from_thread(self.update_display, Panel(f"Executing on {target}: {query}\n", title=label, border_style="blue"), label)
            
            import psycopg2
            from rich.table import Table
            from rich.panel import Panel
            from rich.console import Group
            
            results = []
            
            for db in dbs_to_run:
                self._init_backend_for_db(db)
                try:
                    conn_dict = self.migrator.source_conn if target == "source" else self.migrator.dest_conn
                    with psycopg2.connect(**conn_dict) as conn:
                        with conn.cursor() as cur:
                            cur.execute(query)
                            if cur.description:
                                columns = [desc[0] for desc in cur.description]
                                table = Table(title=f"[{db}] Result ({target})")
                                for col in columns:
                                    table.add_column(col)
                                rows = cur.fetchall()
                                for row in rows:
                                    table.add_row(*[str(val) for val in row])
                                results.append(table)
                            else:
                                results.append(Panel(f"Query executed successfully. Rows affected: {cur.rowcount}", title=f"[{db}] Result ({target})"))
                except Exception as e:
                    results.append(Panel(f"Error: {e}", title=f"[{db}] Error ({target})", border_style="red"))
                    
            self.call_from_thread(self.update_display, Group(*results), label)
            
        except Exception as e:
            self.call_from_thread(self.update_display, Panel(f"Error in SQL Shell: {e}", title=label, border_style="red"), label)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config_migrator.ini")
    args = parser.parse_args()
    app = MigratorApp(args.config)
    app.run()


if __name__ == "__main__":
    main()
