import pytest
from unittest.mock import MagicMock, patch

from src.cli.commands import cmd_sync_lobs
from src.config import Config

def test_cmd_sync_lobs_success():
    """Test the CLI wrapper for synchronizing large objects (success case)."""
    args = MagicMock()
    args.config = "dummy.ini"
    args.dry_run = False

    with patch("src.cli.commands.Config") as mock_config_cls, \
         patch("src.cli.commands.Migrator") as mock_migrator_cls, \
         patch("src.cli.commands.print_status") as mock_print_status, \
         patch("src.cli.commands.print_verbose_execution") as mock_print_verbose:
         
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.sync_large_objects.return_value = (True, "Success", ["cmd1"], ["out1"])
        mock_migrator_cls.return_value = mock_migrator_instance

        # Invoke the command
        exit_code = cmd_sync_lobs(args)

        # Assertions
        assert exit_code == 0
        mock_migrator_instance.sync_large_objects.assert_called_once()
        mock_print_status.assert_called_once_with(True, "Success")
        mock_print_verbose.assert_called_once_with(args, ["cmd1"], ["out1"])


def test_cmd_sync_lobs_failure():
    """Test the CLI wrapper for synchronizing large objects (failure case)."""
    args = MagicMock()
    args.config = "dummy.ini"
    args.dry_run = False

    with patch("src.cli.commands.Config") as mock_config_cls, \
         patch("src.cli.commands.Migrator") as mock_migrator_cls, \
         patch("src.cli.commands.print_status") as mock_print_status, \
         patch("src.cli.commands.print_verbose_execution") as mock_print_verbose:
         
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.sync_large_objects.return_value = (False, "Failure", ["cmd1"], ["err1"])
        mock_migrator_cls.return_value = mock_migrator_instance

        # Invoke the command
        exit_code = cmd_sync_lobs(args)

        # Assertions
        assert exit_code == 1
        mock_migrator_instance.sync_large_objects.assert_called_once()
        mock_print_status.assert_called_once_with(False, "Failure")
        mock_print_verbose.assert_called_once_with(args, ["cmd1"], ["err1"])


def test_cmd_sync_lobs_dry_run():
    """Test the CLI wrapper for synchronizing large objects (dry run)."""
    args = MagicMock()
    args.config = "dummy.ini"
    args.dry_run = True

    with patch("src.cli.commands.Config") as mock_config_cls, \
         patch("src.cli.commands.Migrator") as mock_migrator_cls:
         
        mock_migrator_instance = MagicMock()
        mock_migrator_cls.return_value = mock_migrator_instance

        # Invoke the command
        exit_code = cmd_sync_lobs(args)

        # Assertions
        assert exit_code == 0
        mock_migrator_instance.sync_large_objects.assert_not_called()
