import pytest
from src.config import Config


def test_config_load(tmp_path):
    config_file = tmp_path / "test.ini"
    config_content = """
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
    config_file.write_text(config_content)

    cfg = Config(str(config_file))
    assert cfg.get_source_conn() == "postgresql://user:pwd@localhost:5432/src_db"
    assert cfg.get_dest_conn() == "postgresql://admin:admin_pwd@remote:5433/dst_db"
    assert cfg.get_replication()['slot_name'] == "test_slot_src_db_public"


def test_get_target_schemas(tmp_path):
    config_file = tmp_path / "test_schemas.ini"

    # Case 1: Default (public)
    config_file.write_text(
        "[source]\ndatabase=d\n[destination]\n[replication]\n")
    cfg = Config(str(config_file))
    assert cfg.get_target_schemas() == ["public"]

    # Case 2: 'all'
    config_file.write_text(
        "[source]\ndatabase=d\n[destination]\n[replication]\ntarget_schema=all\n")
    cfg = Config(str(config_file))
    assert cfg.get_target_schemas() == ["all"]

    # Case 3: list
    config_file.write_text(
        "[source]\ndatabase=d\n[destination]\n[replication]\ntarget_schema=s1, s2,  s3\n")
    cfg = Config(str(config_file))
    assert cfg.get_target_schemas() == ["s1", "s2", "s3"]


def test_config_not_found():
    with pytest.raises(FileNotFoundError):
        Config("/path/to/nonexistent/file.ini")


def test_config_path(tmp_path):
    config_file = tmp_path / "test.ini"
    config_file.write_text(
        "[source]\ndatabase=d\n[destination]\n[replication]\n")
    path_str = str(config_file)
    cfg = Config(path_str)
    assert cfg.config_path == path_str
