import os
import random
import string
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
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        
        iterations = 200
        actions = ["press_tab", "press_enter", "press_key", "click_button", "switch_tab", "type_random"]
        
        keys = ["down", "up", "left", "right", "pageup", "pagedown", "home", "end", "space", "escape"]
        
        for i in range(iterations):
            action = random.choice(actions)
            
            try:
                if action == "press_tab":
                    # 70% chance for tab, 30% for shift+tab
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
                            # Try to click the button
                            try:
                                await pilot.click(btn)
                            except Exception:
                                # Sometimes clicking fails if widget is moving or obscured
                                pass
                elif action == "switch_tab":
                    from textual.widgets import TabbedContent
                    tabbed_contents = list(app.query(TabbedContent))
                    if tabbed_contents:
                        tabbed_content = tabbed_contents[0]
                        tabs = list(tabbed_content.query(TabPane))
                        if tabs:
                            target_tab = random.choice(tabs)
                            # Directly set active to simulate switching
                            tabbed_content.active = target_tab.id
                elif action == "type_random":
                    focused = app.focused
                    if isinstance(focused, Input):
                        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
                        await pilot.type(random_str)
                    else:
                        # Find an Input to type into even if not focused
                        inputs = list(app.query(Input))
                        if inputs and random.random() > 0.5:
                            inp = random.choice(inputs)
                            if inp.visible and inp.enabled:
                                inp.focus()
                                random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
                                await pilot.type(random_str)
                
                # Small random pause
                await pilot.pause(random.uniform(0.01, 0.03))
            except Exception:
                # App internal errors should be caught by Textual's run_test
                pass
            
            if i % 50 == 0:
                 await pilot.pause(0.1)

        assert app.is_running
        # Final check - make sure we can still interact
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.is_running
