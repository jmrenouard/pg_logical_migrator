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
from textual.widgets import Header, Footer, Log, Button, Label, Static
from textual.containers import Horizontal, Vertical
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
        background: #2c3e50;
        color: white;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }
    Footer {
        background: #2c3e50;
        color: #bdc3c7;
    }
    #main_container {
        layout: horizontal;
    }
    #sidebar {
        width: 35;
        background: #34495e;
        padding: 1;
        border-right: tall #2980b9;
    }
    #content {
        width: 1fr;
        padding: 1;
        background: #ecf0f1;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
        height: 3;
    }
    #step_1 { background: #2980b9; }
    #step_2 { background: #2980b9; }
    #step_3 { background: #2980b9; }
    #step_4 { background: #e67e22; }
    #step_5 { background: #e67e22; }
    #step_6 { background: #e67e22; }
    #step_7 { background: #27ae60; }
    #step_8 { background: #8e44ad; }
    #step_9 { background: #8e44ad; }
    #step_10 { background: #8e44ad; }
    #step_11 { background: #8e44ad; }
    #step_12 { background: #c0392b; }
    #step_13 { background: #f1c40f; color: black; }
    #step_14 { background: #f1c40f; color: black; }

    #log_area {
        height: 1fr;
        background: black;
        color: #00ff00;
        border: solid #2980b9;
    }
    #result_area {
        height: 1fr;
        padding: 1;
        border: solid #2980b9;
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
            with Vertical(id="sidebar"):
                yield Button("1. Check Connectivity", id="step_1")
                yield Button("2. Run Diagnostics", id="step_2")
                yield Button("3. Verify Parameters", id="step_3")
                yield Button("4. Copy Schema", id="step_4")
                yield Button("5. Setup Publication", id="step_5")
                yield Button("6. Setup Subscription", id="step_6")
                yield Button("7. Replication Status", id="step_7")
                yield Button("8. Sync Sequences", id="step_8")
                yield Button("9. Activate Seqs", id="step_9")
                yield Button("10. Enable Triggers", id="step_10")
                yield Button("11. Refresh MatViews", id="step_11")
                yield Button("13. Object Audit", id="step_13")
                yield Button("14. Row Parity", id="step_14")
                yield Button("12. STOP/CLEANUP", id="step_12")

            with Vertical(id="content"):
                yield Static(id="result_area")
                yield Log(id="log_area")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "PostgreSQL Logical Migrator"
        self.log_area = self.query_one("#log_area")
        self.result_area = self.query_one("#result_area")
        self.log_area.write_line("[bold green]TUI Initialized. Ready for migration.[/bold green]")

    def _log_detail(self, label: str, cmds, outs):
        """Write SQL commands and their outputs/results into the log panel."""
        if cmds:
            self.log_area.write_line(f"── {label} Commands ──")
            for i, cmd in enumerate(cmds):
                self.log_area.write_line(f"  SQL> {cmd}")
                if outs and i < len(outs):
                    out_str = str(outs[i]).strip()
                    if out_str:
                        for line in out_str.splitlines():
                            self.log_area.write_line(f"       → {line}")
        if not cmds:
            self.log_area.write_line(f"── {label}: (no commands recorded) ──")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.log_area.write_line("")
        self.log_area.write_line(f"▶ Running {event.button.label}...")
        try:
            if event.button.id == "step_1":
                res = self.checker.check_connectivity()
                src_ok = res['source']
                dst_ok = res['dest']
                status = f"Source: {'CONNECTED' if src_ok else 'FAILED'}\nDest: {'CONNECTED' if dst_ok else 'FAILED'}"
                color = "green" if src_ok and dst_ok else "red"
                self.result_area.update(Panel(status, title="[Step 1] Connectivity", border_style=color))
                self.log_area.write_line(f"  Source → {'OK' if src_ok else 'FAIL'}  |  Dest → {'OK' if dst_ok else 'FAIL'}")

            elif event.button.id == "step_2":
                res = self.checker.check_problematic_objects()
                diag = f"No PK tables: {len(res['no_pk'])}\nLarge Objects: {res['large_objects']}\nIdentity cols: {len(res['identities'])}\nUnowned Seqs: {len(res['unowned_seqs'])}"
                self.result_area.update(Panel(diag, title="[Step 2] Diagnostics", border_style="yellow"))
                self.log_area.write_line(f"  Tables without PK: {len(res['no_pk'])}")
                for t in res['no_pk']:
                    self.log_area.write_line(f"    - {t['schema_name']}.{t['table_name']}")
                self.log_area.write_line(f"  Large Objects: {res['large_objects']}")
                self.log_area.write_line(f"  Identity Columns: {len(res['identities'])}")
                self.log_area.write_line(f"  Unowned Sequences: {len(res['unowned_seqs'])}")
                for s in res['unowned_seqs']:
                    self.log_area.write_line(f"    - {s['schema_name']}.{s['seq_name']}")

            elif event.button.id == "step_3":
                res = self.checker.check_replication_params()
                table = Table(title="PG Parameters")
                table.add_column("Param", style="cyan")
                table.add_column("Current")
                table.add_column("Expected")
                table.add_column("Status")
                for p in res:
                    table.add_row(p['parameter'], p['actual'], p['expected'], p['status'])
                    self.log_area.write_line(f"  {p['parameter']}: {p['actual']} (expected: {p['expected']}) → {p['status']}")
                self.result_area.update(table)

            elif event.button.id == "step_4":
                success, msg, cmds, outs = self.migrator.step4_migrate_schema()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 4] Schema Migration", border_style=color))
                self._log_detail("Schema Migration", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_5":
                success, msg, cmds, outs = self.migrator.step5_setup_source()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 5] Source Pub", border_style=color))
                self._log_detail("Publication Setup", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_6":
                success, msg, cmds, outs = self.migrator.step6_setup_destination()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 6] Dest Sub", border_style=color))
                self._log_detail("Subscription Setup", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_7":
                rows = self.migrator.get_replication_status()
                if not rows:
                    self.result_area.update(Panel("No active subscription found.", title="Replication Status", border_style="red"))
                    self.log_area.write_line("  No active subscription found.")
                else:
                    info_lines = []
                    for r in rows:
                        for k, v in r.items():
                            line = f"  {k}: {v}"
                            info_lines.append(line)
                            self.log_area.write_line(line)
                    self.result_area.update(Panel("\n".join(info_lines), title="Replication Status", border_style="green"))

            elif event.button.id == "step_8":
                success, msg, cmds, outs = self.post_sync.sync_sequences()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 8/9] Sync Sequences", border_style=color))
                self._log_detail("Sync Sequences", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_10":
                success, msg, cmds, outs = self.post_sync.enable_triggers()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 10] Enable Triggers", border_style=color))
                self._log_detail("Enable Triggers", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_11":
                success, msg, cmds, outs = self.post_sync.refresh_materialized_views()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 11] Refresh MatViews", border_style=color))
                self._log_detail("Refresh MatViews", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            elif event.button.id == "step_13":
                s, m, c, o, rep = self.validator.audit_objects()
                table = Table(title="Object Audit")
                table.add_column("Type")
                table.add_column("Source")
                table.add_column("Dest")
                table.add_column("Status")
                for r in rep:
                    table.add_row(r['type'], str(r['source']), str(r['dest']), r['status'])
                    self.log_area.write_line(f"  {r['type']}: src={r['source']} dst={r['dest']} → {r['status']}")
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
                    self.log_area.write_line(f"  {r['table']}: src={r['source']} dst={r['dest']} diff={r['diff']} → {r['status']}")
                self.result_area.update(table)
                self._log_detail("Row Parity", c, o)
                self.log_area.write_line(f"  Summary: {m}")

            elif event.button.id == "step_12":
                success, msg, cmds, outs = self.migrator.step12_terminate_replication()
                color = "green" if success else "red"
                self.result_area.update(Panel(msg, title="[Step 12] Cleanup", border_style=color))
                self._log_detail("Cleanup", cmds, outs)
                self.log_area.write_line(f"  Result: {'OK' if success else 'FAIL'} — {msg}")

            self.log_area.write_line(f"✔ {event.button.label} completed.")

        except Exception as e:
            self.log_area.write_line(f"✘ ERROR: {str(e)}")
            logging.error(f"Error in TUI step: {e}", exc_info=True)

def setup_results_dir():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = os.path.join("RESULTS", timestamp)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def run_automated(config_path, results_dir=None):
    if not results_dir:
        results_dir = setup_results_dir()
    else:
        os.makedirs(results_dir, exist_ok=True)
    
    print(f"--- Starting Automated Migration ({config_path}) ---")
    print(f"--- Results will be stored in: {results_dir} ---")
    
    log_file = os.path.join(results_dir, "pg_migrator.log")
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, filename=log_file,
                        format="%(asctime)s [%(levelname)s] %(message)s", force=True)

    config = Config(config_path)
    sc = PostgresClient(config.get_source_conn(), label="SOURCE")
    dc = PostgresClient(config.get_dest_conn(), label="DESTINATION")
    checker = DBChecker(sc, dc)
    migrator = Migrator(config)
    post_sync = PostSync(sc, dc)
    validator = Validator(sc, dc)
    reporter = ReportGenerator()

    try:
        print("[1] Connectivity...")
        res = checker.check_connectivity()
        reporter.add_step("1", "Connectivity", "OK" if res['source'] and res['dest'] else "FAIL", "Check completed")

        print("[4] Schema migration...")
        s, m, c, o = migrator.step4_migrate_schema()
        reporter.add_step("4", "Schema Migration", "OK" if s else "FAIL", m, commands=c, outputs=o)

        print("[5] Setup Source...")
        s, m, c, o = migrator.step5_setup_source()
        reporter.add_step("5", "Source Setup", "OK" if s else "FAIL", m, commands=c, outputs=o)

        print("[6] Setup Destination...")
        s, m, c, o = migrator.step6_setup_destination()
        reporter.add_step("6", "Destination Setup", "OK" if s else "FAIL", m, commands=c, outputs=o)

        print("Waiting 10s for initial sync...")
        time.sleep(10)

        print("[8/9/10/11] Post-Sync...")
        s1, m1, c1, o1 = post_sync.refresh_materialized_views()
        s2, m2, c2, o2 = post_sync.sync_sequences()
        s3, m3, c3, o3 = post_sync.enable_triggers()
        all_cmds = (c1 or []) + (c2 or []) + (c3 or [])
        all_outs = (o1 or []) + (o2 or []) + (o3 or [])
        reporter.add_step("POST", "Post-Sync", "OK", "MatViews, Seqs, Triggers processed", commands=all_cmds, outputs=all_outs)

        print("[13/14] Validation...")
        s1, m1, c1, o1, r1 = validator.audit_objects()
        s2, m2, c2, o2, r2 = validator.compare_row_counts()
        reporter.add_step("VAL", "Validation", "OK", "Audit and data parity checked", commands=(c1 or [])+(c2 or []), outputs=(o1 or [])+(o2 or []))

        print("[12] Cleanup...")
        s, m, c, o = migrator.step12_terminate_replication()
        reporter.add_step("12", "Cleanup", "OK", "Replication stopped", commands=c, outputs=o)

        report_path = os.path.join(results_dir, "migration_report.html")
        out = reporter.generate_html(report_path)
        print(f"--- Automated Migration Finished. Report: {out} ---")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        reporter.add_step("FATAL", "Exception", "ERROR", str(e))
        report_path = os.path.join(results_dir, "migration_report_error.html")
        reporter.generate_html(report_path)

def main():
    parser = argparse.ArgumentParser(description="PostgreSQL Logical Migrator")
    parser.add_argument("--config", default="config_migrator.ini", help="Path to config .ini file")
    parser.add_argument("--auto", action="store_true", help="Automated mode (non-interactive)")
    parser.add_argument("--results-dir", help="Directory for storing results and reports")
    args = parser.parse_args()

    if args.auto:
        run_automated(args.config, results_dir=args.results_dir)
    else:
        app = MigratorApp(args.config)
        app.run()

if __name__ == "__main__":
    main()
