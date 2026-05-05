import pytest
from unittest.mock import MagicMock, patch
from src.cli.commands import (
    cmd_check, cmd_diagnose, cmd_params, cmd_migrate_schema_pre_data,
    cmd_migrate_schema_post_data, cmd_setup_pub, cmd_setup_sub,
    cmd_repl_progress, cmd_sync_sequences,
    cmd_enable_triggers, cmd_disable_triggers, cmd_refresh_matviews,
    cmd_reassign_owner, cmd_audit_objects, cmd_validate_rows,
    cmd_cleanup, cmd_generate_config, cmd_setup_reverse,
    cmd_cleanup_reverse, cmd_sync_lobs
)


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.config = "dummy.ini"
    args.dry_run = False
    args.drop_dest = False
    args.use_stats = False
    args.output = "dummy_out.ini"
    return args


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.DBChecker")
def test_cmd_check(mock_dbchecker, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_dbchecker_instance = mock_dbchecker.return_value
    mock_dbchecker_instance.check_connectivity.return_value = {
        "source": True, "dest": True}

    assert cmd_check(mock_args) == 0

    mock_dbchecker_instance.check_connectivity.return_value = {
        "source": False, "dest": True}
    assert cmd_check(mock_args) == 1


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.DBChecker")
def test_cmd_diagnose(mock_dbchecker, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_dbchecker_instance = mock_dbchecker.return_value
    mock_dbchecker_instance.check_problematic_objects.return_value = {
        "no_pk": [{"schema_name": "s", "table_name": "t"}],
        "large_objects": 0,
        "identities": [{"table_schema": "s", "table_name": "t", "column_name": "c"}],
        "unowned_seqs": [{"schema_name": "s", "seq_name": "seq"}],
        "matviews": [{"schema_name": "s", "matview_name": "mv"}],
    }
    mock_dbchecker_instance.get_database_size_analysis.return_value = {
        "database": {"total_pretty": "10MB"},
        "tables": [{"schema_name": "s", "table_name": "t", "data_pretty": "1MB", "index_pretty": "1MB", "total_pretty": "2MB", "percent": 20}]
    }

    assert cmd_diagnose(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.DBChecker")
def test_cmd_params(mock_dbchecker, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_dbchecker_instance = mock_dbchecker.return_value

    mock_dbchecker_instance.check_replication_params.return_value = {
        "source": [{"parameter": "wal_level", "actual": "logical", "expected": "logical", "status": "OK"}],
        "dest": [{"parameter": "max_replication_slots", "actual": "10", "expected": "10", "status": "OK"}]
    }
    assert cmd_params(mock_args) == 0

    mock_dbchecker_instance.check_replication_params.return_value = {
        "source": [{"parameter": "wal_level", "actual": "replica", "expected": "logical", "status": "FAIL"}],
    }
    assert cmd_params(mock_args) == 1


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_migrate_schema_pre_data(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step4a_migrate_schema_pre_data.return_value = (
        True, "msg", [], [])

    assert cmd_migrate_schema_pre_data(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_migrate_schema_pre_data(mock_args) == 0

    mock_args.drop_dest = True
    assert cmd_migrate_schema_pre_data(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_migrate_schema_post_data(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step10_terminate_replication.return_value = (
        True, "msg", [], [])
    mock_mig_instance.step4b_migrate_schema_post_data.return_value = (
        True, "msg", [], [])

    assert cmd_migrate_schema_post_data(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_migrate_schema_post_data(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_setup_pub(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step5_setup_source.return_value = (True, "msg", [], [])

    assert cmd_setup_pub(mock_args) == 0

    mock_args.dry_run = True
    mock_cfg_instance = mock_cfg.return_value
    mock_cfg_instance.get_replication.return_value = {
        "publication_name": "pub"}
    assert cmd_setup_pub(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_setup_sub(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step6_setup_destination.return_value = (
        True, "msg", [], [])

    assert cmd_setup_sub(mock_args) == 0

    mock_args.dry_run = True
    mock_cfg_instance = mock_cfg.return_value
    mock_cfg_instance.get_replication.return_value = {
        "subscription_name": "sub"}
    assert cmd_setup_sub(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_repl_progress(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value

    mock_mig_instance.get_initial_copy_progress.return_value = {
        "summary": {
            "total_tables": 1, "completed_tables": 1,
            "percent_bytes": 100, "percent_tables": 100,
            "bytes_copied_pretty": "10MB", "total_source_pretty": "10MB"
        },
        "tables": [{"table_name": "t1", "state": "r", "bytes_copied": 100, "size_source": 100, "percent": 100}]
    }
    assert cmd_repl_progress(mock_args) == 0

    mock_mig_instance.get_initial_copy_progress.return_value = {
        "summary": {"total_tables": 0},
        "tables": []
    }
    assert cmd_repl_progress(mock_args) == 0

    mock_mig_instance.get_initial_copy_progress.return_value = None
    assert cmd_repl_progress(mock_args) == 1


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.PostSync")
def test_cmd_sync_sequences(mock_ps, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.sync_sequences.return_value = (True, "msg", [], [])

    assert cmd_sync_sequences(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_sync_sequences(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.PostSync")
def test_cmd_enable_triggers(mock_ps, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.enable_triggers.return_value = (True, "msg", [], [])

    assert cmd_enable_triggers(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_enable_triggers(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.PostSync")
def test_cmd_disable_triggers(mock_ps, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.disable_triggers.return_value = (True, "msg", [], [])

    assert cmd_disable_triggers(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_disable_triggers(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.PostSync")
def test_cmd_refresh_matviews(mock_ps, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.refresh_materialized_views.return_value = (
        True, "msg", [], [])

    assert cmd_refresh_matviews(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_refresh_matviews(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.PostSync")
def test_cmd_reassign_owner(mock_ps, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_cfg_instance = mock_cfg.return_value
    mock_cfg_instance.get_dest_dict.return_value = {"user": "test_user"}

    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.reassign_ownership.return_value = (True, "msg", [], [])

    assert cmd_reassign_owner(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_reassign_owner(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.Validator")
def test_cmd_audit_objects(mock_val, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_val_instance = mock_val.return_value
    mock_val_instance.audit_objects.return_value = (
        True, "msg", [], [], [{"type": "TABLE", "source": 1, "dest": 1, "status": "OK"}])

    assert cmd_audit_objects(mock_args) == 0

    mock_val_instance.audit_objects.return_value = (
        True, "msg", [], [], [{"type": "TABLE", "source": 1, "dest": 2, "status": "FAIL"}])
    assert cmd_audit_objects(mock_args) == 1


@patch("src.cli.commands.Config")
@patch("src.cli.commands.build_clients")
@patch("src.cli.commands.Validator")
def test_cmd_validate_rows(mock_val, mock_bc, mock_cfg, mock_args):
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_val_instance = mock_val.return_value
    mock_val_instance.compare_row_counts.return_value = (True, "msg", [], [], [
                                                         {"table": "t1", "source": 100, "dest": 100, "diff": 0, "status": "OK"}])

    assert cmd_validate_rows(mock_args) == 0

    mock_val_instance.compare_row_counts.return_value = (True, "msg", [], [], [
                                                         {"table": "t1", "source": 100, "dest": 90, "diff": 10, "status": "FAIL"}])
    assert cmd_validate_rows(mock_args) == 1


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_cleanup(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.step10_terminate_replication.return_value = (
        True, "msg", [], [])

    assert cmd_cleanup(mock_args) == 0

    mock_args.dry_run = True
    mock_cfg_instance = mock_cfg.return_value
    mock_cfg_instance.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    assert cmd_cleanup(mock_args) == 0



@patch("src.cli.commands.generate_sample_config")
def test_cmd_generate_config(mock_gen, mock_args):
    assert cmd_generate_config(mock_args) == 0
    mock_gen.assert_called_once_with("dummy_out.ini")

    mock_args.output = None
    assert cmd_generate_config(mock_args) == 0
    mock_gen.assert_called_with("config_migrator.sample.ini")


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_setup_reverse(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.setup_reverse_replication.return_value = (
        True, "msg", [], [])

    assert cmd_setup_reverse(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_cleanup_reverse(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.cleanup_reverse_replication.return_value = (
        True, "msg", [], [])

    assert cmd_cleanup_reverse(mock_args) == 0


@patch("src.cli.commands.Config")
@patch("src.cli.commands.Migrator")
def test_cmd_sync_lobs(mock_migrator, mock_cfg, mock_args):
    mock_mig_instance = mock_migrator.return_value
    mock_mig_instance.sync_large_objects.return_value = (True, "msg", [], [])

    assert cmd_sync_lobs(mock_args) == 0

    mock_args.dry_run = True
    assert cmd_sync_lobs(mock_args) == 0
