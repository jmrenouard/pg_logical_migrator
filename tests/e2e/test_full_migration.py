import pytest
import os
import shutil
import subprocess
import time
from src.db import PostgresClient

def test_full_migration_e2e(tmp_path):
    """
    E2E Test: Full migration from pg_source to pg_target.
    Requirements: Docker containers 'pg_source' and 'pg_target' must be running.
    """
    results_root = tmp_path / "RESULTS"
    os.makedirs(results_root, exist_ok=True)
    
    # We'll use the existing test_migration config or create a temporary one
    config_path = "config_migrator.ini"
    if not os.path.exists(config_path):
        pytest.skip("config_migrator.ini not found. Run 'make env-up' first.")

    # Run the automated migration
    results_dir = str(tmp_path / "e2e_run")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    python_bin = "venv/bin/python" if os.path.exists("venv/bin/python") else "python3"
    
    res = subprocess.run([
        python_bin, "pg_migrator.py", "init-replication",
        "--config", config_path,
        "--drop-dest",
        "--results-dir", results_dir
    ], capture_output=True, text=True, env=env)
    assert res.returncode == 0, f"init-replication failed: {res.stderr}"
    
    res = subprocess.run([
        python_bin, "pg_migrator.py", "post-migration",
        "--config", config_path,
        "--results-dir", results_dir
    ], capture_output=True, text=True, env=env)
    assert res.returncode == 0, f"post-migration failed: {res.stderr}"
    
    # 1. Check if results directory exists
    assert os.path.exists(results_dir)
    
    # 2. Check if log and report exist
    assert os.path.exists(os.path.join(results_dir, "pg_migrator.log"))
    assert os.path.exists(os.path.join(results_dir, "report_init.html"))
    assert os.path.exists(os.path.join(results_dir, "report_post.html"))
    
    # 3. Verify data parity on a sample table (e.g., actor in pagila)
    from src.config import Config
    cfg = Config(config_path)
    sc = PostgresClient(cfg.get_source_conn(), label="SOURCE")
    dc = PostgresClient(cfg.get_dest_conn(), label="DESTINATION")
    
    s_count = sc.execute_query("SELECT count(*) FROM actor;")[0]['count']
    d_count = dc.execute_query("SELECT count(*) FROM actor;")[0]['count']
    
    assert s_count > 0
    assert s_count == d_count
    
    # 4. Verify Large Object (LOB) synchronization
    print("Testing LOB synchronization...")
    # First check if the OID exists on DEST but is broken (native logical repl behavior)
    # The 'init-replication' already copied the table but OIDs refer to non-existent objects on DEST.
    # We call 'sync-lobs' explicitly (though it is included in post-migration pipeline in TUI, 
    # CLI commands are independent unless run via a pipeline).
    cmd_lob = [python_bin, "pg_migrator.py", "sync-lobs", "-c", config_path]
    res_lob = subprocess.run(cmd_lob, capture_output=True, text=True, env=env)
    assert res_lob.returncode == 0, f"sync-lobs failed: {res_lob.stderr}"
    
    # Verify that the new OID exists in pg_largeobject_metadata on DESTINATION
    lob_row = dc.execute_query("SELECT picture_oid FROM schema_lobs.table_with_lobs WHERE id = 1;")[0]
    new_oid = lob_row['picture_oid']
    assert new_oid is not None
    assert new_oid != 0
    
    res_dest_lo = dc.execute_query(f"SELECT count(*) FROM pg_largeobject_metadata WHERE oid = {new_oid};")
    assert res_dest_lo[0]['count'] == 1, f"LOB OID {new_oid} not found on destination"

    # 5. Verify Reverse Replication setup
    print("Testing Reverse Replication setup...")
    cmd_rev = [python_bin, "pg_migrator.py", "setup-reverse", "-c", config_path]
    res_rev = subprocess.run(cmd_rev, capture_output=True, text=True)
    assert res_rev.returncode == 0
    
    # Check if sub_rev exists on SOURCE
    sub_rev_name = cfg.get_replication()["subscription_name"] + "_rev"
    res_src_sub = sc.execute_query(f"SELECT count(*) FROM pg_subscription WHERE subname = '{sub_rev_name}';")
    assert res_src_sub[0]['count'] == 1
    
    print(f"E2E Success: {s_count} actors migrated and Rollback configured.")
