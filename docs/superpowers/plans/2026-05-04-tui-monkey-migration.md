# TUI Monkey Migration E2E Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and execute an E2E test that runs a full PostgreSQL migration via the TUI while subjecting the interface to random "monkey" stress (random inputs/clicks).

**Architecture:** Use `textual.pilot` to automate the `MigratorApp`. The test will trigger the automated pipelines and simultaneously run a background "monkey" task that generates random UI events. After completion, it will verify database parity.

**Tech Stack:** Python, Textual (TUI framework), Pytest, Psycopg2 (Postgres client).

---

### Task 1: Create the TUI Monkey Migration Test

**Files:**
- Create: `tests/e2e/test_tui_monkey_migration.py`

- [ ] **Step 1: Write the E2E monkey test logic**

```python
import os
import random
import string
import asyncio
import pytest
from src.tui import MigratorApp
from src.db import PostgresClient
from src.config import Config
from textual.widgets import Button, Select, Input, TabbedContent, TabPane, Static

@pytest.mark.asyncio
async def test_tui_monkey_migration_e2e():
    config_path = "tests/test_config.ini"
    if not os.path.exists(config_path):
        pytest.skip("tests/test_config.ini not found. Run 'make env-up' first.")

    app = MigratorApp(config_path)
    
    # Track if we should keep monkeying
    monkey_active = True

    async def monkey_stress(pilot):
        actions = ["press_tab", "press_enter", "press_key", "click_button", "switch_tab", "type_random"]
        keys = ["down", "up", "left", "right", "pageup", "pagedown", "home", "end", "space", "escape"]
        
        while monkey_active:
            action = random.choice(actions)
            try:
                if action == "press_tab":
                    await pilot.press("tab" if random.random() > 0.3 else "shift+tab")
                elif action == "press_enter":
                    await pilot.press("enter")
                elif action == "press_key":
                    await pilot.press(random.choice(keys))
                elif action == "click_button":
                    buttons = [b for b in app.query(Button) if b.visible and b.enabled]
                    if buttons:
                        await pilot.click(random.choice(buttons))
                elif action == "switch_tab":
                    tabbed_contents = list(app.query(TabbedContent))
                    if tabbed_contents:
                        tc = tabbed_contents[0]
                        panes = [p for p in tc.query(TabPane) if p.id]
                        if panes:
                            tc.active = random.choice(panes).id
                elif action == "type_random":
                    inputs = [i for i in app.query(Input) if i.visible and i.enabled]
                    if inputs:
                        inp = random.choice(inputs)
                        inp.focus()
                        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
                        await pilot.type(random_str)
            except Exception:
                pass
            await asyncio.sleep(0.1)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        
        # 1. Switch to Automation tab
        tabbed_content = app.query_one(TabbedContent)
        # Find the pane with INIT PIPELINE
        for pane in tabbed_content.query(TabPane):
             if pane.query("#cmd_init"):
                 tabbed_content.active = pane.id
                 break
        await pilot.pause(0.1)

        # 2. Start Monkey in background
        monkey_task = asyncio.create_task(monkey_stress(pilot))

        # 3. Start INIT PIPELINE
        await pilot.click("#cmd_init")
        
        # 4. Wait for INIT PIPELINE to complete (look for "Pipeline Completed" in display)
        # Timeout 120s
        for _ in range(120):
            display = app.query_one("#main_display", Static)
            if "Pipeline Completed Successfully" in str(display.renderable):
                break
            await pilot.pause(1.0)
        else:
             monkey_active = False
             await monkey_task
             pytest.fail("INIT PIPELINE timed out or failed")

        # 5. Start POST PIPELINE
        await pilot.click("#cmd_post")

        # 6. Wait for POST PIPELINE to complete
        # Timeout 120s
        for _ in range(120):
            display = app.query_one("#main_display", Static)
            if "Post-Migration Pipeline Completed Successfully" in str(display.renderable):
                break
            await pilot.pause(1.0)
        else:
             monkey_active = False
             await monkey_task
             pytest.fail("POST PIPELINE timed out or failed")

        # Stop monkey
        monkey_active = False
        await monkey_task

        # Final verification
        cfg = Config(config_path)
        sc = PostgresClient(cfg.get_source_conn(), label="SOURCE")
        dc = PostgresClient(cfg.get_dest_conn(), label="DESTINATION")

        s_count = sc.execute_query("SELECT count(*) FROM actor;")[0]['count']
        d_count = dc.execute_query("SELECT count(*) FROM actor;")[0]['count']
        
        assert s_count > 0
        assert s_count == d_count
        print(f"Monkey test successful! Migrated {s_count} actors.")

```

- [ ] **Step 2: Run the test**

Run: `pytest -vv tests/e2e/test_tui_monkey_migration.py`
Expected: PASS

### Task 2: Data Consistency Verification

- [ ] **Step 1: Check multiple tables**

Run a script to verify row counts for all tables in `pagila` schema.

```python
import os
from src.config import Config
from src.db import PostgresClient

def verify_all_tables():
    config_path = "tests/test_config.ini"
    cfg = Config(config_path)
    sc = PostgresClient(cfg.get_source_conn())
    dc = PostgresClient(cfg.get_dest_conn())
    
    tables = sc.execute_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")
    
    all_match = True
    for t in tables:
        table_name = t['table_name']
        s_count = sc.execute_query(f"SELECT count(*) FROM \"{table_name}\";")[0]['count']
        d_count = dc.execute_query(f"SELECT count(*) FROM \"{table_name}\";")[0]['count']
        if s_count != d_count:
            print(f"Mismatch in {table_name}: Source={s_count}, Dest={d_count}")
            all_match = False
        else:
            print(f"Table {table_name} matches: {s_count} rows")
    
    return all_match

if __name__ == "__main__":
    if verify_all_tables():
        print("ALL TABLES MATCH")
    else:
        print("DATA MISMATCH DETECTED")
        exit(1)
```

- [ ] **Step 2: Run verification script**

Run: `python3 -c "import os; from src.config import Config; from src.db import PostgresClient; cfg=Config('tests/test_config.ini'); sc=PostgresClient(cfg.get_source_conn()); dc=PostgresClient(cfg.get_dest_conn()); tables=sc.execute_query(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';\"); all_match=True; [print(f\"Table {t['table_name']} matches: {sc.execute_query(f'SELECT count(*) FROM \"{t[\"table_name\"]}\";')[0]['count']} rows\") if sc.execute_query(f'SELECT count(*) FROM \"{t[\"table_name\"]}\";')[0]['count'] == dc.execute_query(f'SELECT count(*) FROM \"{t[\"table_name\"]}\";')[0]['count'] else (print(f\"Mismatch in {t['table_name']}\"), globals().update(all_match=False)) for t in tables]; exit(0 if all_match else 1)"`
