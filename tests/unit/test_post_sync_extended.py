"""Extended tests for src/post_sync.py — targeting 100% coverage.

Missing lines (original analysis):
  13-17, 42-43, 45-46, 77-78, 80-81, 84, 109-110, 112-113,
  116-142, 150-153, 173-176, 194-197, 218-221, 235-245, 259-269,
  283-293, 309-321, 343-346
"""
from unittest.mock import MagicMock, call

import pytest

from src.post_sync import PostSync


# ---------------------------------------------------------------------------
# _get_schema_filter helper
# ---------------------------------------------------------------------------

class TestGetSchemaFilter:
    def test_no_config_returns_empty(self):
        ps = PostSync(MagicMock(), MagicMock(), config=None)
        assert ps._get_schema_filter() == ""

    def test_all_schemas_returns_empty(self):
        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["all"]
        ps = PostSync(MagicMock(), MagicMock(), config=cfg)
        assert ps._get_schema_filter() == ""

    def test_specific_schemas_returns_filter(self):
        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["public", "sales"]
        ps = PostSync(MagicMock(), MagicMock(), config=cfg)
        result = ps._get_schema_filter()
        assert "'public'" in result
        assert "'sales'" in result

    def test_custom_nspname_col(self):
        cfg = MagicMock()
        cfg.get_target_schemas.return_value = ["myschema"]
        ps = PostSync(MagicMock(), MagicMock(), config=cfg)
        result = ps._get_schema_filter(nspname_col="nspname")
        assert "nspname IN" in result


# ---------------------------------------------------------------------------
# refresh_materialized_views
# ---------------------------------------------------------------------------

class TestRefreshMaterializedViews:
    def test_empty_list(self):
        dest = MagicMock()
        dest.execute_query.return_value = []
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.refresh_materialized_views()
        assert ok is True
        assert "0" in msg

    def test_none_result(self):
        dest = MagicMock()
        dest.execute_query.return_value = None
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.refresh_materialized_views()
        assert ok is True

    def test_execute_script_failure(self):
        dest = MagicMock()
        dest.execute_query.return_value = [
            {"schema_name": "public", "matview_name": "mv_fail"}]
        dest.execute_script.side_effect = Exception("permission denied")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.refresh_materialized_views()
        assert ok is True  # outer call succeeds, per-row failure is appended
        assert any("FAILED" in o for o in outs)

    def test_execute_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = Exception("timeout")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.refresh_materialized_views()
        assert ok is False
        assert "timeout" in msg


# ---------------------------------------------------------------------------
# sync_sequences
# ---------------------------------------------------------------------------

class TestSyncSequences:
    def test_empty_sequences(self):
        source = MagicMock()
        source.execute_query.return_value = []
        ps = PostSync(source, MagicMock())
        ok, msg, cmds, outs = ps.sync_sequences()
        assert ok is True

    def test_none_sequences(self):
        source = MagicMock()
        source.execute_query.return_value = None
        ps = PostSync(source, MagicMock())
        ok, msg, cmds, outs = ps.sync_sequences()
        assert ok is True

    def test_sequence_value_fetch_failure(self):
        source = MagicMock()
        source.execute_query.side_effect = [
            [{"schema_name": "public", "seq_name": "seq1"}],
            Exception("cannot read"),
        ]
        ps = PostSync(source, MagicMock())
        ok, msg, cmds, outs = ps.sync_sequences()
        assert ok is True
        assert any("FAILED" in o for o in outs)

    def test_execute_query_failure(self):
        source = MagicMock()
        source.execute_query.side_effect = Exception("db down")
        ps = PostSync(source, MagicMock())
        ok, msg, cmds, outs = ps.sync_sequences()
        assert ok is False

    def test_res_is_none_for_seq(self):
        """Branch: res is falsy after querying sequence value."""
        source = MagicMock()
        source.execute_query.side_effect = [
            [{"schema_name": "public", "seq_name": "seq1"}],
            None,  # no result for the sequence value
        ]
        ps = PostSync(source, MagicMock())
        ok, msg, cmds, outs = ps.sync_sequences()
        assert ok is True


# ---------------------------------------------------------------------------
# enable_triggers
# ---------------------------------------------------------------------------

class TestEnableTriggers:
    def test_success(self):
        dest = MagicMock()
        dest.execute_query.return_value = [
            {"schema_name": "public", "table_name": "t1"},
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.enable_triggers()
        assert ok is True
        dest.execute_script.assert_called_with(
            'ALTER TABLE "public"."t1" ENABLE TRIGGER ALL;')

    def test_script_failure_per_table(self):
        dest = MagicMock()
        dest.execute_query.return_value = [
            {"schema_name": "public", "table_name": "t_fail"}]
        dest.execute_script.side_effect = Exception("locked")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.enable_triggers()
        assert ok is True
        assert any("FAILED" in o for o in outs)

    def test_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = Exception("conn lost")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.enable_triggers()
        assert ok is False


# ---------------------------------------------------------------------------
# disable_triggers
# ---------------------------------------------------------------------------

class TestDisableTriggers:
    def test_success(self):
        dest = MagicMock()
        dest.execute_query.return_value = [
            {"schema_name": "public", "table_name": "t1"},
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.disable_triggers()
        assert ok is True
        dest.execute_script.assert_called_with(
            'ALTER TABLE "public"."t1" DISABLE TRIGGER ALL;')

    def test_script_failure_per_table(self):
        dest = MagicMock()
        dest.execute_query.return_value = [
            {"schema_name": "public", "table_name": "t_fail"}]
        dest.execute_script.side_effect = Exception("readonly")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.disable_triggers()
        assert ok is True
        assert any("FAILED" in o for o in outs)

    def test_empty_tables(self):
        dest = MagicMock()
        dest.execute_query.return_value = []
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.disable_triggers()
        assert ok is True

    def test_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = Exception("fatal")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.disable_triggers()
        assert ok is False


# ---------------------------------------------------------------------------
# _apply_reassign
# ---------------------------------------------------------------------------

class TestApplyReassign:
    def test_success(self):
        dest = MagicMock()
        ps = PostSync(MagicMock(), dest)
        cmds, outs = [], []
        err = ps._apply_reassign('ALTER TABLE t OWNER TO u;', "t", cmds, outs)
        assert err == 0
        assert outs[0] == "  - t: SUCCESS"

    def test_failure(self):
        dest = MagicMock()
        dest.execute_script.side_effect = Exception("permission denied")
        ps = PostSync(MagicMock(), dest)
        cmds, outs = [], []
        err = ps._apply_reassign('ALTER TABLE t OWNER TO u;', "t", cmds, outs)
        assert err == 1
        assert "FAILED" in outs[0]


# ---------------------------------------------------------------------------
# reassign_ownership — error branches
# ---------------------------------------------------------------------------

class TestReassignOwnershipErrors:
    def _make_dest(self, side_effects):
        dest = MagicMock()
        dest.execute_query.side_effect = side_effects
        return dest

    def test_db_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            Exception("db gone"),   # DB name query fails
            [],  # schemas
            [],  # tables
            [],  # views
            [],  # matviews
            [],  # seqs
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        # DB error counted but rest proceeds
        assert any("FAILED" in o for o in outs)

    def test_schema_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],          # DB name ok
            Exception("schema error"),  # schemas fail
            [],  # tables
            [],  # views
            [],  # matviews
            [],  # seqs
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_tables_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],                        # schemas
            Exception("table error"),  # tables fail
            [],  # views
            [],  # matviews
            [],  # seqs
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_views_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],
            [],
            Exception("view error"),
            [],  # matviews
            [],  # seqs
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_matviews_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],
            [],
            [],
            Exception("matview error"),
            [],  # seqs
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_seqs_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],
            [],
            [],
            [],
            Exception("seq error"),
            [],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_funcs_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],
            [],
            [],
            [],
            [],
            Exception("func error"),
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_types_query_failure(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [],
            [],
            [],
            [],
            [],
            [],
            Exception("type error"),
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert any("FAILED" in o for o in outs)

    def test_with_views_and_matviews(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "test_db"}],
            [{"schema_name": "public"}],
            [],  # tables
            [{"schema_name": "public", "obj_name": "v1"}],   # views
            [{"schema_name": "public", "obj_name": "mv1"}],  # matviews
            [{"schema_name": "public", "obj_name": "seq1"}], # seqs
            [{"schema_name": "public", "func_name": "fn1", "func_args": "", "func_type": "FUNCTION"}],  # funcs
            [],  # types
        ]
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert ok is True
        dest.execute_script.assert_any_call(
            'ALTER VIEW "public"."v1" OWNER TO "owner";')
        dest.execute_script.assert_any_call(
            'ALTER MATERIALIZED VIEW "public"."mv1" OWNER TO "owner";')
        dest.execute_script.assert_any_call(
            'ALTER SEQUENCE "public"."seq1" OWNER TO "owner";')
        dest.execute_script.assert_any_call(
            'ALTER FUNCTION "public"."fn1"() OWNER TO "owner";')

    def test_with_errors_in_msg(self):
        dest = MagicMock()
        dest.execute_query.side_effect = [
            [{"db": "mydb"}],
            [{"schema_name": "s1"}],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        dest.execute_script.side_effect = Exception("owner fail")
        ps = PostSync(MagicMock(), dest)
        ok, msg, cmds, outs = ps.reassign_ownership("owner")
        assert ok is False
        assert "errors" in msg
