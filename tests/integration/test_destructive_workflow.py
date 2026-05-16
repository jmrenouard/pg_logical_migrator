import pytest
from unittest.mock import patch
import argparse
from src.cli.wizard import MigrationWizard

@pytest.fixture
def mock_wizard_args():
    return argparse.Namespace(
        config="config_migrator.ini",
        database="test_migration",
        results_dir="RESULTS",
        loglevel="INFO",
        dry_run=False,
        verbose=False,
        use_stats=False,
        sync_delay=3600,
        drop_dest=False,
        wait=True,
        owner=None,
        output="config_migrator.sample.ini",
        log_file=None,
        command="wizard"
    )

def test_wizard_destructive_schema_pre_data(mock_wizard_args):
    """
    Simulate interactive wizard execution for step 4 (Schema pre-data) with drop-dest.
    """
    # Mock inputs:
    # 1. Action: "4" (Schema Pre-data)
    # 2. Confirm: "Execute migrate-schema-pre-data?": True
    # 3. Confirm: "Drop destination DB first?": True
    # 4. Action: "x" (Exit)

    input_actions = ["4", "q"]
    input_confirms = {
        "Execute [cyan]migrate-schema-pre-data[/cyan]?": True,
        "Drop destination DB first? (--drop-dest)": True,
        "Generate HTML report before leaving?": False
    }

    def mock_ask_action(*args, **kwargs):
        if input_actions:
            return input_actions.pop(0)
        return "q"

    def mock_confirm_ask(prompt, **kwargs):
        for k, v in input_confirms.items():
            if k in prompt:
                return v
        return kwargs.get("default", True)

    def mock_input(*args, **kwargs):
        if input_actions:
            return input_actions.pop(0)
        return "q"

    wizard = MigrationWizard(mock_wizard_args.config, mock_wizard_args.database)
    
    with patch("src.cli.wizard.Prompt.ask", side_effect=mock_ask_action), \
         patch("src.cli.wizard.Confirm.ask", side_effect=mock_confirm_ask), \
         patch("builtins.input", side_effect=mock_input):
        
        wizard.run()

    # Verify history
    assert wizard.model.history.get("4") == "OK", "Step 4 should complete successfully"
