import pytest
from unittest.mock import MagicMock, patch
from src.db import PostgresClient, execute_shell_command
import sys

def test_postgres_client_execute_query():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [{"id": 1, "name": "test"}]
        
        # Setup context manager for get_conn
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        # psycopg 3 Connection.execute returns a cursor
        mock_conn.execute.return_value = mock_cur
        
        results = client.execute_query("SELECT * FROM test", fetch=True)
        assert results == [{"id": 1, "name": "test"}]
        mock_conn.execute.assert_called_once_with("SELECT * FROM test", None)

def test_shell_command_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "Success output"
        mock_run.return_value.returncode = 0
        
        success, output = execute_shell_command("ls")
        assert success is True
        assert output == "Success output"

def test_shell_command_failure():
    import subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "ls", stderr="Error output")
        
        success, output = execute_shell_command("ls")
        assert success is False
        assert output == "Error output"

def test_pretty_size():
    from src.db import pretty_size
    assert pretty_size(None) == "0 B"
    assert pretty_size(500) == "500 B"
    assert pretty_size(1024) == "1 kB"
    assert pretty_size(1500 * 1024 * 1024) == "1.5 GB"
    assert pretty_size(1.5 * 1024**6) == "1536.0 PB"

def test_get_conn():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch("psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        with client.get_conn() as conn:
            assert conn == mock_conn
        mock_connect.assert_called_once()
        mock_conn.close.assert_called_once()

def test_execute_query_with_params():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [{"id": 1}]
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_cur
        
        results = client.execute_query("SELECT * FROM test WHERE id = %s", params=[1], fetch=True)
        assert results == [{"id": 1}]
        mock_conn.execute.assert_called_once_with("SELECT * FROM test WHERE id = %s", [1])


def test_postgres_client_execute_query_no_fetch():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        results = client.execute_query("UPDATE test SET name='test'", fetch=False)
        assert results is None
        mock_conn.execute.assert_called_once_with("UPDATE test SET name='test'", None)

def test_postgres_client_execute_query_error():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("Query failed")
        with pytest.raises(Exception, match="Query failed"):
            client.execute_query("SELECT 1")

def test_postgres_client_execute_script():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        client.execute_script("SELECT 1; SELECT 2;", autocommit=False)
        mock_conn.execute.assert_called_once_with("SELECT 1; SELECT 2;")
        mock_conn.commit.assert_called_once()

def test_postgres_client_execute_script_error():
    client = PostgresClient("postgresql://user:pwd@host:5432/db")
    with patch.object(PostgresClient, "get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("Script failed")
        with pytest.raises(Exception, match="Script failed"):
            client.execute_script("SELECT 1; SELECT 2;")

def test_verbose_print(capsys):
    import src.db
    from src.db import _verbose_print
    src.db.VERBOSE = True
    _verbose_print("TEST", "Hello World", file=sys.stdout)
    out, _ = capsys.readouterr()
    assert "[VERBOSE:TEST]" in out
    assert "Hello World" in out
    
    _verbose_print("TEST", ["Line 1", "Line 2"], file=sys.stdout)
    out, _ = capsys.readouterr()
    assert "[VERBOSE:TEST]" in out
    assert "Line 1" in out
    assert "Line 2" in out
    src.db.VERBOSE = False
