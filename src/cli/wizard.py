import os
import sys
import logging
import time
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import Config
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.report_generator import ReportGenerator
from src.cli.helpers import build_clients, print_status, setup_results_dir

console = Console()

class MigrationWizard:
    def __init__(self, config_path: str, database: Optional[str] = None):
        self.config_path = config_path
        self.database = database
        self.cfg = Config(config_path, database)
        self.results_dir = setup_results_dir()
        self.sc, self.dc = build_clients(self.cfg)
        self.checker = DBChecker(self.sc, self.dc, self.cfg)
        self.migrator = Migrator(self.cfg)
        self.post_sync = PostSync(self.sc, self.dc, self.cfg)
        self.validator = Validator(self.sc, self.dc, self.cfg)
        self.reporter = ReportGenerator()
        
        self.command_to_id = {
            'check': '1', 'diagnose': '2', 'params': '3', 
            'migrate-schema-pre-data': '4', 'setup-pub': '5', 
            'setup-sub': '6', 'repl-progress': '7', 'progress': '7', 'wait-sync': '7',
            'refresh-matviews': '8', 'sync-sequences': '9', 'terminate-repl': '10', 
            'sync-lobs': '11a', 'sync-unlogged': '11b', 'enable-triggers': '12', 
            'reassign-owner': '13', 'audit-objects': '14', 'validate-rows': '15', 
            'cleanup': '16', 'cleanup-reverse': '16', 'setup-reverse': '17'
        }

        self.steps = [
            {"id": "1", "name": "Check Connectivity", "phase": "Preparation"},
            {"id": "2", "name": "Diagnose problematic objects", "phase": "Preparation"},
            {"id": "3", "name": "Verify replication params", "phase": "Preparation"},
            {"id": "4", "name": "Migrate schema (pre-data)", "phase": "Preparation"},
            {"id": "5", "name": "Setup Publication", "phase": "Execution"},
            {"id": "6", "name": "Setup Subscription", "phase": "Execution"},
            {"id": "7", "name": "Monitor Progress", "phase": "Execution"},
            {"id": "8", "name": "Refresh MatViews", "phase": "Finalization"},
            {"id": "9", "name": "Sync Sequences", "phase": "Finalization"},
            {"id": "10", "name": "Terminate Replication + Schema (post-data)", "phase": "Finalization"},
            {"id": "11a", "name": "Sync LOBs", "phase": "Finalization"},
            {"id": "11b", "name": "Sync UNLOGGED", "phase": "Finalization"},
            {"id": "12", "name": "Enable Triggers", "phase": "Finalization"},
            {"id": "13", "name": "Reassign Owner", "phase": "Finalization"},
            {"id": "14", "name": "Audit Objects", "phase": "Validation"},
            {"id": "15", "name": "Validate Rows", "phase": "Validation"},
            {"id": "16", "name": "Cleanup", "phase": "Validation"},
            {"id": "17", "name": "Setup Reverse", "phase": "Rollback"}
        ]

    def run(self):
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]PostgreSQL Logical Migrator Wizard[/bold cyan]\n"
            "This interactive assistant will guide you through the 17-step migration process.",
            border_style="blue"
        ))
        
        # Database Selection if not specified
        if not self.database:
            dbs = self.cfg.get_databases()
            if '*' in dbs:
                with console.status("[bold green]Discovering databases..."):
                    res = self.sc.execute_query("SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';")
                    dbs = [row['datname'] for row in res]
            
            if len(dbs) > 1:
                self.database = Prompt.ask("Multiple databases found. Please select one", choices=dbs, default=dbs[0])
                self.cfg.set_override_db(self.database)
                # Rebuild clients for selected DB
                self.sc, self.dc = build_clients(self.cfg)
                self.checker = DBChecker(self.sc, self.dc, self.cfg)
                self.migrator = Migrator(self.cfg)
                self.post_sync = PostSync(self.sc, self.dc, self.cfg)
                self.validator = Validator(self.sc, self.dc, self.cfg)
            elif len(dbs) == 1:
                self.database = dbs[0]
                self.cfg.set_override_db(self.database)
            else:
                self.database = "postgres" # Fallback
        
        console.print(f"[bold]Target Database:[/] [green]{self.database}[/green]\n")
        
        while True:
            state = self._detect_state()
            self._display_summary(state)
            
            choice = Prompt.ask(
                "\n[bold yellow]What would you like to do?[/bold yellow]",
                choices=["next", "run", "status", "config", "pipeline", "exit"],
                default="next"
            )
            
            if choice == "next":
                next_step = self._get_next_logical_step(state)
                if next_step:
                    self._run_step(next_step)
                else:
                    console.print("[green]All steps completed![/green]")
            elif choice == "run":
                cmd_or_id = Prompt.ask("Enter step ID or CLI command name (e.g. 5, setup-pub)")
                step_id = self.command_to_id.get(cmd_or_id, cmd_or_id)
                step = next((s for s in self.steps if s['id'] == step_id), None)
                if step:
                    self._run_step(step)
                else:
                    console.print(f"[red]Step/Command '{cmd_or_id}' not found.[/red]")
            elif choice == "status":
                self._display_detailed_status(state)
            elif choice == "config":
                self._menu_configure_access()
            elif choice == "pipeline":
                self._run_pipeline_menu()
            elif choice == "exit":
                break

    def _menu_configure_access(self):
        console.print(Panel("Configuration Assistant", style="bold cyan"))
        
        if not os.path.exists(self.config_path):
            if Confirm.ask("Configuration file not found. Generate a default one?"):
                from src.cli.commands import cmd_generate_config
                import argparse
                out = Prompt.ask("Output path", default=self.config_path)
                args = argparse.Namespace(output=out)
                cmd_generate_config(args)
                self.config_path = out
                self.cfg = Config(out)
                console.print(f"[green]Generated {out}[/green]")

        if Confirm.ask("Configure Source Database?"):
            src_data = self._prompt_db_details("Source")
            self.cfg.update_section("source", src_data)
            
        if Confirm.ask("Configure Destination Database?"):
            dst_data = self._prompt_db_details("Destination")
            self.cfg.update_section("destination", dst_data)
            
        if Confirm.ask("Configure Replication Settings?"):
            rep_data = self._prompt_replication_details()
            self.cfg.update_section("replication", rep_data)
            
        if Confirm.ask(f"Save configuration to {self.config_path}?"):
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            self.cfg.save()
            console.print("[green]Configuration saved![/green]")
            # Re-init clients and state
            try:
                self.sc, self.dc = build_clients(self.cfg)
                self.checker = DBChecker(self.sc, self.dc, self.cfg)
                self.migrator = Migrator(self.cfg)
            except Exception as e:
                console.print(f"[yellow]Note: Could not immediately reconnect: {e}[/yellow]")

    def _prompt_db_details(self, label):
        data = {}
        # Get existing values as defaults
        existing = self.cfg.get_source_dict() if label == "Source" else self.cfg.get_dest_dict()
        
        data['host'] = Prompt.ask(f"{label} Host", default=existing.get('host', 'localhost'))
        data['port'] = Prompt.ask(f"{label} Port", default=existing.get('port', '5432'))
        data['user'] = Prompt.ask(f"{label} User", default=existing.get('user', 'postgres'))
        data['password'] = Prompt.ask(f"{label} Password", password=True, default=existing.get('password', ''))
        data['database'] = Prompt.ask(f"{label} Database", default=existing.get('database', 'postgres'))
        return data

    def _prompt_replication_details(self):
        data = {}
        existing = self.cfg.get_replication()
        
        data['target_schema'] = Prompt.ask("Target Schema(s) (comma-separated)", default=existing.get('target_schema', 'public'))
        data['publication_name'] = Prompt.ask("Publication Name", default=existing.get('publication_name', 'migrator_pub'))
        data['subscription_name'] = Prompt.ask("Subscription Name", default=existing.get('subscription_name', 'migrator_sub'))
        return data

    def _detect_state(self):
        # Basic state detection logic
        state = {
            "connectivity": {"source": False, "dest": False},
            "schema_pre": False,
            "publication": None,
            "subscription": None,
            "sync_done": False,
            "schema_post": False,
            "replication_active": False
        }
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            progress.add_task(description="Checking environment state...", total=None)
            
            # 1. Connectivity
            conn = self.checker.check_connectivity()
            state["connectivity"] = conn
            
            if conn["source"]:
                # 2. Publication
                pub_name = self.cfg.get_replication().get('publication_name', 'migrator_pub')
                res = self.sc.execute_query("SELECT pubname FROM pg_publication WHERE pubname = %s", (pub_name,))
                state["publication"] = res[0]['pubname'] if res else None
            
            if conn["dest"]:
                # 3. Subscription
                sub_name = self.cfg.get_replication().get('subscription_name', 'migrator_sub')
                res = self.dc.execute_query("SELECT subname FROM pg_subscription WHERE subname = %s", (sub_name,))
                state["subscription"] = res[0]['subname'] if res else None
                
                # 4. Schema Pre-data (check if a known table exists)
                res = self.dc.execute_query("SELECT 1 FROM information_schema.tables LIMIT 1")
                state["schema_pre"] = len(res) > 0
                
                # 5. Replication Active
                if state["subscription"]:
                    res = self.dc.execute_query("SELECT count(*) as active FROM pg_stat_subscription WHERE subname = %s", (sub_name,))
                    state["replication_active"] = res[0]['active'] > 0
                    
                    # Check sync progress
                    progress_res = self.migrator.get_initial_copy_progress()
                    if progress_res and all(t['state'] == 'ready' for t in progress_res['tables']):
                        state["sync_done"] = True
        
        return state

    def _display_summary(self, state):
        table = Table(title="Migration State Summary", box=None)
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="bold")
        
        src_stat = "[green]Connected[/]" if state["connectivity"]["source"] else "[red]Disconnected[/]"
        dst_stat = "[green]Connected[/]" if state["connectivity"]["dest"] else "[red]Disconnected[/]"
        table.add_row("Source DB", src_stat)
        table.add_row("Destination DB", dst_stat)
        
        pub_stat = f"[green]Created ({state['publication']})[/]" if state["publication"] else "[yellow]Missing[/]"
        table.add_row("Publication", pub_stat)
        
        sub_stat = f"[green]Created ({state['subscription']})[/]" if state["subscription"] else "[yellow]Missing[/]"
        table.add_row("Subscription", sub_stat)
        
        sync_stat = "[green]Finished[/]" if state["sync_done"] else "[yellow]In Progress / Not Started[/]"
        table.add_row("Data Sync", sync_stat)
        
        console.print(table)

    def _get_next_logical_step(self, state):
        if not state["connectivity"]["source"] or not state["connectivity"]["dest"]:
            return self.steps[0] # Step 1: Check
        
        if not state["schema_pre"]:
            return self.steps[3] # Step 4: Schema Pre
            
        if not state["publication"]:
            return self.steps[4] # Step 5: Pub
            
        if not state["subscription"]:
            return self.steps[5] # Step 6: Sub
            
        if not state["sync_done"]:
            return self.steps[6] # Step 7: Progress
            
        if state["replication_active"]:
            return self.steps[7] # Step 8: MatViews (Start of Cutover)
            
        # Default fallback to find first uncompleted or logically next
        return self.steps[0]

    def _display_detailed_status(self, state):
        console.print("\n[bold]Detailed Migration Health Check[/bold]")
        
        # Table of all steps with status
        table = Table(title=f"Migration Health: {self.database}")
        table.add_column("Step", justify="right")
        table.add_column("Description")
        table.add_column("Status")
        
        # Step 1
        conn_ok = state['connectivity']['source'] and state['connectivity']['dest']
        table.add_row("1", "Connectivity", "[green]OK[/]" if conn_ok else "[red]FAIL[/]")
        
        # Step 5/6
        pub_ok = state['publication'] is not None
        table.add_row("5", "Publication", "[green]OK[/]" if pub_ok else "[yellow]MISSING[/]")
        
        sub_ok = state['subscription'] is not None
        table.add_row("6", "Subscription", "[green]OK[/]" if sub_ok else "[yellow]MISSING[/]")
        
        # Step 7
        sync_ok = state['sync_done']
        table.add_row("7", "Initial Sync", "[green]COMPLETED[/]" if sync_ok else "[yellow]PENDING[/]")
        
        console.print(table)

    def _run_step(self, step):
        console.print(f"\n[bold blue]>>> Step {step['id']}: {step['name']}[/bold blue]")
        
        if not Confirm.ask(f"Do you want to execute Step {step['id']}?"):
            return
            
        try:
            rc = 0
            if step['id'] == "1":
                res = self.checker.check_connectivity()
                print_status(res['source'], f"Source: {'OK' if res['source'] else 'FAIL'}")
                print_status(res['dest'], f"Dest: {'OK' if res['dest'] else 'FAIL'}")
                rc = 0 if res['source'] and res['dest'] else 1
            elif step['id'] == "2":
                res = self.checker.check_problematic_objects()
                console.print(f"Tables without PK: {len(res['no_pk'])}")
                console.print(f"Large Objects: {res['large_objects']}")
                console.print(f"Unowned Sequences: {len(res['unowned_seqs'])}")
                console.print(f"Unlogged Tables: {len(res.get('unlogged_tables', []))}")
            elif step['id'] == "3":
                res = self.checker.check_replication_params()
                all_ok = True
                for side in ["source", "dest"]:
                    for p in res.get(side, []):
                        if p['status'] == "FAIL": all_ok = False
                        console.print(f"  [{side.upper()}] {p['parameter']}: {p['actual']} -> {p['status']}")
                rc = 0 if all_ok else 1
            elif step['id'] == "4":
                s, m, c, o = self.migrator.step4a_migrate_schema_pre_data(drop_dest=False)
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "5":
                s, m, c, o = self.migrator.step5_setup_source()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "6":
                s, m, c, o = self.migrator.step6_setup_destination()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "7":
                self.migrator.wait_for_sync()
            elif step['id'] == "8":
                s, m, c, o = self.post_sync.refresh_materialized_views()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "9":
                s, m, c, o = self.post_sync.sync_sequences()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "10":
                s, m, c, o = self.migrator.step10_terminate_replication()
                print_status(s, f"Termination: {m}")
                s2, m2, c2, o2 = self.migrator.step4b_migrate_schema_post_data()
                print_status(s2, f"Schema Post: {m2}")
                rc = 0 if s and s2 else 1
            elif step['id'] == "11a":
                s, m, c, o = self.migrator.sync_large_objects()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "11b":
                s, m, c, o = self.migrator.sync_unlogged_tables()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "12":
                s, m, c, o = self.post_sync.enable_triggers()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "13":
                s, m, c, o = self.post_sync.reassign_ownership()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "14":
                s, m, c, o, rep = self.validator.audit_objects()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "15":
                s, m, c, o, rep = self.validator.compare_row_counts()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "16":
                s, m, c, o = self.migrator.cleanup_reverse_replication()
                print_status(s, m)
                rc = 0 if s else 1
            elif step['id'] == "17":
                s, m, c, o = self.migrator.setup_reverse_replication()
                print_status(s, m)
                rc = 0 if s else 1
            
            if rc == 0:
                console.print(f"\n[green]Step {step['id']} completed successfully.[/green]")
            else:
                console.print(f"\n[red]Step {step['id']} failed.[/red]")
                
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

    def _run_pipeline_menu(self):
        console.print(Panel("Shortcut Pipelines", style="bold magenta"))
        choice = Prompt.ask("Choose pipeline", choices=["init-replication", "post-migration", "back"], default="init-replication")
        
        import argparse
        if choice == "init-replication":
            from src.cli.pipelines import cmd_init_replication
            drop = Confirm.ask("Drop destination database if it exists? (--drop-dest)", default=False)
            wait = Confirm.ask("Wait for initial synchronization to complete? (--wait)", default=True)
            args = argparse.Namespace(
                config=self.config_path, 
                database=self.database, 
                results_dir=self.results_dir, 
                loglevel="INFO", 
                dry_run=False, 
                drop_dest=drop, 
                wait=wait, 
                sync_delay=3600
            )
            console.print("[yellow]Starting init-replication pipeline...[/yellow]")
            cmd_init_replication(args)
        elif choice == "post-migration":
            from src.cli.pipelines import cmd_post_migration
            args = argparse.Namespace(
                config=self.config_path, 
                database=self.database, 
                results_dir=self.results_dir, 
                loglevel="INFO", 
                dry_run=False
            )
            console.print("[yellow]Starting post-migration pipeline...[/yellow]")
            cmd_post_migration(args)

def cmd_wizard(args):
    wizard = MigrationWizard(args.config, getattr(args, "database", None))
    wizard.run()
    return 0
