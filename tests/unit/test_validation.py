"""
test_validation.py — Unit tests for the Validator class.

Tests cover row count comparison (exact and estimated modes) and structural
object parity auditing between source and destination databases.
"""

from unittest.mock import MagicMock
from src.validation import Validator


def test_validator_compare_row_counts_exact():
    """Verify exact row count comparison reports OK when counts match."""
    source = MagicMock()
    dest = MagicMock()

    # Mock table list
    source.execute_query.side_effect = [
        [{"schema_name": "public", "table_name": "t1"}],  # table list
        [{"count": 10}],                                # source t1 count
        [{"count": 10}]                                 # dest t1 count
    ]
    dest.execute_query.return_value = [{"count": 10}]

    v = Validator(source, dest)
    success, summary, cmds, outs, report = v.compare_row_counts(
        use_stats=False)

    assert success is True
    assert len(report) == 1
    assert report[0]["status"] == "OK"
    assert report[0]["source"] == 10


def test_validator_compare_row_counts_stats():
    """Verify estimated (pg_stat) row comparison reports DIFF on count mismatch."""
    source = MagicMock()
    dest = MagicMock()

    source.execute_query.return_value = [
        {"schema_name": "public", "table_name": "t1", "row_count": 100}
    ]
    dest.execute_query.return_value = [
        {"schema_name": "public", "table_name": "t1", "row_count": 95}
    ]

    v = Validator(source, dest)
    success, summary, cmds, outs, report = v.compare_row_counts(use_stats=True)

    assert success is True
    assert len(report) == 1
    assert report[0]["status"] == "DIFF"
    assert report[0]["source"] == 100
    assert report[0]["dest"] == 95


def test_validator_audit_objects():
    """Verify structural audit flags DIFF for views but OK for tables when counts match."""
    source = MagicMock()
    dest = MagicMock()

    source.execute_query.return_value = [
        {"type": "TABLE", "count": 10},
        {"type": "VIEW", "count": 5}
    ]
    dest.execute_query.return_value = [
        {"type": "TABLE", "count": 10},
        {"type": "VIEW", "count": 4}
    ]

    v = Validator(source, dest)
    success, summary, cmds, outs, report = v.audit_objects()

    assert success is True
    assert report[0]["type"] == "TABLE"
    assert report[0]["status"] == "OK"
    assert report[1]["type"] == "VIEW"
    assert report[1]["status"] == "DIFF"
