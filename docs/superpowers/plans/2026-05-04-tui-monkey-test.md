# TUI Monkey Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an automated monkey test for the TUI to detect crashes and stability issues.

**Architecture:** Use `App.run_test()` and `pilot` to perform 100+ random actions on the TUI while mocking all database and backend interactions.

**Tech Stack:** Python, Pytest, Textual, unittest.mock

---

### Task 1: Setup Mocks and Test Boilerplate

**Files:**
- Create: `tests/integration/test_tui_monkey.py`

- [ ] **Step 1: Write the boilerplate for the monkey test with mocks**

```python
import os
import random
import pytest
from unittest.mock import MagicMock, patch
from src.tui import MigratorApp
from textual.widgets import Button, Select, Input, TabPane

@pytest.fixture
def mock_backend():
    with patch("src.tui.PostgresClient") as mock_pg, \
         patch("src.tui.DBChecker") as mock_checker, \
         patch("src.tui.Migrator") as mock_migrator, \
         patch("src.tui.PostSync") as mock_post_sync, \
         patch("src.tui.Validator") as mock_validator, \
         patch("src.tui.Config") as mock_config:
        
        # Setup mock config
        mock_config_inst = mock_config.return_value
        mock_config_inst.get_databases.return_value = ["test_db_1", "test_db_2"]
        mock_config_inst.get_source_conn.return_value = {}
        mock_config_inst.get_dest_conn.return_value = {}
        mock_config_inst.get_target_schemas.return_value = ["public"]
        mock_config_inst.get_source_dict.return_value = {"user": "u", "host": "h", "port": "5432"}
        mock_config_inst.get_dest_dict.return_value = {"user": "u", "host": "h", "port": "5432"}
        
        # Setup mock checker
        mock_checker_inst = mock_checker.return_value
        mock_checker_inst.check_connectivity.return_value = {"source": True, "dest": True}
        mock_checker_inst.check_problematic_objects.return_value = {
            "no_pk": [], "large_objects": 0, "unowned_seqs": [], "unlogged_tables": [], "top_tables": []
        }
        mock_checker_inst.check_replication_params.return_value = {"source": [], "dest": []}
        
        # Setup mock migrator
        mock_migrator_inst = mock_migrator.return_value
        mock_migrator_inst.drop_recreate_dest_db.return_value = (True, "Dropped", [], [])
        mock_migrator_inst.step4a_migrate_schema_pre_data.return_value = (True, "Pre-data done", [], [])
        mock_migrator_inst.step5_setup_source.return_value = (True, "Source setup", [], [])
        mock_migrator_inst.step6_setup_destination.return_value = (True, "Dest setup", [], [])
        mock_migrator_inst.get_initial_copy_progress.return_value = {"tables": []}
        
        yield {
            "pg": mock_pg,
            "checker": mock_checker,
            "migrator": mock_migrator,
            "post_sync": mock_post_sync,
            "validator": mock_validator,
            "config": mock_config
        }

@pytest.mark.asyncio
async def test_tui_monkey_run(mock_backend):
    config_path = "dummy_config.ini"
    app = MigratorApp(config_path)
    
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        # We'll add monkey logic in Task 2
        assert app.title == "pg_logical_migrator"
```

- [ ] **Step 2: Run test to verify it passes (initial setup)**

Run: `pytest tests/integration/test_tui_monkey.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tui_monkey.py
git commit -m "test: setup tui monkey test boilerplate and mocks"
```

---

### Task 2: Implement Monkey Logic

**Files:**
- Modify: `tests/integration/test_tui_monkey.py`

- [ ] **Step 1: Implement the random action loop**

```python
import random
import string

@pytest.mark.asyncio
async def test_tui_monkey_run(mock_backend):
    config_path = "dummy_config.ini"
    app = MigratorApp(config_path)
    
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        
        iterations = 150
        actions = ["press_tab", "press_enter", "press_key", "click_button", "switch_tab", "type_random"]
        
        keys = ["down", "up", "left", "right", "pageup", "pagedown", "home", "end", "space", "escape"]
        
        for i in range(iterations):
            action = random.choice(actions)
            
            try:
                if action == "press_tab":
                    await pilot.press("tab" if random.random() > 0.3 else "shift+tab")
                elif action == "press_enter":
                    await pilot.press("enter")
                elif action == "press_key":
                    await pilot.press(random.choice(keys))
                elif action == "click_button":
                    buttons = list(app.query(Button))
                    if buttons:
                        btn = random.choice(buttons)
                        if btn.visible and btn.enabled:
                            await pilot.click(btn)
                elif action == "switch_tab":
                    from textual.widgets import TabbedContent
                    tabbed_content = app.query_one(TabbedContent)
                    tabs = list(tabbed_content.query(TabPane))
                    if tabs:
                        target_tab = random.choice(tabs)
                        # Textual pilot doesn't have a direct way to switch tabs easily via click sometimes
                        # if the tab label isn't easily clickable, but we can try to press keys or use tabbed_content.active
                        tabbed_content.active = target_tab.id
                elif action == "type_random":
                    # Find an input if focused or just type randomly
                    focused = app.focused
                    if isinstance(focused, Input):
                        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
                        await pilot.type(random_str)
                
                await pilot.pause(0.01) # Small pause to allow UI to react
            except Exception as e:
                # Some errors like "Widget not found" might be okay if UI changed
                # but we want to catch actual app crashes.
                # Textual's run_test should catch exceptions in the app itself.
                pass
            
            if i % 50 == 0:
                 await pilot.pause(0.1) # Bigger pause every 50 iterations

        assert app.is_running
```

- [ ] **Step 2: Run the monkey test**

Run: `pytest tests/integration/test_tui_monkey.py -v`
Expected: PASS (and it should take a few seconds)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tui_monkey.py
git commit -m "test: implement monkey test logic for TUI"
```

---

### Task 3: Final Validation and Cleanup

- [ ] **Step 1: Run all integration tests to ensure no regressions**

Run: `pytest tests/integration/ -v`

- [ ] **Step 2: Document findings**

If any crashes were found, list them. If not, state that the TUI is stable under monkey testing.

- [ ] **Step 3: Final Commit**

```bash
git commit -m "docs: finalize TUI monkey test results"
```
