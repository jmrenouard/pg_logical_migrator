import pytest
from src.db import PostgresClient
from src.checker import DBChecker
from src.migrator import Migrator
from src.post_sync import PostSync
from src.validation import Validator
from src.config import Config


@pytest.fixture
def config():
    cfg = Config("tests/test_config.ini")
    cfg.set_override_db("test_migration")
    return cfg


@pytest.fixture
def source_client(config):
    return PostgresClient(config.get_source_conn(), label="SOURCE")


@pytest.fixture
def dest_client(config):
    return PostgresClient(config.get_dest_conn(), label="DESTINATION")


@pytest.fixture
def db_checker(source_client, dest_client):
    return DBChecker(source_client, dest_client)


@pytest.fixture
def migrator(config):
    return Migrator(config)


@pytest.fixture
def db_validator(source_client, dest_client):
    return Validator(source_client, dest_client)


@pytest.fixture
def post_sync(source_client, dest_client):
    return PostSync(source_client, dest_client)
