"""
test_post_sync.py — Unit tests for the PostSync class.

Tests cover post-migration cleanup and object synchronization tasks, including
refreshing materialized views, synchronizing sequences, enabling triggers,
and reassigning ownership.
"""

from unittest.mock import MagicMock
from src.post_sync import PostSync


def test_post_sync_refresh_matviews():
    """Verify materialized views are correctly refreshed."""
    source = MagicMock()
    dest = MagicMock()

    dest.execute_query.return_value = [
        {"schema_name": "public", "matview_name": "mv1"}]

    ps = PostSync(source, dest)
    success, msg, cmds, outs = ps.refresh_materialized_views()

    assert success is True
    dest.execute_script.assert_called_with(
        'REFRESH MATERIALIZED VIEW "public"."mv1";')


def test_post_sync_sequences():
    """Verify sequence synchronization fetches the last value from source and applies to dest."""
    source = MagicMock()
    dest = MagicMock()

    source.execute_query.side_effect = [
        [{"schema_name": "public", "seq_name": "s1"}],  # seq list
        [{"last_value": 42, "is_called": True}]        # s1 value
    ]

    ps = PostSync(source, dest)
    success, msg, cmds, outs = ps.sync_sequences()

    assert success is True
    dest.execute_script.assert_called_with(
        "SELECT setval('\"public\".\"s1\"', 42, true);")


def test_post_sync_enable_triggers():
    """Verify all triggers are enabled on the target tables after sync."""
    source = MagicMock()
    dest = MagicMock()

    dest.execute_query.return_value = [
        {"schema_name": "public", "table_name": "t1"}]

    ps = PostSync(source, dest)
    success, msg, cmds, outs = ps.enable_triggers()

    assert success is True
    dest.execute_script.assert_called_with(
        'ALTER TABLE "public"."t1" ENABLE TRIGGER ALL;')


def test_post_sync_reassign_ownership():
    """Verify ownership of databases, schemas, tables, and types are correctly reassigned."""
    source = MagicMock()
    dest = MagicMock()

    # Mock queries for: DB name, Schemas, Tables, Views, MatViews, Seqs,
    # Funcs, Types
    dest.execute_query.side_effect = [
        [{"db": "test_db"}],  # DB
        [{"schema_name": "public"}],  # Schemas
        [{"schema_name": "public", "obj_name": "t1"}],  # Tables
        [],  # Views
        [],  # MatViews
        [],  # Seqs
        [],  # Funcs
        [{"schema_name": "public", "type_name": "enum1"}]  # Types
    ]

    ps = PostSync(source, dest)
    success, msg, cmds, outs = ps.reassign_ownership("new_owner")

    assert success is True
    assert "Reassigned 4/4" in msg
    # Verify some expected calls
    dest.execute_script.assert_any_call(
        'ALTER DATABASE "test_db" OWNER TO "new_owner";')
    dest.execute_script.assert_any_call(
        'ALTER SCHEMA "public" OWNER TO "new_owner";')
    dest.execute_script.assert_any_call(
        'ALTER TABLE "public"."t1" OWNER TO "new_owner";')
    dest.execute_script.assert_any_call(
        'ALTER TYPE "public"."enum1" OWNER TO "new_owner";')
