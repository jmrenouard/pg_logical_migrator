from unittest.mock import MagicMock, patch
from src.migrator import Migrator


def test_sync_large_objects_no_columns():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {"database": "src"}
    mock_config.get_dest_dict.return_value = {"database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:
        mock_instance = mock_pc.return_value
        mock_instance.execute_query.return_value = []

        success, msg, cmds, outs = m.sync_large_objects()
        assert success is True


def test_sync_large_objects_success():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {
        "host": "h1",
        "port": 5432,
        "user": "u1",
        "password": "p1",
        "database": "src"}
    mock_config.get_dest_dict.return_value = {
        "host": "h2",
        "port": 5433,
        "user": "u2",
        "password": "p2",
        "database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1", "column_name": "c1"}],
            [{"attname": "id"}],
            [{"id": 1, "c1": 12345}]
        ]

        mock_s_conn = MagicMock()
        mock_d_conn = MagicMock()

        mock_s_ctx = MagicMock()
        mock_d_ctx = MagicMock()
        mock_pc_instance.get_conn.side_effect = [mock_s_ctx, mock_d_ctx]
        mock_s_ctx.__enter__.return_value = mock_s_conn
        mock_d_ctx.__enter__.return_value = mock_d_conn

        mock_s_cur = MagicMock()
        mock_s_conn.cursor.return_value.__enter__.return_value = mock_s_cur

        mock_d_cur = MagicMock()
        mock_d_conn.cursor.return_value.__enter__.return_value = mock_d_cur

        mock_s_cur.fetchone.side_effect = [{"lo_open": 100}, {"loread": b"data"}, {"loread": None}]
        mock_d_cur.fetchone.side_effect = [{"lo_create": 67890}, {"lo_open": 200}]

        success, msg, cmds, outs = m.sync_large_objects()

        assert success is True
        assert "Processed 1 objects" in msg

        # Check calls on source cursor
        found_lo_open = False
        for call in mock_s_cur.execute.call_args_list:
            if "lo_open" in call[0][0]:
                found_lo_open = True
                assert call[0][1][0] == 12345
        assert found_lo_open

        # Check destination update verification
        update_calls = [call for call in mock_d_cur.execute.call_args_list if hasattr(call[0][0], 'as_string')]
        assert len(update_calls) == 1
        
        # Check commits
        mock_s_conn.commit.assert_called()
        mock_d_conn.commit.assert_called()


def test_sync_large_objects_failure():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {
        "host": "h1",
        "port": 5432,
        "user": "u1",
        "password": "p1",
        "database": "src"}
    mock_config.get_dest_dict.return_value = {
        "host": "h2",
        "port": 5433,
        "user": "u2",
        "password": "p2",
        "database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1", "column_name": "c1"}],
            [{"attname": "id"}],
            [{"id": 1, "c1": 12345}]
        ]

        mock_s_conn = MagicMock()
        mock_d_conn = MagicMock()

        mock_s_ctx = MagicMock()
        mock_d_ctx = MagicMock()
        mock_pc_instance.get_conn.side_effect = [mock_s_ctx, mock_d_ctx]
        mock_s_ctx.__enter__.return_value = mock_s_conn
        mock_d_ctx.__enter__.return_value = mock_d_conn

        mock_s_cur = MagicMock()
        mock_s_conn.cursor.return_value.__enter__.return_value = mock_s_cur
        mock_s_cur.execute.side_effect = Exception("Read error")

        success, msg, cmds, outs = m.sync_large_objects()

        assert success is True
        assert any("Read error" in str(o) for o in outs)
        mock_d_conn.rollback.assert_called()


def test_sync_large_objects_connection_failure():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = "host=h1"
    mock_config.get_dest_conn.return_value = "host=h2"

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1", "column_name": "c1"}],
            [{"attname": "id"}],
            [{"id": 1, "c1": 12345}]
        ]
        mock_pc_instance.get_conn.side_effect = Exception("Connection Failed")
        success, msg, cmds, outs = m.sync_large_objects()

        assert success is False
        assert "Connection Failed" in msg

def test_sync_large_objects_no_data():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {
        "host": "h1",
        "port": 5432,
        "user": "u1",
        "password": "p1",
        "database": "src"}
    mock_config.get_dest_dict.return_value = {
        "host": "h2",
        "port": 5433,
        "user": "u2",
        "password": "p2",
        "database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:
        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1", "column_name": "c1"}],
            [{"attname": "id"}],
            [] # No data returned
        ]

        success, msg, cmds, outs = m.sync_large_objects()
        assert success is True
        assert "Processed 0 objects" in msg

def test_sync_large_objects_outer_failure():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {
        "host": "h1",
        "port": 5432,
        "user": "u1",
        "password": "p1",
        "database": "src"}
    mock_config.get_dest_dict.return_value = {
        "host": "h2",
        "port": 5433,
        "user": "u2",
        "password": "p2",
        "database": "dst"}
    mock_config.get_replication.return_value = {
        "publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_target_schemas.return_value = ["all"]

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:
        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = Exception("Outer query failed")

        success, msg, cmds, outs = m.sync_large_objects()

        assert success is False
        assert "Outer query failed" in msg

