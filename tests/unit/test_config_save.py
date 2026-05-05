import os
import configparser
import pytest
from src.config import Config

def test_config_update_and_save(tmp_path):
    config_file = tmp_path / "test.ini"
    config_file.write_text("[source]\nhost=old")
    
    cfg = Config(str(config_file))
    cfg.update_section("source", {"host": "new", "port": "5432"})
    cfg.save()
    
    # Read back and verify
    new_cfg = configparser.ConfigParser()
    new_cfg.read(str(config_file))
    assert new_cfg["source"]["host"] == "new"
    assert new_cfg["source"]["port"] == "5432"
