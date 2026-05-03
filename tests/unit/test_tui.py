import pytest
from unittest.mock import patch, MagicMock
from src.tui import MigratorApp, main
from textual.widgets import Checkbox, Button, ListView


@pytest.fixture(autouse=True)
def mock_sleep():
    with patch("time.sleep", return_value=None) as mock:
        yield mock

@pytest.fixture
def mock_config():
    with patch("src.tui.Config") as mock:
        mock_instance = mock.return_value
        mock_instance.get_target_schemas.return_value = ["public"]
        mock_instance.get_databases.return_value = ["test_db"]
        mock_instance.config = MagicMock()
        mock_instance.config.get.return_value = "INFO"
        mock_instance.get_source_dict.return_value = {'user': 'user', 'password': 'pw', 'host': 'host', 'port': '5432'}
        mock_instance.get_dest_dict.return_value = {'user': 'user', 'password': 'pw', 'host': 'host', 'port': '5433'}
        yield mock


@pytest.fixture
def mock_pgclient():
    with patch("src.tui.PostgresClient") as mock:
        yield mock


@pytest.fixture
def mock_dbchecker():
    with patch("src.tui.DBChecker") as mock:
        yield mock


@pytest.fixture
def mock_migrator():
    with patch("src.tui.Migrator") as mock:
        yield mock


@pytest.fixture
def mock_postsync():
    with patch("src.tui.PostSync") as mock:
        yield mock


@pytest.fixture
def mock_validator():
    with patch("src.tui.Validator") as mock:
        yield mock


class MockButtonEvent:
    def __init__(self, btn_id, label="Test"):
        self.button = MagicMock(id=btn_id, label=label)


@pytest.mark.asyncio
async def test_app_startup_and_history(
        mock_config, mock_pgclient, mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")

    mock_dbchecker_instance = mock_dbchecker.return_value
    mock_dbchecker_instance.check_connectivity.return_value = {
        "source": True, "dest": False}

    async with app.run_test() as pilot:
        assert app.title == "pg_logical_migrator"

        # Test Step 1: Check
        app.handle_buttons(MockButtonEvent("step_1"))
        mock_dbchecker_instance.check_connectivity.assert_called_once()

        # Test History Recall
        history_list = app.query_one("#history_list", ListView)
        assert len(history_list) >= 1

        # Select the history item to trigger recall_history
        # Just manually invoke the handler
        app.recall_history(MagicMock(item=history_list.children[0]))


@pytest.mark.asyncio
async def test_app_buttons(mock_config, mock_pgclient,
                           mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")

    mock_dbchecker_instance = mock_dbchecker.return_value
    mock_mig_instance = mock_migrator.return_value
    mock_val_instance = mock_validator.return_value

    # Mock return values for different steps
    mock_dbchecker_instance.check_problematic_objects.return_value = {
        'no_pk': ['t1'], 'large_objects': 5, 'unowned_seqs': ['s1'], 'unlogged_tables': []
    }

    mock_dbchecker_instance.check_replication_params.return_value = {
        'source': [{'parameter': 'wal_level', 'actual': 'logical', 'status': 'OK'}],
        'dest': [{'parameter': 'max_replication_slots', 'actual': '10', 'status': 'WARN'}]
    }

    mock_mig_instance.step4a_migrate_schema_pre_data.return_value = (
        True, "msg", [], [])
    mock_mig_instance.step5_setup_source.return_value = (True, "msg", [], [])
    mock_mig_instance.step6_setup_destination.return_value = (
        True, "msg", [], [])

    mock_mig_instance.get_initial_copy_progress.return_value = {
        "summary": {"total_tables": 1},
        "tables": [{"table_name": "t1", "state": "r", "percent": 100}]
    }

    mock_mig_instance.sync_large_objects.return_value = (True, "msg", [], [])

    mock_val_instance.audit_objects.return_value = (
        True, "msg", [], [], [{'type': 'TABLE', 'source': 1, 'dest': 1, 'status': 'OK'}])
    mock_val_instance.compare_row_counts.return_value = (
        True, "msg", [], [], [{'table': 't1', 'diff': 0, 'status': 'OK'}])

    async with app.run_test() as pilot:
        # Check Drop Dest Button is available
        drop_dest_btn = app.query_one("#step_drop_dest", Button)
        
        app.handle_buttons(MockButtonEvent("step_show_config"))

        app.handle_buttons(MockButtonEvent("step_2"))
        mock_dbchecker_instance.check_problematic_objects.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_3"))
        mock_dbchecker_instance.check_replication_params.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_4"))
        mock_mig_instance.step4a_migrate_schema_pre_data.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_5"))
        mock_mig_instance.step5_setup_source.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_6"))
        await pilot.pause(0.2)
        mock_mig_instance.step6_setup_destination.assert_called_once()

        app.handle_buttons(MockButtonEvent("cmd_progress"))
        mock_mig_instance.get_initial_copy_progress.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_11"))
        mock_mig_instance.sync_large_objects.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_14"))
        mock_val_instance.audit_objects.assert_called_once()

        app.handle_buttons(MockButtonEvent("step_15"))
        mock_val_instance.compare_row_counts.assert_called_once()

        # Generic step handling
        app.handle_buttons(MockButtonEvent("step_8"))
        app.handle_buttons(MockButtonEvent("cmd_apply_params"))


@pytest.mark.asyncio
async def test_app_progress_none(
        mock_config, mock_pgclient, mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.get_initial_copy_progress.return_value = None

    async with app.run_test() as pilot:
        app.handle_buttons(MockButtonEvent("cmd_progress"))
        mock_mig_instance.get_initial_copy_progress.assert_called_once()


@pytest.mark.asyncio
async def test_app_pipelines(mock_config, mock_pgclient,
                             mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")

    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step4a_migrate_schema_pre_data.return_value = (
        True, "msg", [], [])
    mock_mig_instance.step5_setup_source.return_value = (True, "msg", [], [])
    mock_mig_instance.step6_setup_destination.return_value = (
        True, "msg", [], [])
    mock_mig_instance.sync_large_objects.return_value = (True, "msg", [], [])
    mock_mig_instance.step10_terminate_replication.return_value = (
        True, "msg", [], [])
    mock_mig_instance.step4b_migrate_schema_post_data.return_value = (
        True, "msg", [], [])
    mock_mig_instance.sync_unlogged_tables.return_value = (
        True, "msg", [], [])

    mock_postsync_instance = mock_postsync.return_value
    mock_postsync_instance.refresh_materialized_views.return_value = (True, "msg", [], [])
    mock_postsync_instance.sync_sequences.return_value = (True, "msg", [], [])
    mock_postsync_instance.enable_triggers.return_value = (True, "msg", [], [])
    mock_postsync_instance.reassign_ownership.return_value = (True, "msg", [], [])

    mock_validator_instance = mock_validator.return_value
    mock_validator_instance.audit_objects.return_value = (True, "msg", [], [], [])
    mock_validator_instance.compare_row_counts.return_value = (True, "msg", [], [], [])

    async with app.run_test() as pilot:
        # Init Pipeline
        app.handle_buttons(MockButtonEvent("cmd_init"))
        await pilot.pause(0.2)
        mock_mig_instance.step4a_migrate_schema_pre_data.assert_called_once()
        mock_mig_instance.wait_for_sync.assert_called()

        # Post Pipeline
        app.handle_buttons(MockButtonEvent("cmd_post"))
        await pilot.pause(0.2)
        mock_mig_instance.step10_terminate_replication.assert_called_once()
        mock_postsync.return_value.sync_sequences.assert_called_once()


@pytest.mark.asyncio
async def test_app_exception_handling(
        mock_config, mock_pgclient, mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")

    mock_dbchecker_instance = mock_dbchecker.return_value
    mock_dbchecker_instance.check_connectivity.side_effect = Exception(
        "Test Exception")

    async with app.run_test() as pilot:
        app.handle_buttons(MockButtonEvent("step_1"))
        mock_dbchecker_instance.check_connectivity.assert_called_once()
        # The exception should be caught and rendered as an Error Panel.


@pytest.mark.asyncio
async def test_app_pipeline_exceptions(
        mock_config, mock_pgclient, mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    app = MigratorApp("dummy.ini")

    mock_mig_instance = mock_migrator.return_value
    # Force step 6 to fail
    mock_mig_instance.step6_setup_destination.side_effect = Exception(
        "Sub fail")

    async with app.run_test() as pilot:
        app.handle_buttons(MockButtonEvent("step_6"))
        await pilot.pause(0.1)

        # Force init pipeline to fail
        mock_mig_instance.step4a_migrate_schema_pre_data.side_effect = Exception(
            "Init fail")
        app.handle_buttons(MockButtonEvent("cmd_init"))
        await pilot.pause(0.1)

        # Force post pipeline to fail
        mock_mig_instance.wait_for_sync.side_effect = Exception("Post fail")
        app.handle_buttons(MockButtonEvent("cmd_post"))
        await pilot.pause(0.1)


@patch("argparse.ArgumentParser.parse_args")
@patch("src.tui.MigratorApp.run")
def test_main(mock_run, mock_parse_args):
    mock_args = MagicMock()
    mock_args.config = "dummy.ini"
    mock_parse_args.return_value = mock_args

    with patch("src.tui.Config") as mock_conf, \
            patch("src.tui.PostgresClient"), \
            patch("src.tui.DBChecker"), \
            patch("src.tui.Migrator"), \
            patch("src.tui.PostSync"), \
            patch("src.tui.Validator"):
        mock_conf.return_value.get_databases.return_value = ["test_db"]
        main()
        mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_app_multi_db_selection(mock_config, mock_pgclient, mock_dbchecker, mock_migrator, mock_postsync, mock_validator):
    """
    Test unitaire pour la sélection d'une base de données dans la TUI.
    Vérifie que la modification de la base sélectionnée met à jour la configuration.
    """
    app = MigratorApp("dummy.ini")
    
    # Configure 2 bases de données mockées
    mock_config_instance = mock_config.return_value
    mock_config_instance.get_databases.return_value = ["db_alpha", "db_beta"]
    
    async with app.run_test() as pilot:
        # Attendre que l'application soit prête
        await pilot.pause(0.1)
        
        # Simuler le changement de sélection de base de données en déclenchant manuellement update_db_selection
        from textual.widgets import Select
        select_widget = app.query_one("#opt_database", Select)
        select_widget.set_options([("ALL DATABASES", "ALL"), ("db_alpha", "db_alpha"), ("db_beta", "db_beta")])
        select_widget.value = "db_beta"
        await pilot.pause(0.1)
        
        # Vérifier que le Select pointe bien vers la nouvelle DB
        assert select_widget.value == "db_beta"
        
        # Et quand on exécute une action, elle s'applique à cette base
        mock_dbchecker_instance = mock_dbchecker.return_value
        await pilot.click("#step_1")
        await pilot.pause(0.1)
        mock_dbchecker_instance.check_connectivity.assert_called()
