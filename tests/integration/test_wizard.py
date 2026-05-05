import pytest
from unittest.mock import patch, MagicMock
from src.cli.wizard import MigrationWizard

@pytest.fixture
def mock_clients():
    with patch("src.cli.wizard.build_clients") as mock:
        sc = MagicMock()
        dc = MagicMock()
        mock.return_value = (sc, dc)
        yield (sc, dc)

@pytest.fixture
def mock_prompts():
    with patch("src.cli.wizard.Prompt.ask") as mock_ask, \
         patch("src.cli.wizard.Confirm.ask") as mock_confirm:
        yield mock_ask, mock_confirm

def test_wizard_init(mock_clients):
    wizard = MigrationWizard("tests/test_config.ini")
    assert wizard.config_path == "tests/test_config.ini"

@patch("src.cli.wizard.console.clear")
@patch("src.cli.wizard.console.print")
def test_wizard_run_flow(mock_print, mock_clear, mock_clients, mock_prompts):
    mock_ask, mock_confirm = mock_prompts
    sc, dc = mock_clients
    
    mock_confirm.return_value = True # Proceed with Step 1
    
    # Mock database queries for _detect_state
    sc.execute_query.return_value = [] # No publication
    dc.execute_query.return_value = [] # No subscription, no tables
    
    wizard = MigrationWizard("tests/test_config.ini")
    
    # Step 1 logic calls check_connectivity
    with patch("src.cli.wizard.DBChecker.check_connectivity") as mock_conn, \
         patch("builtins.input", side_effect=["next", "exit"]):
        mock_conn.return_value = {"source": True, "dest": True}
        wizard.run()
        mock_conn.assert_called()

    assert mock_confirm.call_count >= 1
