# E2E TUI Monkey Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a robust E2E test that drives a real migration through the TUI while injecting random interactions to verify stability.

**Architecture:** The test uses Textual's `run_test` and `pilot` to interact with `MigratorApp`. It uses a background "monkey" function to stress the UI during asynchronous migration steps managed by the app's internal workers.

**Tech Stack:** `pytest`, `pytest-asyncio`, `textual`, `psycopg2`.

---

### Task 1: Test Skeleton and Setup

**Files:**
- Create: `tests/e2e/test_tui_monkey_migration.py`

- [ ] **Step 1: Write the failing test skeleton**

```python
import pytest
import random
import string
import asyncio
import time
from textual.widgets import Button, TabPane, Select, Input, Static, ListView, TabbedContent
from src.tui import MigratorApp

@pytest.mark.asyncio
async def test_tui_monkey_migration_full():
    app = MigratorApp("tests/test_config.ini")
    async with app.run_test() as pilot:
        # Just check if it boots
        assert app.is_running
        await pilot.pause(0.1)
```

- [ ] **Step 2: Run test to verify it passes (as a skeleton)**

Run: `pytest tests/e2e/test_tui_monkey_migration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tui_monkey_migration.py
git commit -m "test: add E2E TUI monkey migration test skeleton"
```

---

### Task 4: Implement Monkey Stressor

**Files:**
- Modify: `tests/e2e/test_tui_monkey_migration.py`

- [ ] **Step 1: Add the `monkey_stress` helper function**

```python
async def monkey_stress(pilot, iterations=5):
    app = pilot.app
    actions = ["press_tab", "press_key", "switch_tab", "type_random"]
    keys = ["down", "up", "left", "right", "space"]
    
    for _ in range(iterations):
        action = random.choice(actions)
        if action == "press_tab":
            await pilot.press("tab" if random.random() > 0.3 else "shift+tab")
        elif action == "press_key":
            await pilot.press(random.choice(keys))
        elif action == "switch_tab":
            from textual.widgets import TabbedContent
            tc = app.query_one(TabbedContent)
            tabs = list(tc.query(TabPane))
            if tabs:
                target = random.choice(tabs)
                tc.active = target.id
        elif action == "type_random":
            focused = app.focused
            if isinstance(focused, Input):
                await pilot.type(''.join(random.choices(string.ascii_letters, k=3)))
        await pilot.pause(0.01)
```

- [ ] **Step 2: Update test to use the stressor**

```python
@pytest.mark.asyncio
async def test_tui_monkey_migration_full():
    app = MigratorApp("tests/test_config.ini")
    async with app.run_test() as pilot:
        await monkey_stress(pilot, iterations=10)
        assert app.is_running
```

- [ ] **Step 3: Run test and commit**

Run: `pytest tests/e2e/test_tui_monkey_migration.py -v`

---

### Task 3: Implement Phase 1 (Init Pipeline)

**Files:**
- Modify: `tests/e2e/test_tui_monkey_migration.py`

- [ ] **Step 1: Add logic to switch to Automation tab and click INIT**

```python
async def wait_for_message(pilot, target_text, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        # Check main display
        display = pilot.app.query_one("#main_display", Static)
        if target_text in str(display.renderable):
            return True
        # Also check history
        history = pilot.app.query_one("#history_list", ListView)
        for item in history.query("HistoryItem"):
             if target_text in str(item.action_label):
                 return True
        await pilot.pause(0.5)
        await monkey_stress(pilot, 2)
    return False

# In test:
# 1. Drop dest first for clean slate
await pilot.click("#step_drop_dest")
await pilot.pause(2)

# 2. Automation -> INIT
tc = app.query_one(TabbedContent)
for pane in tc.query(TabPane):
    if "AUTOMATION" in str(pane.label):
        tc.active = pane.id
        break

await pilot.click("#cmd_init")
assert await wait_for_message(pilot, "Pipeline Completed Successfully", timeout=120)
```

- [ ] **Step 2: Run test and commit**

---

### Task 4: Implement Phase 2 (Post Pipeline) and Validation

**Files:**
- Modify: `tests/e2e/test_tui_monkey_migration.py`

- [ ] **Step 1: Click POST PIPELINE and Verify Data**

```python
# 3. Automation -> POST
await pilot.click("#cmd_post")
assert await wait_for_message(pilot, "Pipeline Completed Successfully", timeout=180)

# 4. Final Validation
from src.db import PostgresClient
dest_client = PostgresClient(app.config.get_dest_conn("test_migration"))
res = dest_client.execute_query("SELECT count(*) FROM actor;")
assert res[0]['count'] > 0
dest_client.close()
```

- [ ] **Step 2: Run full test and commit**

Run: `pytest tests/e2e/test_tui_monkey_migration.py -v`
Expected: Final report generated, data present, no crashes.
