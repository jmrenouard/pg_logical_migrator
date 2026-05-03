from unittest.mock import MagicMock, patch
from src.migrator import Migrator


def test_sync_unlogged_tables_no_tables():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {"database": "src"}
    mock_config.get_dest_dict.return_value = {"database": "dst"}

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:
        mock_instance = mock_pc.return_value
        mock_instance.execute_query.return_value = []

        success, msg, synced_count, outs = m.sync_unlogged_tables()
        assert success is True
        assert synced_count == 0


def test_sync_unlogged_tables_success():
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

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1"}],
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
        
        copy_out_ctx = MagicMock()
        mock_s_cur.copy.return_value = copy_out_ctx
        copy_out_iter = MagicMock()
        copy_out_ctx.__enter__.return_value = ["data1", "data2"]

        mock_d_cur = MagicMock()
        mock_d_conn.cursor.return_value.__enter__.return_value = mock_d_cur
        
        copy_in_ctx = MagicMock()
        mock_d_cur.copy.return_value = copy_in_ctx
        copy_in_obj = MagicMock()
        copy_in_ctx.__enter__.return_value = copy_in_obj

        success, msg, synced_count, outs = m.sync_unlogged_tables()

        assert success is True
        assert synced_count == 1
        assert "Successfully synced 1 UNLOGGED tables." in msg
        mock_s_conn.commit.assert_called_once()
        mock_d_conn.commit.assert_called_once()
        mock_d_cur.execute.assert_called_with('TRUNCATE TABLE "public"."t1";')
        assert copy_in_obj.write.call_count == 2


def test_sync_unlogged_tables_failure():
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

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = [
            [{"schema_name": "public", "table_name": "t1"}],
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
        mock_d_cur.execute.side_effect = Exception("Truncate error")

        success, msg, synced_count, outs = m.sync_unlogged_tables()

        assert success is False
        assert "Truncate error" in msg
        mock_d_conn.rollback.assert_called_once()
        mock_s_conn.rollback.assert_called_once()


def test_sync_unlogged_tables_connection_failure():
    mock_config = MagicMock()

    m = Migrator(mock_config)

    with patch("src.migrator.PostgresClient") as mock_pc:

        mock_pc_instance = mock_pc.return_value
        mock_pc_instance.execute_query.side_effect = Exception("Connection Failed")
        success, msg, synced_count, outs = m.sync_unlogged_tables()

        assert success is False
        assert "Connection Failed" in msg
