"""Tests for src/cli/helpers.py — targeting 100% coverage."""
import datetime
import logging
import os
import types
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.cli.helpers import (
    build_clients,
    generate_sample_config,
    print_status,
    print_table,
    print_verbose_execution,
    setup_logging,
    setup_results_dir,
)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_console_only(self):
        setup_logging(level="DEBUG")
        assert logging.root.level == logging.DEBUG

    def test_with_log_file(self, tmp_path):
        log_file = str(tmp_path / "sub" / "test.log")
        setup_logging(level="WARNING", log_file=log_file)
        assert os.path.exists(os.path.dirname(log_file))
        assert any(isinstance(h, logging.FileHandler) for h in logging.root.handlers)

    def test_default_level_info(self):
        setup_logging()
        assert logging.root.level == logging.INFO

    def test_invalid_level_defaults_to_info(self):
        setup_logging(level="NOTAREAL")
        # getattr returns logging.INFO (20) for unknown levels
        assert logging.root.level == logging.INFO


# ---------------------------------------------------------------------------
# setup_results_dir
# ---------------------------------------------------------------------------

class TestSetupResultsDir:
    def test_with_base(self, tmp_path):
        base = str(tmp_path / "myresults")
        result = setup_results_dir(base=base)
        assert result == base
        assert os.path.isdir(base)

    def test_without_base_creates_timestamped(self, tmp_path):
        with patch("src.cli.helpers.os.makedirs") as mock_mkdirs, \
             patch("src.cli.helpers.os.path.join", return_value=str(tmp_path / "RESULTS/ts")):
            result = setup_results_dir()
            mock_mkdirs.assert_called_once()

    def test_timestamp_format(self):
        with patch("src.cli.helpers.os.makedirs"):
            result = setup_results_dir()
            # Should contain "RESULTS/" in path
            assert "RESULTS" in result


# ---------------------------------------------------------------------------
# build_clients
# ---------------------------------------------------------------------------

class TestBuildClients:
    def test_returns_two_clients(self):
        cfg = MagicMock()
        cfg.get_source_conn.return_value = "host=localhost dbname=src"
        cfg.get_dest_conn.return_value = "host=localhost dbname=dst"
        with patch("src.cli.helpers.PostgresClient") as MockClient:
            MockClient.side_effect = lambda conn, label=None: MagicMock(name=label)
            sc, dc = build_clients(cfg)
        assert sc is not None
        assert dc is not None


# ---------------------------------------------------------------------------
# print_status
# ---------------------------------------------------------------------------

class TestPrintStatus:
    def test_success(self, capsys):
        print_status(True, "All good")
        out = capsys.readouterr().out
        assert "OK" in out
        assert "All good" in out

    def test_failure(self, capsys):
        print_status(False, "Something broke")
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "Something broke" in out


# ---------------------------------------------------------------------------
# print_table
# ---------------------------------------------------------------------------

class TestPrintTable:
    def test_basic_table(self, capsys):
        print_table(["Name", "Value"], [["foo", "bar"], ["baz", "qux"]])
        out = capsys.readouterr().out
        assert "Name" in out
        assert "foo" in out
        assert "baz" in out

    def test_empty_rows(self, capsys):
        print_table(["A", "B"], [])
        out = capsys.readouterr().out
        assert "A" in out

    def test_wide_cell_adjusts_col_width(self, capsys):
        print_table(["Col"], [["short"], ["a_much_longer_string"]])
        out = capsys.readouterr().out
        assert "a_much_longer_string" in out


# ---------------------------------------------------------------------------
# print_verbose_execution
# ---------------------------------------------------------------------------

class TestPrintVerboseExecution:
    def _args(self, verbose=True):
        args = types.SimpleNamespace(verbose=verbose)
        return args

    def test_no_verbose_does_nothing(self, capsys):
        print_verbose_execution(self._args(verbose=False), ["CMD1"])
        assert capsys.readouterr().out == ""

    def test_empty_cmds_does_nothing(self, capsys):
        print_verbose_execution(self._args(verbose=True), [])
        assert capsys.readouterr().out == ""

    def test_cmd_without_output(self, capsys):
        print_verbose_execution(self._args(), ["SELECT 1;"])
        out = capsys.readouterr().out
        assert "SELECT 1;" in out

    def test_cmd_with_short_output(self, capsys):
        print_verbose_execution(self._args(), ["SELECT 1;"], ["row1"])
        out = capsys.readouterr().out
        assert "row1" in out

    def test_cmd_with_long_output_truncated(self, capsys):
        long_out = "\n".join([f"line{i}" for i in range(20)])
        print_verbose_execution(self._args(), ["CMD"], [long_out])
        out = capsys.readouterr().out
        assert "lines hidden" in out

    def test_no_verbose_attr(self, capsys):
        """args without 'verbose' attribute should not print."""
        args = object()  # has no verbose attr
        print_verbose_execution(args, ["CMD"])
        assert capsys.readouterr().out == ""

    def test_none_outs_defaults_to_empty(self, capsys):
        print_verbose_execution(self._args(), ["CMD1"], None)
        out = capsys.readouterr().out
        assert "CMD1" in out


# ---------------------------------------------------------------------------
# generate_sample_config
# ---------------------------------------------------------------------------

class TestGenerateSampleConfig:
    def test_creates_file(self, tmp_path):
        path = str(tmp_path / "sample.ini")
        generate_sample_config(path)
        assert os.path.exists(path)

    def test_file_contents(self, tmp_path):
        path = str(tmp_path / "sample.ini")
        generate_sample_config(path)
        content = open(path).read()
        assert "[source]" in content
        assert "[destination]" in content
        assert "[replication]" in content

    def test_prints_confirmation(self, tmp_path, capsys):
        path = str(tmp_path / "out.ini")
        generate_sample_config(path)
        out = capsys.readouterr().out
        assert "Sample configuration written" in out
