import pytest
from unittest.mock import MagicMock, patch
from src.migrator import Migrator

def test_migrator_init():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = {"user": "u", "password": "p", "host": "h", "port": 5432, "database": "d"}
    mock_config.get_dest_conn.return_value = {"user": "u2", "password": "p2", "host": "h2", "port": 5433, "database": "d2"}
    mock_config.get_replication.return_value = {"publication_name": "pub", "subscription_name": "sub"}
    
    m = Migrator(mock_config)
    assert m.replication_cfg["publication_name"] == "pub"

def test_step5_setup_source():
    mock_config = MagicMock()
    mock_config.get_source_conn.return_value = "postgresql://u:p@h:5432/d"
    mock_config.get_dest_conn.return_value = "postgresql://u2:p2@h2:5433/d2"
    mock_config.get_replication.return_value = {"publication_name": "test_pub", "subscription_name": "test_sub"}
    
    m = Migrator(mock_config)
    
    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.execute_query.return_value = []
        success, msg, cmds, outs = m.step5_setup_source()
        
        assert success is True
        assert "test_pub" in msg
        mock_instance.execute_script.assert_any_call("CREATE PUBLICATION test_pub FOR ALL TABLES;")

def test_step6_setup_destination():
    mock_config = MagicMock()
    # Mock return values for methods used in __init__
    mock_config.get_source_conn.return_value = {"user": "u", "password": "p", "database": "db"}
    mock_config.get_dest_conn.return_value = {"user": "u2", "password": "p2", "database": "db2", "host": "h2", "port": 5433}
    mock_config.get_replication.return_value = {"publication_name": "test_pub", "subscription_name": "test_sub"}
    
    m = Migrator(mock_config)
    
    with patch("src.migrator.PostgresClient") as mock_client:
        mock_instance = mock_client.return_value
        success, msg, cmds, outs = m.step6_setup_destination()
        
        assert success is True
        assert "test_sub" in msg
        # Check if the subscription creation call was made
        calls = [c[0][0] for c in mock_instance.execute_script.call_args_list]
        assert any("CREATE SUBSCRIPTION test_sub" in call for call in calls)
