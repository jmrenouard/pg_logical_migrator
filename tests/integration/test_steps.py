import pytest
import os
import subprocess
from src.db import PostgresClient
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator

def test_step1_connectivity(db_checker):
    """Step 1: Check connectivity."""
    res = db_checker.check_connectivity()
    assert res['source'] is True
    assert res['dest'] is True

def test_step2_diagnostics(db_checker):
    """Step 2: Check problematic objects."""
    res = db_checker.check_problematic_objects()
    assert "no_pk" in res
    assert "large_objects" in res
    assert res["large_objects"] == 0

def test_step3_parameters(db_checker):
    """Step 3: Check PG parameters."""
    res = db_checker.check_replication_params()
    if isinstance(res, tuple):
        res = res[0]
    assert len(res) > 0
    assert 'source' in res
    assert 'dest' in res
    
    source_params = {p['parameter']: p for p in res['source']}
    assert 'wal_level' in source_params
    assert source_params['wal_level']['status'] in ['OK', 'WARNING', 'ERROR', 'PENDING RESTART']

def test_step4_schema_migration(migrator, dest_client):
    """Step 4: Schema copy."""
    success, msg, *_ = migrator.step4_migrate_schema()
    assert success is True
    
    # Verify tables exist on dest
    query = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
    res = dest_client.execute_query(query)
    # Pagila has many tables
    assert res[0]['count'] > 0

def test_step5_setup_source(migrator, source_client):
    """Step 5: Create publication."""
    success, msg, *_ = migrator.step5_setup_source()
    assert success is True
    
    # Verify publication
    res = source_client.execute_query("SELECT pubname FROM pg_publication;")
    assert len(res) > 0

def test_step6_setup_destination(migrator, dest_client):
    """Step 6: Create subscription."""
    success, msg, *_ = migrator.step6_setup_destination()
    assert success is True
    
    # Verify subscription
    res = dest_client.execute_query("SELECT subname FROM pg_subscription;")
    assert len(res) > 0

def test_step8_sequences(post_sync, dest_client):
    """Step 8: Sync sequences."""
    # This might need some data to be useful, but let's check it runs
    post_sync.sync_sequences()

def test_step9_activate_sequences(post_sync):
    """Step 9: Activate sequences."""
    post_sync.activate_sequences()

def test_step10_activate_triggers(post_sync):
    """Step 10: Activate triggers."""
    post_sync.enable_triggers()

def test_step13_validation_audit(db_validator):
    """Step 13: Object parity audit."""
    success, summary, cmds, outs, report = db_validator.audit_objects()
    assert success is True
    assert isinstance(report, list)

def test_step14_row_counts(db_validator):
    """Step 14: Compare row counts."""
    success, summary, cmds, outs, report = db_validator.compare_row_counts()
    assert success is True
    assert isinstance(report, list)

def test_step12_cleanup(migrator, source_client, dest_client):
    """Step 12: Cleanup (Termination)."""
    success, msg, *_ = migrator.step12_terminate_replication()
    assert success is True
    
    # Verify removal
    res_sub = dest_client.execute_query("SELECT subname FROM pg_subscription;")
    assert len(res_sub) == 0
    res_pub = source_client.execute_query("SELECT pubname FROM pg_publication;")
    assert len(res_pub) == 0
