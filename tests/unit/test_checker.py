import pytest
from unittest.mock import MagicMock
from src.checker import DBChecker

def test_check_connectivity():
    source = MagicMock()
    dest = MagicMock()
    
    # Success case
    source.get_conn.return_value.__enter__.return_value = MagicMock()
    dest.get_conn.return_value.__enter__.return_value = MagicMock()
    
    checker = DBChecker(source, dest)
    res = checker.check_connectivity()
    assert res == {"source": True, "dest": True}
    
    # Failure case
    source.get_conn.side_effect = Exception("error")
    res = checker.check_connectivity()
    assert res == {"source": False, "dest": True}

def test_check_problematic_objects():
    source = MagicMock()
    source.execute_query.side_effect = [
        [{"schema": "public", "table": "no_pk_table"}], # no_pk
        [{"count": 5}],                                 # large objects
        [],                                             # identities
        [],                                             # unowned seqs
        [],                                             # unlogged tables
        [],                                             # temp tables
        [],                                             # foreign tables
        []                                              # matviews
    ]
    
    checker = DBChecker(source)
    res = checker.check_problematic_objects()
    
    assert len(res["no_pk"]) == 1
    assert res["large_objects"] == 5
    assert len(res["identities"]) == 0
    assert len(res["unowned_seqs"]) == 0

def test_check_replication_params():
    source = MagicMock()
    source.execute_query.return_value = [
        {"name": "wal_level", "setting": "minimal"},
        {"name": "max_replication_slots", "setting": "10"}
    ]
    
    checker = DBChecker(source)
    res = checker.check_replication_params()
    
    wal_param = next(p for p in res['source'] if p['parameter'] == 'wal_level')
    assert wal_param['status'] == 'FAIL'
    assert wal_param['expected'] == 'logical'

def test_get_database_size_analysis():
    source = MagicMock()
    source.execute_query.side_effect = [
        [{"total_bytes": 1024, "total_pretty": "1 kB"}], # db size
        [{"schema_name": "public", "table_name": "t1", "total_pretty": "512 B", "percent": 50.0}] # table size
    ]
    
    checker = DBChecker(source)
    res = checker.get_database_size_analysis(source)
    
    assert res["database"]["total_pretty"] == "1 kB"
    assert res["tables"][0]["table_name"] == "t1"
    assert res["tables"][0]["percent"] == 50.0

def test_db_checker_schema_filter():
    source = MagicMock()
    mock_config = MagicMock()
    mock_config.get_target_schemas.return_value = ["s1", "s2"]
    
    checker = DBChecker(source, config=mock_config)
    sf = checker._get_schema_filter("col")
    assert "col IN ('s1', 's2')" in sf
    
    mock_config.get_target_schemas.return_value = ["all"]
    sf = checker._get_schema_filter("col")
    assert sf == ""
