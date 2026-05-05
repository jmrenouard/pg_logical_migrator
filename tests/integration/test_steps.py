
def test_step01_connectivity(db_checker):
    """Step 1: Check connectivity."""
    res = db_checker.check_connectivity()
    assert res['source'] is True
    assert res['dest'] is True


def test_step02_diagnostics(db_checker):
    """Step 2: Check problematic objects."""
    res = db_checker.check_problematic_objects()
    assert "no_pk" in res
    assert "large_objects" in res
    # Depending on whether extra test data was injected, this might be > 0
    assert res["large_objects"] >= 0


def test_step03_parameters(db_checker):
    """Step 3: Check PG parameters."""
    res = db_checker.check_replication_params()
    if isinstance(res, tuple):
        res = res[0]
    assert len(res) > 0
    assert 'source' in res
    assert 'dest' in res

    source_params = {p['parameter']: p for p in res['source']}
    assert 'wal_level' in source_params
    assert source_params['wal_level']['status'] in [
        'OK', 'WARNING', 'ERROR', 'PENDING RESTART']


def test_step04a_schema_pre_data(migrator, dest_client):
    """Step 4a: Schema copy pre-data."""
    success, msg, *_ = migrator.step4a_migrate_schema_pre_data(drop_dest=True)
    assert success is True

    # Verify tables exist on dest
    query = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
    res = dest_client.execute_query(query)
    # Pagila has many tables
    assert res[0]['count'] > 0


def test_step05_setup_source(migrator, source_client):
    """Step 5: Create publication."""
    success, msg, *_ = migrator.step5_setup_source()
    assert success is True

    # Verify publication
    res = source_client.execute_query("SELECT pubname FROM pg_publication;")
    assert len(res) > 0


def test_step06_setup_destination(migrator, dest_client):
    """Step 6: Create subscription."""
    success, msg, *_ = migrator.step6_setup_destination()
    assert success is True

    # Verify subscription
    res = dest_client.execute_query("SELECT subname FROM pg_subscription;")
    assert len(res) > 0


def test_step07_wait_for_sync(migrator):
    """Step 7: Wait for initial synchronization."""
    success, msg, *_ = migrator.wait_for_sync(timeout=600, show_progress=False)
    assert success is True


def test_step08_cleanup(migrator, source_client, dest_client):
    """Step 10: Terminate replication."""
    success, msg, *_ = migrator.step10_terminate_replication()
    assert success is True

    # Verify removal
    sub_name = migrator.replication_cfg['subscription_name']
    pub_name = migrator.replication_cfg['publication_name']
    res_sub = dest_client.execute_query(f"SELECT subname FROM pg_subscription WHERE subname = '{sub_name}';")
    assert len(res_sub) == 0
    res_pub = source_client.execute_query(f"SELECT pubname FROM pg_publication WHERE pubname = '{pub_name}';")
    assert len(res_pub) == 0


def test_step09_schema_post_data(migrator):
    """Step 4b: Schema copy post-data."""
    success, msg, *_ = migrator.step4b_migrate_schema_post_data()
    assert success is True


def test_step10_sequences(post_sync, dest_client):
    """Step 8: Sync sequences."""
    post_sync.sync_sequences()


def test_step11_activate_sequences(post_sync):
    """Step 9: Activate sequences."""
    post_sync.activate_sequences()


def test_step12_activate_triggers(post_sync):
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
