"""
migrator.py — Core logical replication orchestrator.

The Migrator class acts as the central coordinator for executing a PostgreSQL
logical migration. It relies on the configured source/destination environments
to progressively setup, monitor, and finalize replication.

Its logic is decomposed into specific thematic mixins located in `src.migrator_components`.
"""

import logging

from src.migrator_components.schema import SchemaMigrationMixin
from src.migrator_components.replication import CoreReplicationMixin
from src.migrator_components.monitoring import MonitoringMixin
from src.migrator_components.data_sync import DataSyncMixin

# Exported for backward compatibility with existing tests that patch these symbols
from src.db import PostgresClient, execute_shell_command, resolve_target_schemas, pgpass_context


class Migrator(SchemaMigrationMixin, CoreReplicationMixin, MonitoringMixin, DataSyncMixin):
    """
    Core orchestrator class that coordinates a multi-step PostgreSQL logical
    replication pipeline.

    Inherits distinct migration behaviors from multiple mixins:
    - SchemaMigrationMixin: Handles pg_dump/psql schema copy operations.
    - CoreReplicationMixin: Manages PUB/SUB creation, replication slots, and teardown.
    - MonitoringMixin: Provides progress tracking and wait loops.
    - DataSyncMixin: Handles specific unlogged and LOB synchronization tasks.
    """

    def __init__(self, config):
        """
        Initialize the migrator with configuration.

        Args:
            config (Config): Configuration object providing connection dictionaries
                             and replication settings.
        """
        self.config = config
        self.source_conn = config.get_source_dict()
        self.dest_conn = config.get_dest_dict()
        self.replication_cfg = config.get_replication()
