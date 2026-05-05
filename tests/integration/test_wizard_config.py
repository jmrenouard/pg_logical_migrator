import pytest
from unittest.mock import patch, MagicMock
from src.cli.wizard import MigrationWizard

@patch("builtins.input")
@patch("src.cli.wizard.Config")
@patch("src.cli.wizard.build_clients")
@patch("src.cli.wizard.Prompt.ask")
@patch("src.cli.wizard.Confirm.ask")
@patch("src.cli.wizard.os.makedirs")
def test_wizard_config_flow(mock_makedirs, mock_confirm, mock_ask, mock_clients, mock_config, mock_input):
    mock_config.return_value.get_databases.return_value = ["postgres"]
    mock_clients.return_value = (MagicMock(), MagicMock())
    # Side effects for input()
    mock_input.side_effect = [
        "config",                        # Choice 1: main menu
        "exit"                           # Choice 2: main menu
    ]
    
    # Side effects for Prompt.ask
    mock_ask.side_effect = [
        "src-host", "5432", "src-user", "src-pass", "src-db", # Source details
        "dst-host", "5433", "dst-user", "dst-pass", "dst-db", # Dest details
        "public", "pub", "sub",          # Replication details
    ]
    
    # Side effects for Confirm.ask
    # 1. Generate default config? -> No (during init)
    # 2. Generate default config? -> No (during _menu_configure)
    # 3. Configure Source? -> Yes
    # 4. Configure Destination? -> Yes
    # 5. Configure Replication? -> Yes
    # 6. Save configuration? -> Yes
    mock_confirm.side_effect = [False, False, True, True, True, True]

    wizard = MigrationWizard("dummy.ini")

    
    # Mock _detect_state to avoid real DB calls during the loop
    with patch.object(wizard, "_detect_state") as mock_detect:
        mock_detect.return_value = {
            "connectivity": {"source": True, "dest": True},
            "schema_pre": False,
            "publication": None,
            "subscription": None,
            "sync_done": False,
            "schema_post": False,
            "replication_active": False
        }
        wizard.run()
    
    # Verifications
    mock_cfg = mock_config.return_value
    calls = mock_cfg.update_section.call_args_list
    assert len(calls) == 3
    assert calls[0][0][0] == "source"
    assert calls[0][0][1]["host"] == "src-host"
    assert calls[0][0][1]["database"] == "src-db"
    
    assert calls[1][0][0] == "destination"
    assert calls[1][0][1]["host"] == "dst-host"
    
    assert calls[2][0][0] == "replication"
    assert calls[2][0][1]["target_schema"] == "public"
    
    assert mock_ask.call_count == 13
