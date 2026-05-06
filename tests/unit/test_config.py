"""
test_config.py — Unit tests for Config (configuration parsing).

Each test validates a single aspect of configuration loading. The original
test_config_load and test_get_target_schemas have been split into atomic tests
to isolate failures and clarify the purpose of each assertion.
"""

import pytest
from src.config import Config


# ---------------------------------------------------------------------------
# Helper to write and load an INI config
# ---------------------------------------------------------------------------

def _write_config(tmp_path, content: str) -> Config:
    """Write config content to a temp file and return a Config object."""
    config_file = tmp_path / "test.ini"
    config_file.write_text(content)
    return Config(str(config_file))


# ---------------------------------------------------------------------------
# Basic config loading (split from test_config_load)
# ---------------------------------------------------------------------------

_FULL_CONFIG = """
[source]
host = localhost
port = 5432
user = user
password = pwd
database = src_db

[destination]
host = remote
port = 5433
user = admin
password = admin_pwd
database = dst_db

[replication]
slot_name = test_slot
publication_name = test_pub
"""


class TestConfigLoadSource:
    """Verify that source connection details are correctly parsed."""

    def test_source_conn_string(self, tmp_path):
        """Source conn string should be a valid postgresql:// URI."""
        cfg = _write_config(tmp_path, _FULL_CONFIG)
        assert cfg.get_source_conn() == "postgresql://user:pwd@localhost:5432/src_db"


class TestConfigLoadDestination:
    """Verify that destination connection details are correctly parsed."""

    def test_dest_conn_string(self, tmp_path):
        """Destination conn string should reflect the [destination] section."""
        cfg = _write_config(tmp_path, _FULL_CONFIG)
        assert cfg.get_dest_conn() == "postgresql://admin:admin_pwd@remote:5433/dst_db"


class TestConfigLoadReplication:
    """Verify that replication parameters are correctly parsed and suffixed."""

    def test_slot_name_has_db_suffix(self, tmp_path):
        """Slot name should be suffixed with database name and default schema."""
        cfg = _write_config(tmp_path, _FULL_CONFIG)
        assert cfg.get_replication()['slot_name'] == "test_slot_src_db_public"


# ---------------------------------------------------------------------------
# Target schemas (split from test_get_target_schemas)
# ---------------------------------------------------------------------------

class TestGetTargetSchemas:
    """Verify get_target_schemas for default, 'all', and explicit list cases."""

    def test_default_returns_public(self, tmp_path):
        """When no target_schema is set, default to ['public']."""
        cfg = _write_config(
            tmp_path,
            "[source]\ndatabase=d\n[destination]\n[replication]\n")
        assert cfg.get_target_schemas() == ["public"]

    def test_all_schema(self, tmp_path):
        """When target_schema=all, return ['all']."""
        cfg = _write_config(
            tmp_path,
            "[source]\ndatabase=d\n[destination]\n[replication]\ntarget_schema=all\n")
        assert cfg.get_target_schemas() == ["all"]

    def test_explicit_list(self, tmp_path):
        """When target_schema=s1, s2, s3, return a trimmed list."""
        cfg = _write_config(
            tmp_path,
            "[source]\ndatabase=d\n[destination]\n[replication]\ntarget_schema=s1, s2,  s3\n")
        assert cfg.get_target_schemas() == ["s1", "s2", "s3"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestConfigErrors:
    """Verify Config behaviour with invalid inputs."""

    def test_config_not_found(self):
        """A nonexistent config file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            Config("/path/to/nonexistent/file.ini")


# ---------------------------------------------------------------------------
# Config path attribute
# ---------------------------------------------------------------------------

class TestConfigPath:
    """Verify that the config_path attribute stores the original file path."""

    def test_config_path_stored(self, tmp_path):
        """config_path should match the file path passed to Config()."""
        cfg = _write_config(
            tmp_path,
            "[source]\ndatabase=d\n[destination]\n[replication]\n")
        assert cfg.config_path == str(tmp_path / "test.ini")
