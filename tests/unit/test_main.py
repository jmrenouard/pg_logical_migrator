"""Tests for src/main.py — targeting 100% coverage."""
from unittest.mock import MagicMock, patch

from src.main import main, setup_results_dir


class TestSetupResultsDir:
    def test_creates_dir_and_returns_path(self, tmp_path):
        with patch("src.main.os.makedirs") as mock_mkdirs, \
             patch("src.main.os.path.join", return_value=str(tmp_path / "RESULTS/ts")):
            result = setup_results_dir()
            mock_mkdirs.assert_called_once()
            assert result.endswith("ts") or "RESULTS" in result

    def test_return_type_is_string(self):
        with patch("src.main.os.makedirs"):
            result = setup_results_dir()
            assert isinstance(result, str)


class TestMain:
    def test_main_runs_app(self):
        mock_app = MagicMock()
        with patch("src.main.MigratorApp", return_value=mock_app) as MockApp, \
             patch("sys.argv", ["prog"]):
            main()
        MockApp.assert_called_once()
        mock_app.run.assert_called_once()

    def test_main_uses_default_config(self):
        mock_app = MagicMock()
        with patch("src.main.MigratorApp", return_value=mock_app) as MockApp, \
             patch("sys.argv", ["prog"]):
            main()
        # Default config is "config_migrator.ini"
        MockApp.assert_called_once_with("config_migrator.ini")

    def test_main_uses_custom_config(self):
        mock_app = MagicMock()
        with patch("src.main.MigratorApp", return_value=mock_app) as MockApp, \
             patch("sys.argv", ["prog", "--config", "custom.ini"]):
            main()
        MockApp.assert_called_once_with("custom.ini")
