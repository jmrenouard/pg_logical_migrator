"""Extended tests for src/migrator.py — targeting missing branches.

Missing lines (original analysis):
  31-122, 145-150, 190-191, 206-207, 228-234, 243-244, 255-262,
  292-294, 320, 325-329, 336-337, 341-343, 368-371, 414-415, 421,
  451-453, 457-512, 521-553, 613-614, 643, 694-697, 703-706, 717,
  783-785, 802
"""
import time
from unittest.mock import MagicMock, patch, call

import pytest

from src.migrator import Migrator
from src.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(schemas=("all",), pub="test_pub", sub="test_sub"):
    cfg = MagicMock(spec=Config)
    cfg.get_source_conn.return_value = (
        "host=localhost port=5432 user=src dbname=srcdb")
    cfg.get_dest_conn.return_value = (
        "host=localhost port=5433 user=dst dbname=dstdb")
    cfg.get_source_dict.return_value = {
        "host": "localhost", "port": "5432",
        "user": "src", "password": "pass",
        "database": "srcdb",
    }
    cfg.get_dest_dict.return_value = {
        "host": "localhost", "port": "5433",
        "user": "dst", "password": "pass",
        "database": "dstdb",
    }
    cfg.get_replication.return_value = {
        "publication_name": pub,
        "subscription_name": sub,
    }
    cfg.get_target_schemas.return_value = list(schemas)
    cfg.override_db = None
    return cfg


# ---------------------------------------------------------------------------
# step4a_migrate_schema_pre_data — drop_dest branches
# ---------------------------------------------------------------------------

class TestStep4aDropDest:
    def test_drop_dest_success(self):
        cfg = _make_config()
        m = Migrator(cfg)

        mock_admin_conn = MagicMock()
        mock_admin_conn.execute.return_value.fetchall.return_value = []

        def client_factory(conn_str, label=None):
            client = MagicMock()
            client.get_conn.return_value.__enter__ = MagicMock(return_value=mock_admin_conn)
            client.get_conn.return_value.__exit__ = MagicMock(return_value=False)
            return client

        with patch("src.db.PostgresClient", side_effect=client_factory), \
             patch("src.db.execute_shell_command", return_value=(True, "ok")):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=True)
        assert ok is True

    def test_drop_dest_pre_cleanup_exception(self):
        """When all DB connections fail, pre-cleanup is skipped but admin drop
        also fails — so the step returns False (expected: can't drop/recreate)."""
        cfg = _make_config()
        m = Migrator(cfg)

        def client_factory(conn_str, label=None):
            client = MagicMock()
            client.get_conn.side_effect = Exception("conn refused")
            return client

        with patch("src.db.PostgresClient", side_effect=client_factory), \
             patch("src.db.execute_shell_command", return_value=(True, "ok")):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=True)
        # Admin drop also fails → step returns False (correct behaviour)
        assert ok is False
        assert "drop/recreate" in msg.lower()

    def test_drop_dest_admin_drop_fails(self):
        """Admin DB connection fails → error returned."""
        cfg = _make_config()
        m = Migrator(cfg)

        call_count = [0]

        def client_factory(conn_str, label=None):
            client = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 2:
                # Pre-cleanup clients succeed
                conn = MagicMock()
                conn.execute.return_value.fetchall.return_value = []
                client.get_conn.return_value.__enter__ = MagicMock(return_value=conn)
                client.get_conn.return_value.__exit__ = MagicMock(return_value=False)
            else:
                # Admin client raises
                client.get_conn.side_effect = Exception("cannot connect")
            return client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=True)
        assert ok is False
        assert "drop/recreate" in msg.lower()

    def test_drop_dest_with_subscription_cleanup(self):
        """Exercises subscription cleanup loop (lines 43-51)."""
        cfg = _make_config()
        m = Migrator(cfg)

        conn = MagicMock()
        # Return a subscription to drop
        conn.execute.return_value.fetchall.return_value = [("sub1",)]

        def client_factory(conn_str, label=None):
            client = MagicMock()
            client.get_conn.return_value.__enter__ = MagicMock(return_value=conn)
            client.get_conn.return_value.__exit__ = MagicMock(return_value=False)
            return client

        with patch("src.db.PostgresClient", side_effect=client_factory), \
             patch("src.db.execute_shell_command", return_value=(True, "ok")):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=True)
        # Subscription cleanup ran, then continued to shell command
        assert ok is True

    def test_drop_dest_with_active_replication_slot(self):
        """Exercises slot cleanup with active PID (lines 59-64)."""
        cfg = _make_config()
        m = Migrator(cfg)

        call_num = [0]
        def execute_side_effect(sql, params=None):
            r = MagicMock()
            call_num[0] += 1
            if "pg_subscription" in sql:
                r.fetchall.return_value = []
            elif "pg_replication_slots" in sql and "database = current_database" in sql:
                r.fetchall.return_value = [("slot1", 12345)]  # active slot
            elif "pg_replication_slots" in sql and "slot_name = %s" in sql:
                r.fetchall.return_value = [("slot1", 12345)]
            else:
                r.fetchall.return_value = []
            return r

        conn = MagicMock()
        conn.execute.side_effect = execute_side_effect

        def client_factory(conn_str, label=None):
            client = MagicMock()
            client.get_conn.return_value.__enter__ = MagicMock(return_value=conn)
            client.get_conn.return_value.__exit__ = MagicMock(return_value=False)
            return client

        with patch("src.db.PostgresClient", side_effect=client_factory), \
             patch("src.db.execute_shell_command", return_value=(True, "ok")):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=True)
        assert ok is True

    def test_schema_filter_in_dump_cmd(self):
        """Exercises schema_args join when schemas != ['all']."""
        cfg = _make_config(schemas=["public", "sales"])
        m = Migrator(cfg)

        with patch("src.db.PostgresClient"), \
             patch("src.db.execute_shell_command", return_value=(True, "ok")):
            ok, msg, cmds, outs = m.step4a_migrate_schema_pre_data(drop_dest=False)
        assert ok is True
        assert any("public" in c or "sales" in c for c in cmds)


# ---------------------------------------------------------------------------
# step4b_migrate_schema_post_data — failure branch
# ---------------------------------------------------------------------------

class TestStep4bMigrateSchemaPostData:
    def test_failure(self):
        cfg = _make_config()
        m = Migrator(cfg)
        with patch("src.db.execute_shell_command", return_value=(False, "error")):
            ok, msg, cmds, outs = m.step4b_migrate_schema_post_data()
        assert ok is False
        assert "POST-DATA" in msg.upper()

    def test_with_schema_filter(self):
        cfg = _make_config(schemas=["myschema"])
        m = Migrator(cfg)
        with patch("src.db.execute_shell_command", return_value=(True, "")):
            ok, msg, cmds, outs = m.step4b_migrate_schema_post_data()
        assert ok is True


# ---------------------------------------------------------------------------
# step5_setup_source — error branches
# ---------------------------------------------------------------------------

class TestStep5SetupSourceExtended:
    def test_with_specific_schemas(self):
        """Exercises schema_filter and 'FOR TABLES IN SCHEMA' branch (lines 243-244)."""
        cfg = _make_config(schemas=["myschema"])
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.return_value = []

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step5_setup_source()
        assert ok is True
        assert any("myschema" in str(c) for c in cmds)

    def test_with_no_pk_tables(self):
        """Covers the REPLICA IDENTITY FULL loop (lines 227-235)."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.return_value = [
            {"schema_name": "public", "table_name": "no_pk_table"}]

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step5_setup_source()
        assert ok is True
        assert any("REPLICA IDENTITY" in str(c) for c in cmds)

    def test_execute_raises_partway(self):
        """Covers the except block that pads out_results (lines 255-262)."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.return_value = []
        # Make execute_script fail after first SQL
        client.execute_script.side_effect = [None, Exception("fail")]

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step5_setup_source()
        assert ok is False

    def test_init_failure_no_sqls(self):
        """Covers the 'no executed_sqls' branch in except (lines 259-261)."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.side_effect = Exception("timeout")

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step5_setup_source()
        assert ok is False
        assert "INITIALIZATION" in cmds


# ---------------------------------------------------------------------------
# step6_setup_destination — failure branch
# ---------------------------------------------------------------------------

class TestStep6SetupDestinationError:
    def test_subscription_creation_fails(self):
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_script.side_effect = Exception("SSL error")

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step6_setup_destination()
        assert ok is False
        assert "SSL error" in msg

    def test_custom_source_host_port_used(self):
        """Covers rep_config.get('source_host'/'source_port') branch."""
        cfg = _make_config()
        cfg.get_replication.return_value = {
            "publication_name": "pub",
            "subscription_name": "sub",
            "source_host": "db-internal",
            "source_port": "5555",
        }
        m = Migrator(cfg)
        client = MagicMock()

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step6_setup_destination()
        assert ok is True


# ---------------------------------------------------------------------------
# wait_for_sync
# ---------------------------------------------------------------------------

class TestWaitForSync:
    def test_timeout(self):
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        
        def _exec_query(q, *args, **kwargs):
            if "pg_subscription WHERE" in q:
                return [{"cnt": 1}]
            return [{"total": 1, "pending": 1}]
            
        client.execute_query.side_effect = _exec_query

        with patch("src.db.PostgresClient", return_value=client), \
             patch("time.sleep"):
            ok, msg, cmds, outs = m.wait_for_sync(timeout=0.1, poll_interval=1)
        assert ok is False
        assert "timed out" in msg

    def test_show_progress_on_sync(self):
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        
        def _exec_query(q, *args, **kwargs):
            if "pg_subscription WHERE" in q:
                return [{"cnt": 1}]
            return [{"total": 1, "pending": 0}]
            
        client.execute_query.side_effect = _exec_query

        with patch("src.db.PostgresClient", return_value=client), \
             patch("time.sleep"):
            ok, msg, cmds, outs = m.wait_for_sync(
                timeout=60, poll_interval=1, show_progress=True)
        assert ok is True

    def test_show_progress_while_waiting(self):
        """Exercises the progress print branch during wait (lines 324-332)."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        
        main_query_returns = [
            [{"total": 2, "pending": 2}],
            [{"total": 2, "pending": 0}],
        ]
        
        def _exec_query(q, *args, **kwargs):
            if "pg_subscription WHERE" in q:
                return [{"cnt": 1}]
            return main_query_returns.pop(0)

        client.execute_query.side_effect = _exec_query

        with patch("src.db.PostgresClient", return_value=client), \
             patch("time.sleep"), \
             patch.object(m, "get_initial_copy_progress", return_value={
                 "summary": {"percent_bytes": 50, "bytes_copied_pretty": "50MB", "total_source_pretty": "100MB"}}):
            ok, msg, cmds, outs = m.wait_for_sync(
                timeout=60, poll_interval=0, show_progress=True)
        assert ok is True

    def test_query_exception_is_warned(self):
        """Lines 336-337: exception in query is caught and warned."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()

        main_query_returns = [
            Exception("query failed"),
            [{"total": 1, "pending": 0}],
        ]

        def _exec_query(q, *args, **kwargs):
            if "pg_subscription WHERE" in q:
                return [{"cnt": 1}]
            val = main_query_returns.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

        client.execute_query.side_effect = _exec_query

        with patch("src.db.PostgresClient", return_value=client), \
             patch("time.sleep"):
            ok, msg, cmds, outs = m.wait_for_sync(timeout=60, poll_interval=0)
        assert ok is True

    def test_result_none_does_not_crash(self):
        """result is None → loop continues."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        
        main_query_returns = [
            None,            # None result
            [{"total": 1, "pending": 0}],  # sync complete
        ]

        def _exec_query(q, *args, **kwargs):
            if "pg_subscription WHERE" in q:
                return [{"cnt": 1}]
            return main_query_returns.pop(0)

        client.execute_query.side_effect = _exec_query

        with patch("src.db.PostgresClient", return_value=client), \
             patch("time.sleep"):
            ok, msg, cmds, outs = m.wait_for_sync(timeout=60, poll_interval=0)
        assert ok is True


# ---------------------------------------------------------------------------
# get_initial_copy_progress — error branches
# ---------------------------------------------------------------------------

class TestGetInitialCopyProgressErrors:
    def test_source_query_fails(self):
        cfg = _make_config()
        m = Migrator(cfg)

        source_client = MagicMock()
        source_client.execute_query.side_effect = Exception("pub tables failed")
        dest_client = MagicMock()

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            result = m.get_initial_copy_progress()
        assert result is None

    def test_dest_query_fails(self):
        cfg = _make_config()
        m = Migrator(cfg)

        source_client = MagicMock()
        source_client.execute_query.return_value = []
        dest_client = MagicMock()
        dest_client.execute_query.side_effect = Exception("sub rel failed")

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            result = m.get_initial_copy_progress()
        assert result is None

    def test_state_d_with_active_copy(self):
        """Exercises state='d' with active copy progress (lines 416-419)."""
        cfg = _make_config(pub="mypub")
        m = Migrator(cfg)

        source_client = MagicMock()
        source_client.execute_query.return_value = [
            {"schemaname": "public", "tablename": "t1", "total_bytes": 1000}]

        dest_client = MagicMock()
        dest_client.execute_query.side_effect = [
            [{"table_name": "public.t1", "state": "d"}],     # rel_status
            [{"table_name": "public.t1",                       # progress_status
              "bytes_processed": 500, "bytes_total": 1000}],
        ]

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            result = m.get_initial_copy_progress()
        assert result is not None
        assert result["tables"][0]["bytes_copied"] == 500

    def test_state_d_without_active_copy(self):
        """Exercises state='d' without active copy (bytes_copied=0)."""
        cfg = _make_config(pub="mypub")
        m = Migrator(cfg)

        source_client = MagicMock()
        source_client.execute_query.return_value = [
            {"schemaname": "public", "tablename": "t1", "total_bytes": 1000}]

        dest_client = MagicMock()
        dest_client.execute_query.side_effect = [
            [{"table_name": "public.t1", "state": "d"}],
            [],  # no progress rows
        ]

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            result = m.get_initial_copy_progress()
        assert result["tables"][0]["bytes_copied"] == 0

    def test_zero_size_source_state_s_gives_100pct(self):
        """state='s' with zero src_size gives 100% (lines 431)."""
        cfg = _make_config(pub="mypub")
        m = Migrator(cfg)

        source_client = MagicMock()
        source_client.execute_query.return_value = [
            {"schemaname": "public", "tablename": "t1", "total_bytes": 0}]

        dest_client = MagicMock()
        dest_client.execute_query.side_effect = [
            [{"table_name": "public.t1", "state": "s"}],
            [],
        ]

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            result = m.get_initial_copy_progress()
        assert result["tables"][0]["percent"] == 100.0


# ---------------------------------------------------------------------------
# get_replication_status
# ---------------------------------------------------------------------------

class TestGetReplicationStatus:
    def test_returns_structure(self):
        cfg = _make_config()
        m = Migrator(cfg)

        client = MagicMock()
        client.execute_query.return_value = []

        with patch("src.db.PostgresClient", return_value=client):
            result = m.get_replication_status()

        assert "publisher" in result
        assert "subscriber" in result
        assert "slots" in result
        assert "publications" in result

    def test_query_exceptions_are_silenced(self):
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.side_effect = Exception("down")

        with patch("src.db.PostgresClient", return_value=client):
            result = m.get_replication_status()
        # All lists should be empty (exceptions silenced)
        assert result["publisher"] == []
        assert result["subscriber"] == []


# ---------------------------------------------------------------------------
# step10_terminate_replication — failure
# ---------------------------------------------------------------------------

class TestStep10TerminateReplication:
    def test_cleanup_fails(self):
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_script.side_effect = Exception("locked")

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.step10_terminate_replication()
        assert ok is False
        assert "locked" in msg


# ---------------------------------------------------------------------------
# setup_reverse_replication — error/edge branches
# ---------------------------------------------------------------------------

class TestSetupReverseReplicationExtended:
    def test_error_padded_out_results(self):
        """Lines 642-647: exception pads out_results and uses INITIALIZATION."""
        cfg = _make_config()
        m = Migrator(cfg)
        client = MagicMock()
        client.execute_query.side_effect = Exception("boom")

        with patch("src.db.PostgresClient", return_value=client):
            ok, msg, cmds, outs = m.setup_reverse_replication()
        assert ok is False
        assert "INITIALIZATION" in cmds

    def test_custom_dest_host_for_src(self):
        """Covers dest_host_for_src/dest_port_for_src from rep_config."""
        cfg = _make_config()
        cfg.get_replication.return_value = {
            "publication_name": "pub",
            "subscription_name": "sub",
            "dest_host_for_src": "db-internal",
            "dest_port_for_src": "9999",
        }
        m = Migrator(cfg)

        dest_client = MagicMock()
        # count=0 → forward sub not present → proceed
        dest_client.execute_query.return_value = [{"count": 0}]

        with patch("src.db.PostgresClient", return_value=dest_client):
            ok, msg, cmds, outs = m.setup_reverse_replication()
        assert ok is True


# ---------------------------------------------------------------------------
# cleanup_reverse_replication — error branches
# ---------------------------------------------------------------------------

class TestCleanupReverseReplicationExtended:
    def test_init_exception_uses_initialization(self):
        """Lines 712-721: outer exception pads and uses INITIALIZATION."""
        cfg = _make_config()
        m = Migrator(cfg)

        with patch("src.db.PostgresClient", side_effect=Exception("fatal")):
            ok, msg, cmds, outs = m.cleanup_reverse_replication()
        assert ok is False
        assert "INITIALIZATION" in cmds

    def test_slot_drop_fails_gracefully(self):
        """Line 694-697: slot drop exception is warned, not re-raised."""
        cfg = _make_config()
        m = Migrator(cfg)

        source_client = MagicMock()
        dest_client = MagicMock()

        def script_side_effect(sql, autocommit=False):
            if "DROP SUBSCRIPTION" in sql:
                return None
            if "pg_drop_replication_slot" in sql:
                raise Exception("slot busy")
            return None

        dest_client.execute_script.side_effect = script_side_effect

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            ok, msg, cmds, outs = m.cleanup_reverse_replication()
        # Partial failure: slot drop failed
        assert any("slot busy" in str(o) for o in outs)

    def test_pub_drop_fails_gracefully(self):
        """Line 703-706: pub drop exception is warned, not re-raised."""
        cfg = _make_config()
        m = Migrator(cfg)

        source_client = MagicMock()
        dest_client = MagicMock()

        # source: call 1 = sub drop (OK)
        # dest: call 1 = slot drop (OK), call 2 = pub drop (fails)
        dest_call_num = [0]

        def dest_script_side_effect(sql, autocommit=False):
            dest_call_num[0] += 1
            if dest_call_num[0] == 1:  # slot drop → ok
                return None
            if dest_call_num[0] == 2:  # pub drop → fail
                raise Exception("pub locked")
            return None

        dest_client.execute_script.side_effect = dest_script_side_effect
        source_client.execute_script.return_value = None

        def client_factory(conn_str, label=None):
            if "srcdb" in conn_str:
                return source_client
            return dest_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            ok, msg, cmds, outs = m.cleanup_reverse_replication()
        assert any("pub locked" in str(o) for o in outs)


# ---------------------------------------------------------------------------
# sync_large_objects — additional branches
# ---------------------------------------------------------------------------

class TestSyncLargeObjectsExtended:
    def test_no_rows_for_table_continues(self):
        """Line 801-802: no rows for a LOB column → continue."""
        cfg = _make_config()
        m = Migrator(cfg)

        source_client = MagicMock()
        # lob_columns has one entry
        source_client.execute_query.side_effect = [
            [],
            [{"schema_name": "public", "table_name": "t1", "column_name": "data"}],
            [{"attname": "id"}],   # pk result
            [],                     # data_query → empty rows → continue
        ]

        def client_factory(conn_str, label=None):
            return source_client

        with patch("src.db.PostgresClient", side_effect=client_factory):
            ok, msg, cmds, outs = m.sync_large_objects()
        assert ok is True
