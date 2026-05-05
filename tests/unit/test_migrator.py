from unittest.mock import MagicMock, patch
from src.migrator import Migrator


def test_migrator_init():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {
        "user": "u",
        "password": "p",
        "host": "h",
        "port": 5432,
        "database": "d"}
    mock_config.get_dest_conn.return_value = {
        "user": "u2",
        "password": "p2",
        "host": "h2",
        "port": 5433,
        "database": "d2"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}

    m = Migrator(mock_config)
    assert m.replication_cfg["publication_name"] == "pub"


def test_step5_setup_source():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = "postgresql://u:p@h:5432/d"
    mock_config.get_dest_conn.return_value = "postgresql://u2:p2@h2:5433/d2"
    mock_config.get_replication.return_value = {
        "publication_name": "test_pub",
        "subscription_name": "test_sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)
    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.execute_query.return_value = []
        success, msg, cmds, outs = m.step5_setup_source()

        assert success is True
        assert "test_pub" in msg
        mock_instance.execute_script.assert_any_call(
            "CREATE PUBLICATION test_pub FOR ALL TABLES;")


def test_step6_setup_destination():
    mock_config = MagicMock()
    # Mock return values for methods used in __init__
    mock_config.get_source_conn.return_value = {
        "user": "u", "password": "p", "database": "db"}
    mock_config.get_dest_conn.return_value = {
        "user": "u2",
        "password": "p2",
        "database": "db2",
        "host": "h2",
        "port": 5433}
    mock_config.get_replication.return_value = {
        "publication_name": "test_pub",
        "subscription_name": "test_sub"}

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        success, msg, cmds, outs = m.step6_setup_destination()

        assert success is True
        assert "test_sub" in msg
        # Check if the subscription creation call was made
        calls = [c[0][0] for c in mock_instance.execute_script.call_args_list]
        assert any("CREATE SUBSCRIPTION test_sub" in call for call in calls)


def test_step4a_migrate_schema_pre_data():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {
        "user": "u", "password": "p", "database": "db"}
    mock_config.get_dest_conn.return_value = {
        "user": "u2",
        "password": "p2",
        "database": "db2",
        "host": "h2",
        "port": 5433}
    mock_config.get_target_schemas.return_value = ["public"]

    m = Migrator(mock_config)

    with patch("src.db.execute_shell_command") as mock_exec, patch("src.migrator.PostgresClient"):
        mock_exec.return_value = (True, "mock migrated")

        success, msg, cmds, outs = m.step4a_migrate_schema_pre_data()

        assert success is True
        assert "PRE-DATA" in msg
        assert len(cmds) > 0


def test_step4b_migrate_schema_post_data():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {
        "user": "u", "password": "p", "database": "db"}
    mock_config.get_dest_conn.return_value = {
        "user": "u2",
        "password": "p2",
        "database": "db2",
        "host": "h2",
        "port": 5433}
    mock_config.get_target_schemas.return_value = ["public"]

    m = Migrator(mock_config)

    with patch("src.db.execute_shell_command") as mock_exec:
        mock_exec.return_value = (True, "mock migrated")

        success, msg, cmds, outs = m.step4b_migrate_schema_post_data()

        assert success is True
        assert "POST-DATA" in msg
        assert len(cmds) > 0


def test_get_initial_copy_progress():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {"database": "src"}
    mock_config.get_dest_conn.return_value = {"database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        # 1. source_tables query
        # 2. rel_status query
        # 3. progress_status query
        mock_instance.execute_query.side_effect = [
            [{"schemaname": "public", "tablename": "t1",
                "total_bytes": 1000}],  # source sizes
            [{"table_name": "public.t1", "state": "d"}],  # dest states
            [{"table_name": "public.t1",
              "bytes_processed": 500,
              "bytes_total": 1000}]  # progress
        ]

        res = m.get_initial_copy_progress()

        assert res["summary"]["percent_bytes"] == 50.0
        assert res["tables"][0]["table_name"] == "public.t1"


def test_migrator_wait_for_sync():
    mock_config = MagicMock()
    mock_config.get_dest_conn.return_value = {
        "database": "dst",
        "user": "u",
        "password": "p",
        "host": "h",
        "port": 5433}
    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        # Simulate:
        # 1. sub exists -> 1 pending table
        # 2. sub exists -> 0 pending tables
        mock_instance.execute_query.side_effect = [
            [{"cnt": 1}],
            [{"total": 1, "pending": 1}],
            [{"cnt": 1}],
            [{"total": 1, "pending": 0}]
        ]
        # Skip progress report fetch during wait
        m.get_initial_copy_progress = MagicMock(return_value=None)

        success, msg, cmds, outs = m.wait_for_sync(
            timeout=5, poll_interval=0.1, show_progress=False)
        assert success is True
        assert "completed" in msg


def test_migrator_setup_reverse_replication():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {
        "database": "src",
        "user": "u1",
        "password": "p1",
        "host": "h1",
        "port": 5432}
    mock_config.get_dest_conn.return_value = {
        "database": "dst",
        "user": "u2",
        "password": "p2",
        "host": "h2",
        "port": 5433}
    mock_config.get_replication.return_value = {
        "publication_name": "pub",
        "subscription_name": "sub",
        "dest_host": "172.17.0.1",
        "dest_port": 5433
    }

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.execute_query.return_value = [{'count': 0}]
        success, msg, cmds, outs = m.setup_reverse_replication()

        assert success is True
        # Verify DEST (Publisher) commands
        assert any("CREATE PUBLICATION pub_rev" in str(c) for c in cmds)
        # Verify SOURCE (Subscriber) commands
        assert any("CREATE SUBSCRIPTION sub_rev" in str(c) for c in cmds)
        assert any("host=172.17.0.1" in str(c) for c in cmds)
