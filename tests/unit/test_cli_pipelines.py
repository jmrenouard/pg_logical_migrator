import pytest
from unittest.mock import MagicMock, patch
from src.cli.pipelines import cmd_init_replication, cmd_post_migration

@pytest.fixture
def mock_args():
    args = MagicMock()
    args.config = "dummy.ini"
    args.results_dir = "dummy_dir"
    args.loglevel = "DEBUG"
    args.sync_delay = 0
    args.dry_run = False
    args.drop_dest = False
    return args

@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
@patch("src.cli.pipelines.DBChecker")
@patch("src.cli.pipelines.Migrator")
@patch("src.cli.pipelines.PostSync")
@patch("src.cli.pipelines.Validator")
@patch("src.cli.pipelines.ReportGenerator")
def test_cmd_init_replication_success(mock_rg, mock_val, mock_ps, mock_mig, mock_dbck, mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    
    # Mock clients
    mock_sc = MagicMock()
    mock_dc = MagicMock()
    mock_bc.return_value = (mock_sc, mock_dc)
    
    # Mock DBChecker
    mock_dbck_instance = mock_dbck.return_value
    mock_dbck_instance.check_connectivity.return_value = {"source": True, "dest": True}
    mock_dbck_instance.check_problematic_objects.return_value = {
        "no_pk": [{"schema_name": "public", "table_name": "test"}],
        "large_objects": 0,
        "identities": [{"table_schema": "public", "table_name": "test", "column_name": "id"}],
        "unowned_seqs": [{"schema_name": "public", "seq_name": "seq"}],
        "unlogged_tables": [],
        "temp_tables": [],
        "foreign_tables": [],
        "matviews": [{"schema_name": "public", "matview_name": "mv"}]
    }
    mock_dbck_instance.get_database_size_analysis.return_value = {
        "database": {"total_pretty": "10MB"},
        "tables": [{"schema_name": "public", "table_name": "test", "data_pretty": "1MB", "index_pretty": "1MB", "total_pretty": "2MB", "percent": 20}]
    }
    mock_dbck_instance.check_replication_params.return_value = {
        "source": [{"parameter": "wal_level", "actual": "logical", "expected": "logical", "status": "OK"}],
        "dest": [{"parameter": "max_replication_slots", "actual": "10", "expected": "10", "status": "OK"}]
    }
    
    # Mock Migrator
    mock_mig_instance = mock_mig.return_value
    mock_mig_instance.step4a_migrate_schema_pre_data.return_value = (True, "msg", [], [])
    mock_mig_instance.step5_setup_source.return_value = (True, "msg", [], [])
    mock_mig_instance.step6_setup_destination.return_value = (True, "msg", [], [])
    mock_mig_instance.wait_for_sync.return_value = (True, "msg", [], [])
    
    # Mock Validator
    mock_val_instance = mock_val.return_value
    mock_val_instance.audit_objects.return_value = (True, "msg", [], [], [{"type": "TABLE", "source": 1, "dest": 1, "status": "OK"}])
    mock_val_instance.compare_row_counts.return_value = (True, "msg", [], [], [{"table": "public.test", "source": 100, "dest": 100, "diff": 0, "status": "OK"}])
    
    # Mock args
    mock_args.drop_dest = False
    mock_args.no_wait = False
    mock_args.use_stats = False
    
    # Run
    exit_code = cmd_init_replication(mock_args)
    
    # Assert
    assert exit_code == 0
    mock_dbck_instance.check_connectivity.assert_called_once()
    mock_mig_instance.step4a_migrate_schema_pre_data.assert_called_once()
@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
def test_cmd_init_replication_dry_run(mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_args.dry_run = True
    exit_code = cmd_init_replication(mock_args)
    assert exit_code == 0

@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
@patch("src.cli.pipelines.DBChecker")
@patch("src.cli.pipelines.Migrator")
@patch("src.cli.pipelines.PostSync")
@patch("src.cli.pipelines.Validator")
@patch("src.cli.pipelines.ReportGenerator")
def test_cmd_post_migration_success(mock_rg, mock_val, mock_ps, mock_mig, mock_dbck, mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    
    # Mock clients
    mock_sc = MagicMock()
    mock_dc = MagicMock()
    mock_bc.return_value = (mock_sc, mock_dc)
    
    # Mock post sync
    mock_ps_instance = mock_ps.return_value
    mock_ps_instance.refresh_materialized_views.return_value = (True, "msg", [], [])
    mock_ps_instance.sync_sequences.return_value = (True, "msg", [], [])
    mock_ps_instance.enable_triggers.return_value = (True, "msg", [], [])
    mock_ps_instance.sync_lobs.return_value = (True, "msg", [], [])
    mock_ps_instance.reassign_ownership.return_value = (True, "msg", [], [])
    
    # Mock migrator
    mock_mig_instance = mock_mig.return_value
    mock_mig_instance.wait_for_sync.return_value = (True, "msg", [], [])
    mock_mig_instance.step4b_migrate_schema_post_data.return_value = (True, "msg", [], [])
    mock_mig_instance.step10_terminate_replication.return_value = (True, "msg", [], [])
    mock_mig_instance.sync_large_objects.return_value = (True, "msg", [], [])
    
    # Mock validator
    mock_val_instance = mock_val.return_value
    mock_val_instance.audit_objects.return_value = (True, "msg", [], [], [{"type": "TABLE", "source": 1, "dest": 1, "status": "OK"}])
    mock_val_instance.compare_row_counts.return_value = (True, "msg", [], [], [{"table": "public.test", "source": 100, "dest": 100, "diff": 0, "status": "OK"}])
    
    # Run
    exit_code = cmd_post_migration(mock_args)
    assert exit_code == 0

@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
@patch("src.cli.pipelines.DBChecker")
def test_cmd_init_replication_fail_connectivity(mock_dbck, mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    mock_bc.return_value = (MagicMock(), MagicMock())
    
    mock_dbck_instance = mock_dbck.return_value
    mock_dbck_instance.check_connectivity.return_value = {"source": False, "dest": False}
    
    exit_code = cmd_init_replication(mock_args)
    assert exit_code == 2

@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
@patch("src.cli.pipelines.DBChecker")
def test_cmd_post_migration_fail_connectivity(mock_dbck, mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    mock_bc.return_value = (MagicMock(), MagicMock())
    
    mock_dbck_instance = mock_dbck.return_value
    mock_dbck_instance.check_connectivity.return_value = {"source": False, "dest": False}
    
    exit_code = cmd_post_migration(mock_args)
    assert exit_code == 2

@patch("src.cli.pipelines.setup_results_dir")
@patch("src.cli.pipelines.setup_logging")
@patch("src.cli.pipelines.Config")
@patch("src.cli.pipelines.build_clients")
def test_cmd_post_migration_dry_run(mock_bc, mock_cfg, mock_sl, mock_srd, mock_args):
    mock_srd.return_value = "dummy_dir"
    mock_bc.return_value = (MagicMock(), MagicMock())
    mock_args.dry_run = True
    exit_code = cmd_post_migration(mock_args)
    assert exit_code == 0
