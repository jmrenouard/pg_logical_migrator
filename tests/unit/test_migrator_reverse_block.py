import pytest
from unittest.mock import MagicMock, patch
from src.migrator import Migrator

def test_setup_reverse_replication_blocked_by_forward_sub():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {"user": "u", "password": "p", "host": "h", "port": 5432, "database": "d"}
    mock_config.get_dest_dict.return_value = {"user": "u2", "password": "p2", "host": "h2", "port": 5433, "database": "d2"}
    mock_config.get_replication.return_value = {"publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_source_conn.return_value = {}
    mock_config.get_dest_conn.return_value = {}

    m = Migrator(mock_config)
    
    with patch("src.migrator.PostgresClient") as mock_client:
        # Mocking the destination client to return 1 for the subscription check
        mock_dest_instance = MagicMock()
        mock_dest_instance.execute_query.return_value = [{'count': 1}]
        
        mock_source_instance = MagicMock()
        
        # side_effect to return different mocks based on label
        def client_side_effect(conn, label=None):
            if label == "DESTINATION":
                return mock_dest_instance
            return mock_source_instance
            
        mock_client.side_effect = client_side_effect
        
        success, msg, cmds, outs = m.setup_reverse_replication()
        
        assert success is False
        assert "Forward replication subscription 'sub' still exists" in msg
        assert "Exists" in outs
        
        # Ensure it didn't proceed to create publication on dest
        # (check_sql is the only thing executed on dest before return)
        calls = [c[0][0] for c in mock_dest_instance.execute_script.call_args_list]
        assert not any("CREATE PUBLICATION" in call for call in calls)

def test_setup_reverse_replication_allowed_when_no_forward_sub():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {"user": "u", "password": "p", "host": "h", "port": 5432, "database": "d"}
    mock_config.get_dest_dict.return_value = {"user": "u2", "password": "p2", "host": "h2", "port": 5433, "database": "d2"}
    mock_config.get_replication.return_value = {"publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_source_conn.return_value = {}
    mock_config.get_dest_conn.return_value = {}

    m = Migrator(mock_config)
    
    with patch("src.migrator.PostgresClient") as mock_client:
        mock_dest_instance = MagicMock()
        # No forward sub exists
        mock_dest_instance.execute_query.return_value = [{'count': 0}]
        
        mock_source_instance = MagicMock()
        
        def client_side_effect(conn, label=None):
            if label == "DESTINATION":
                return mock_dest_instance
            return mock_source_instance
            
        mock_client.side_effect = client_side_effect
        
        success, msg, cmds, outs = m.setup_reverse_replication()
        
        assert success is True
        assert "Reverse replication setup successfully" in msg
        
        # Verify it attempted to create reverse publication on dest
        calls_dest = [c[0][0] for c in mock_dest_instance.execute_script.call_args_list]
        assert any("CREATE PUBLICATION pub_rev" in call for call in calls_dest)
        
        # Verify it attempted to create reverse subscription on source
        calls_src = [c[0][0] for c in mock_source_instance.execute_script.call_args_list]
        assert any("CREATE SUBSCRIPTION sub_rev" in call for call in calls_src)

def test_cleanup_reverse_replication():
    mock_config = MagicMock()
    mock_config.get_source_dict.return_value = {"user": "u", "password": "p", "host": "h", "port": 5432, "database": "d"}
    mock_config.get_dest_dict.return_value = {"user": "u2", "password": "p2", "host": "h2", "port": 5433, "database": "d2"}
    mock_config.get_replication.return_value = {"publication_name": "pub", "subscription_name": "sub"}
    mock_config.get_source_conn.return_value = {}
    mock_config.get_dest_conn.return_value = {}

    m = Migrator(mock_config)
    
    with patch("src.migrator.PostgresClient") as mock_client:
        mock_dest_instance = MagicMock()
        mock_source_instance = MagicMock()
        
        def client_side_effect(conn, label=None):
            if label == "DESTINATION":
                return mock_dest_instance
            return mock_source_instance
            
        mock_client.side_effect = client_side_effect
        
        success, msg, cmds, outs = m.cleanup_reverse_replication()
        
        assert success is True
        assert "Reverse replication cleaned up" in msg
        
        # Verify it attempted to drop reverse subscription on source
        calls_src = [c[0][0] for c in mock_source_instance.execute_script.call_args_list]
        assert any("DROP SUBSCRIPTION IF EXISTS sub_rev" in call for call in calls_src)
        
        # Verify it attempted to drop reverse publication on dest
        calls_dest = [c[0][0] for c in mock_dest_instance.execute_script.call_args_list]
        assert any("DROP PUBLICATION IF EXISTS pub_rev" in call for call in calls_dest)
