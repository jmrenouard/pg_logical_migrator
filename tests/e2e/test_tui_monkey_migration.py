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
    """
    E2E Test: Run a full migration via TUI with monkey stress.
    """
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
                        btn = random.choice(buttons)
                        # Avoid clicking 'Drop Dest' as it might interfere too much if hit at wrong time
                        if btn.id != "step_drop_dest":
                            await pilot.click(btn)
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
            await asyncio.sleep(0.05) # Faster monkey

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        
        # 1. Switch to Automation tab
        tabbed_content = app.query_one(TabbedContent)
        # Find the pane with INIT PIPELINE
        target_tab_id = None
        for pane in tabbed_content.query(TabPane):
             if pane.query("#cmd_init"):
                 target_tab_id = pane.id
                 break
        
        if target_tab_id:
            tabbed_content.active = target_tab_id
        else:
            pytest.fail("Could not find AUTOMATION tab")
            
        await pilot.pause(0.2)

        # 2. Start Monkey in background
        monkey_task = asyncio.create_task(monkey_stress(pilot))

        # 3. Start INIT PIPELINE
        await pilot.click("#cmd_init")
        
        # 4. Wait for INIT PIPELINE to complete
        # Timeout 180s (increased for safety)
        success_init = False
        for _ in range(180):
            display = app.query_one("#main_display", Static)
            # Textual's Static widget stores its Rich renderable in _renderable
            content = str(getattr(display, "_renderable", ""))
            if "COMPLETED" in content or "Successfully" in content:
                success_init = True
                break
            if "Pipeline Failed" in content:
                monkey_active = False
                await monkey_task
                pytest.fail(f"INIT PIPELINE failed: {content}")
            await pilot.pause(1.0)
        
        if not success_init:
             monkey_active = False
             await monkey_task
             pytest.fail("INIT PIPELINE timed out")

        await pilot.pause(1.0)

        # 5. Start POST PIPELINE
        # Ensure we are on the right tab if monkey switched it
        tabbed_content.active = target_tab_id
        await pilot.pause(0.2)
        await pilot.click("#cmd_post")

        # 6. Wait for POST PIPELINE to complete
        success_post = False
        for _ in range(180):
            display = app.query_one("#main_display", Static)
            content = str(getattr(display, "_renderable", ""))
            if "COMPLETED" in content or "Successfully" in content:
                success_post = True
                break
            if "Pipeline Failed" in content:
                monkey_active = False
                await monkey_task
                pytest.fail(f"POST PIPELINE failed: {content}")
            await pilot.pause(1.0)
            
        if not success_post:
             monkey_active = False
             await monkey_task
             pytest.fail("POST PIPELINE timed out")

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
