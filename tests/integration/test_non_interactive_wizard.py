from unittest.mock import patch
from src.cli.wizard import MigrationWizard

@patch("src.cli.wizard.WizardModel.init_config")
@patch("src.cli.wizard.WizardModel.init_clients")
@patch("src.cli.wizard.WizardModel.detect_state")
@patch("src.cli.wizard.WizardModel.get_next_step")
@patch("src.cli.wizard.MigrationWizard._execute_step")
@patch("src.cli.wizard.MigrationWizard._generate_report")
def test_non_interactive_wizard_flow(mock_generate_report, mock_execute_step, mock_get_next_step, mock_detect_state, mock_init_clients, mock_init_config):
    mock_init_config.return_value = True
    mock_init_clients.return_value = True
    mock_detect_state.return_value = {"source": True, "dest": True}
    
    # Simulate first step available, then finished
    mock_get_next_step.side_effect = [
        {"id": 1, "name": "Connectivity Check", "desc": "Check connectivity", "cmd": "check"},
        None
    ]
    
    wizard = MigrationWizard(config_path="dummy.ini", database="test_migration", non_interactive=True)
    
    # Run the wizard
    wizard.run()
    
    # Verify the step was executed
    mock_execute_step.assert_called_once()
    assert mock_execute_step.call_args[0][0]["id"] == 1
    
    # Verify report was generated
    mock_generate_report.assert_called_once()
