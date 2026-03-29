import pytest
from unittest.mock import MagicMock, patch
from src.db import PostgresClient, execute_shell_command

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
