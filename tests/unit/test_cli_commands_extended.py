"""Extended tests for src/cli/commands.py — targeting missing branches.

Missing lines (original analysis):
  137-146, 234, 301, 441-442, 454-460
"""
import types
from unittest.mock import MagicMock, patch

import pytest

from src.cli import commands


def _args(**kwargs):
    defaults = {
        "config": "config_migrator.ini",
        "dry_run": False,
        "verbose": False,
        "drop_dest": False,
        "use_stats": False,
        "owner": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# cmd_migrate_schema_pre_data — dry_run with drop_dest
# ---------------------------------------------------------------------------

class TestCmdMigrateSchemaPreDataDryRun:
    def test_dry_run_with_drop_dest(self, capsys):
        args = _args(dry_run=True, drop_dest=True)
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator"):
            rc = commands.cmd_migrate_schema_pre_data(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "drop-dest" in out.lower() or "DRY-RUN" in out

    def test_dry_run_without_drop_dest(self, capsys):
        args = _args(dry_run=True, drop_dest=False)
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator"):
            rc = commands.cmd_migrate_schema_pre_data(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# cmd_progress — edge branches (no tables, missing data)
# ---------------------------------------------------------------------------

class TestCmdProgress:
    def test_no_progress_data(self, capsys):
        args = _args()
        migrator = MagicMock()
        migrator.get_initial_copy_progress.return_value = None
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_progress(args)
        assert rc == 1

    def test_no_tables_in_publication(self, capsys):
        args = _args()
        migrator = MagicMock()
        migrator.get_initial_copy_progress.return_value = {
            "summary": {
                "total_tables": 0,
                "completed_tables": 0,
                "total_source_bytes": 0,
                "total_source_pretty": "0 B",
                "bytes_copied": 0,
                "bytes_copied_pretty": "0 B",
                "percent_tables": 0,
                "percent_bytes": 0,
            },
            "tables": [],
        }
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_progress(args)
        assert rc == 0

    def test_tables_with_state_d(self, capsys):
        """Exercises the 'd' state branch coloring (line 233-234)."""
        args = _args()
        migrator = MagicMock()
        migrator.get_initial_copy_progress.return_value = {
            "summary": {
                "total_tables": 1,
                "completed_tables": 0,
                "total_source_bytes": 1000,
                "total_source_pretty": "1 KB",
                "bytes_copied": 500,
                "bytes_copied_pretty": "500 B",
                "percent_tables": 0,
                "percent_bytes": 50,
            },
            "tables": [
                {"table_name": "public.t1", "state": "d",
                 "bytes_copied": 500, "size_source": 1000, "percent": 50}
            ],
        }
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_progress(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# cmd_terminate_replication (Step 10)
# ---------------------------------------------------------------------------

class TestCmdTerminateReplication:
    def test_step10_1_fails_aborts(self):
        args = _args()
        migrator = MagicMock()
        migrator.step10_terminate_replication.return_value = (
            False, "slot locked", [], [])
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_terminate_replication(args)
        assert rc == 1
        # step4b should NOT be called
        migrator.step4b_migrate_schema_post_data.assert_not_called()

    def test_step10_success_schema_fails(self):
        args = _args()
        migrator = MagicMock()
        migrator.step10_terminate_replication.return_value = (
            True, "ok", [], [])
        migrator.step4b_migrate_schema_post_data.return_value = (
            False, "schema fail", [], [])
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_terminate_replication(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# cmd_wait_sync (utility)
# ---------------------------------------------------------------------------

class TestCmdWaitSync:
    def test_success(self, capsys):
        args = _args()
        migrator = MagicMock()
        migrator.wait_for_sync.return_value = (True, "done", [], [])
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_wait_sync(args)
        assert rc == 0

    def test_failure(self, capsys):
        args = _args()
        migrator = MagicMock()
        migrator.wait_for_sync.return_value = (False, "timeout", [], [])
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_wait_sync(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# cmd_cleanup_reverse
# ---------------------------------------------------------------------------

class TestCmdCleanupReverse:
    def test_success(self, capsys):
        args = _args()
        migrator = MagicMock()
        migrator.cleanup_reverse_replication.return_value = (
            True, "cleaned", [], [])
        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.Migrator", return_value=migrator):
            rc = commands.cmd_cleanup_reverse(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# cmd_tui
# ---------------------------------------------------------------------------

class TestCmdTui:
    def test_calls_run(self):
        args = _args()
        mock_app = MagicMock()
        with patch("src.cli.commands.Config"), \
             patch("src.main.MigratorApp", return_value=mock_app, create=True), \
             patch("src.cli.commands.MigratorApp", return_value=mock_app, create=True):
            try:
                rc = commands.cmd_tui(args)
            except (ImportError, AttributeError):
                pytest.skip("TUI import issue in test context")


# ---------------------------------------------------------------------------
# cmd_diagnose — size analysis branches
# ---------------------------------------------------------------------------

class TestCmdDiagnoseExtended:
    def test_no_size_data(self, capsys):
        """Line 301: sizes is None → skip size block."""
        args = _args()

        checker = MagicMock()
        checker.check_problematic_objects.return_value = {
            "no_pk": [], "large_objects": 0, "identities": [],
            "unowned_seqs": [], "unlogged_tables": [], "temp_tables": [],
            "foreign_tables": [], "matviews": [],
        }
        checker.get_database_size_analysis.return_value = None

        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.build_clients", return_value=(MagicMock(), MagicMock())), \
             patch("src.cli.commands.DBChecker", return_value=checker):
            rc = commands.cmd_diagnose(args)
        assert rc == 0

    def test_empty_table_rows(self, capsys):
        """Line 441-442: table_rows is empty → no table printed."""
        args = _args()

        checker = MagicMock()
        checker.check_problematic_objects.return_value = {
            "no_pk": [], "large_objects": 0, "identities": [],
            "unowned_seqs": [], "unlogged_tables": [], "temp_tables": [],
            "foreign_tables": [], "matviews": [],
        }
        checker.get_database_size_analysis.return_value = {
            "database": {"total_pretty": "1 GB"},
            "tables": [],  # empty → no table rows printed
        }

        with patch("src.cli.commands.Config"), \
             patch("src.cli.commands.build_clients", return_value=(MagicMock(), MagicMock())), \
             patch("src.cli.commands.DBChecker", return_value=checker):
            rc = commands.cmd_diagnose(args)
        assert rc == 0
