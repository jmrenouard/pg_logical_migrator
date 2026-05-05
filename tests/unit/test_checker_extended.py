"""Extended tests for src/checker.py — targeting 100% coverage.

Missing lines (original analysis):
  31-32, 70-73, 172, 195-203, 207-214, 226-242, 284-286
"""
from unittest.mock import MagicMock

import pytest

from src.checker import DBChecker


# ---------------------------------------------------------------------------
# check_connectivity
# ---------------------------------------------------------------------------

class TestCheckConnectivityExtended:
    def test_dest_none_skipped(self):
        source = MagicMock()
        source.get_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
        source.get_conn.return_value.__exit__ = MagicMock(return_value=False)
        checker = DBChecker(source, dest_client=None)
        res = checker.check_connectivity()
        assert res["source"] is True
        assert res["dest"] is False

    def test_dest_connection_failure(self):
        source = MagicMock()
        source.get_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
        source.get_conn.return_value.__exit__ = MagicMock(return_value=False)

        dest = MagicMock()
        dest.get_conn.side_effect = Exception("refused")

        checker = DBChecker(source, dest)
        res = checker.check_connectivity()
        assert res["dest"] is False


# ---------------------------------------------------------------------------
# check_problematic_objects — schema filter branch
# ---------------------------------------------------------------------------

class TestCheckProblematicObjectsSchemaFilter:
    def test_with_specific_schema_filter(self):
        """Exercises the schema_filter_identity branch (lines 69-73)."""
        source = MagicMock()
        source.execute_query.return_value = []

        # Patch second call (lo_count) to return an int-like row
        source.execute_query.side_effect = [
            [],       # no_pk
            [{"count": 5}],   # lo_count
            [],       # identities
            [],       # unowned_seqs
            [],       # unlogged_tables
            [],       # temp_tables
            [],       # foreign_tables
            [],       # matviews
            [],       # top_tables
        ]

        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["myschema"]

        checker = DBChecker(source, config=cfg)
        result = checker.check_problematic_objects()
        assert result["large_objects"] == 5

    def test_with_all_schemas(self):
        """schema_filter_identity should be empty when schemas == ['all']."""
        source = MagicMock()
        def mock_execute_query(query, params=None):
            if "pg_largeobject_metadata" in query:
                return [{"count": 0}]
            return []
        source.execute_query.side_effect = mock_execute_query
        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["all"]
        checker = DBChecker(source, config=cfg)
        result = checker.check_problematic_objects()
        assert result["large_objects"] == 0


# ---------------------------------------------------------------------------
# check_replication_params — apply branches
# ---------------------------------------------------------------------------

class TestCheckReplicationParamsApply:
    def _make_client(self, params):
        client = MagicMock()
        client.execute_query.return_value = params
        return client

    def test_apply_wal_level_on_source(self):
        """Lines 206-212: apply when wal_level != logical."""
        params = [
            {"name": "wal_level", "setting": "replica", "unit": None,
             "category": "WAL", "pending_restart": False},
        ]
        source = self._make_client(params)
        dest = self._make_client([])
        checker = DBChecker(source, dest)
        result = checker.check_replication_params(apply_source=True, apply_dest=False)
        source.execute_query.assert_any_call(
            "ALTER SYSTEM SET wal_level = 'logical';")

    def test_apply_fails_gracefully(self):
        """Lines 213-215: apply raises exception — error logged."""
        params = [
            {"name": "wal_level", "setting": "replica", "unit": None,
             "category": "WAL", "pending_restart": False},
        ]
        source = MagicMock()
        # First call: get_pg_parameters; second call: ALTER SYSTEM fails
        source.execute_query.side_effect = [params, Exception("superuser needed")]
        dest = self._make_client([])
        checker = DBChecker(source, dest)
        # Should not raise
        result = checker.check_replication_params(apply_source=True)
        assert result  # just verifies it returns without crashing

    def test_apply_integer_param_below_min(self):
        """Lines 187-198: int param below min triggers apply."""
        params = [
            {"name": "max_replication_slots", "setting": "2", "unit": None,
             "category": "WAL", "pending_restart": False},
        ]
        source = self._make_client(params)
        dest = self._make_client([])
        checker = DBChecker(source, dest)
        result = checker.check_replication_params(apply_source=True)
        source.execute_query.assert_any_call(
            "ALTER SYSTEM SET max_replication_slots = '10';")

    def test_apply_invalid_int_param(self):
        """Lines 200-203: non-integer setting triggers apply."""
        params = [
            {"name": "max_replication_slots", "setting": "off", "unit": None,
             "category": "WAL", "pending_restart": False},
        ]
        source = self._make_client(params)
        dest = self._make_client([])
        checker = DBChecker(source, dest)
        result = checker.check_replication_params(apply_source=True)
        source.execute_query.assert_any_call(
            "ALTER SYSTEM SET max_replication_slots = '10';")

    def test_pending_restart_sets_status(self):
        """Line 172: pending_restart => PENDING RESTART status."""
        params = [
            {"name": "wal_level", "setting": "replica", "unit": None,
             "category": "WAL", "pending_restart": True},
        ]
        source = self._make_client(params)
        dest = self._make_client([])
        checker = DBChecker(source, dest)
        result = checker.check_replication_params()
        assert result["source"][0]["status"] == "PENDING RESTART"

    def test_dest_client_none_skipped(self):
        """Lines 165-167: dest=None skips dest loop."""
        params = [
            {"name": "wal_level", "setting": "logical", "unit": None,
             "category": "WAL", "pending_restart": False},
        ]
        source = self._make_client(params)
        checker = DBChecker(source, dest_client=None)
        result = checker.check_replication_params()
        assert result["dest"] == []


# ---------------------------------------------------------------------------
# get_object_counts
# ---------------------------------------------------------------------------

class TestGetObjectCounts:
    def test_returns_query_result(self):
        client = MagicMock()
        client.execute_query.return_value = [
            {"schemas": 1, "tables": 5, "views": 2, "matviews": 0,
             "sequences": 3, "triggers": 10}]
        checker = DBChecker(client)
        res = checker.get_object_counts(client)
        assert res[0]["tables"] == 5

    def test_with_schema_filter(self):
        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["public"]
        client = MagicMock()
        client.execute_query.return_value = [
            {"schemas": 1, "tables": 2, "views": 0, "matviews": 0,
             "sequences": 0, "triggers": 0}]
        checker = DBChecker(client, config=cfg)
        res = checker.get_object_counts(client)
        assert res is not None


# ---------------------------------------------------------------------------
# get_database_size_analysis — error branch
# ---------------------------------------------------------------------------

class TestGetDatabaseSizeAnalysisError:
    def test_returns_none_on_exception(self):
        client = MagicMock()
        client.execute_query.side_effect = Exception("timeout")
        checker = DBChecker(client)
        result = checker.get_database_size_analysis(client)
        assert result is None

    def test_db_size_none(self):
        client = MagicMock()
        # First call: db_size_rows is empty; second call: table sizes
        client.execute_query.side_effect = [
            [],   # no rows → db_size is None
            [],   # table_sizes
        ]
        checker = DBChecker(client)
        result = checker.get_database_size_analysis(client)
        # Should handle None db_size gracefully
        assert result is not None
        assert result["database"] is None

    def test_db_bytes_zero_uses_one(self):
        """Branch: total_db_bytes == 0 falls back to 1."""
        client = MagicMock()
        client.execute_query.side_effect = [
            [{"total_bytes": 0, "total_pretty": "0 bytes"}],
            [],  # table_sizes
        ]
        checker = DBChecker(client)
        result = checker.get_database_size_analysis(client)
        assert result is not None
