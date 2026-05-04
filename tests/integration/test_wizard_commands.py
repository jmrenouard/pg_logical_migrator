from unittest.mock import patch, MagicMock
from src.cli.wizard import MigrationWizard

@patch("src.cli.wizard.Prompt.ask")
@patch.object(MigrationWizard, "_run_step")
@patch.object(MigrationWizard, "_detect_state")
@patch("src.cli.wizard.build_clients")
def test_wizard_run_by_command_name(mock_clients, mock_detect, mock_run_step, mock_ask):
    mock_clients.return_value = (MagicMock(), MagicMock())
    wizard = MigrationWizard("test.ini")
    mock_detect.return_value = {
        "connectivity": {"source": True, "dest": True},
        "schema_pre": False,
        "publication": None,
        "subscription": None,
        "sync_done": False,
        "schema_post": False,
        "replication_active": False
    }
    # User selects 'run', then 'setup-pub', then 'exit'
    mock_ask.side_effect = ["run", "setup-pub", "exit"]
    
    wizard.run()
    
    # Check if _run_step was called with the step corresponding to '5' (setup-pub)
    assert mock_run_step.called
    args, _ = mock_run_step.call_args
    assert args[0]['id'] == '5'
    assert args[0]['name'] == 'Setup Publication'
