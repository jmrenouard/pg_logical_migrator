import pytest
from unittest.mock import patch, MagicMock
from src.cli.wizard import MigrationWizard

@patch("src.cli.wizard.build_clients")
@patch("src.cli.wizard.Prompt.ask")
@patch("src.cli.wizard.Confirm.ask")
@patch("src.cli.wizard.Config.save")
@patch("src.cli.wizard.os.makedirs")
def test_wizard_config_flow(mock_makedirs, mock_save, mock_confirm, mock_ask, mock_clients):
    mock_clients.return_value = (MagicMock(), MagicMock())
    wizard = MigrationWizard("dummy.ini")
    
    # 1. Main menu: select 'config'
    # 2. Confirm "Configure Source Database?" -> Yes
    # 3. _prompt_db_details for Source
    # 4. Confirm "Configure Destination Database?" -> Yes
    # 5. _prompt_db_details for Destination
    # 6. Confirm "Configure Replication Settings?" -> Yes
    # 7. _prompt_replication_details
    # 8. Confirm "Save configuration to dummy.ini?" -> Yes
    # 9. Main menu: select 'exit'
    
    # Side effects for Prompt.ask
    mock_ask.side_effect = [
        "config",                        # Choice 1: main menu
        "src-host", "5432", "src-user", "src-pass", "src-db", # Source details
        "dst-host", "5433", "dst-user", "dst-pass", "dst-db", # Dest details
        "public", "pub", "sub",          # Replication details
        "exit"                           # Choice 2: main menu
    ]
    
    # Side effects for Confirm.ask (always True)
    mock_confirm.return_value = True
    
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
    assert mock_save.called
    assert wizard.cfg.config["source"]["host"] == "src-host"
    assert wizard.cfg.config["source"]["database"] == "src-db"
    assert wizard.cfg.config["destination"]["host"] == "dst-host"
    assert wizard.cfg.config["replication"]["target_schema"] == "public"
    assert mock_ask.call_count == 15
