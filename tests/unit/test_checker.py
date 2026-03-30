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
