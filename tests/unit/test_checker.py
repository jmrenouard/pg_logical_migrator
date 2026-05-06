"""
test_checker.py — Unit tests for DBChecker (pre-migration diagnostics).

Each test validates a single, well-defined behaviour of the DBChecker class.
Previously, some tests (e.g. test_check_connectivity) combined success and
failure scenarios in a single function, hiding failures; they have been split
into atomic tests for clarity.
"""

from unittest.mock import MagicMock
from src.checker import DBChecker


# ---------------------------------------------------------------------------
# Connectivity checks
# ---------------------------------------------------------------------------

class TestCheckConnectivity:
    """Verify DBChecker.check_connectivity behaviour for reachable/unreachable hosts."""

    def test_both_reachable(self):
        """Both source and destination databases are reachable → both True."""
        source = MagicMock()
        dest = MagicMock()
        source.get_conn.return_value.__enter__.return_value = MagicMock()
        dest.get_conn.return_value.__enter__.return_value = MagicMock()

        checker = DBChecker(source, dest)
        res = checker.check_connectivity()
        assert res == {"source": True, "dest": True}

    def test_source_unreachable(self):
        """Source database unreachable → source=False, dest=True."""
        source = MagicMock()
        dest = MagicMock()
        source.get_conn.side_effect = Exception("Connection refused")
        dest.get_conn.return_value.__enter__.return_value = MagicMock()

        checker = DBChecker(source, dest)
        res = checker.check_connectivity()
        assert res["source"] is False
        assert res["dest"] is True

    def test_dest_unreachable(self):
        """Destination database unreachable → source=True, dest=False."""
        source = MagicMock()
        dest = MagicMock()
        source.get_conn.return_value.__enter__.return_value = MagicMock()
        dest.get_conn.side_effect = Exception("Connection refused")

        checker = DBChecker(source, dest)
        res = checker.check_connectivity()
        assert res["source"] is True
        assert res["dest"] is False


# ---------------------------------------------------------------------------
# Problematic objects scan
# ---------------------------------------------------------------------------

def test_check_problematic_objects():
    """Verify diagnostic scan identifies tables without primary keys and LOBs."""
    source = MagicMock()
    source.execute_query.side_effect = [
        [{"schema": "public", "table": "no_pk_table"}],  # no_pk
        [{"count": 5}],                                 # large objects
        [],                                             # identities
        [],                                             # unowned seqs
        [],                                             # unlogged tables
        [],                                             # temp tables
        [],                                             # foreign_tables
        [],                                             # matviews
        []                                              # top_tables
    ]

    checker = DBChecker(source)
    res = checker.check_problematic_objects()

    assert len(res["no_pk"]) == 1
    assert res["large_objects"] == 5
    assert len(res["identities"]) == 0
    assert len(res["unowned_seqs"]) == 0


# ---------------------------------------------------------------------------
# Replication parameters
# ---------------------------------------------------------------------------

def test_check_replication_params():
    """Verify that wal_level=minimal is flagged as FAIL (expected: logical)."""
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


# ---------------------------------------------------------------------------
# Database size analysis
# ---------------------------------------------------------------------------

def test_get_database_size_analysis():
    """Verify database size analysis returns correct structure and values."""
    source = MagicMock()
    source.execute_query.side_effect = [
        [{"total_bytes": 1024, "total_pretty": "1 kB"}],  # db size
        [{"schema_name": "public",
          "table_name": "t1",
          "total_pretty": "512 B",
          "percent": 50.0}]  # table size
    ]

    checker = DBChecker(source)
    res = checker.get_database_size_analysis(source)

    assert res["database"]["total_pretty"] == "1 kB"
    assert res["tables"][0]["table_name"] == "t1"
    assert res["tables"][0]["percent"] == 50.0


# ---------------------------------------------------------------------------
# Schema filter (now inherited from SchemaFilterMixin)
# ---------------------------------------------------------------------------

class TestSchemaFilter:
    """Verify that SchemaFilterMixin behaviour is correctly inherited by DBChecker."""

    def test_specific_schemas_filter(self):
        """Specific schemas should produce a SQL IN clause."""
        source = MagicMock()
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ["s1", "s2"]

        checker = DBChecker(source, config=mock_config)
        sf = checker._get_schema_filter("col")
        assert "col IN ('s1', 's2')" in sf

    def test_all_schemas_returns_empty(self):
        """'all' schemas should return an empty filter string."""
        source = MagicMock()
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ["all"]

        checker = DBChecker(source, config=mock_config)
        sf = checker._get_schema_filter("col")
        assert sf == ""
