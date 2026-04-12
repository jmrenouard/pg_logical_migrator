![pg_logical_migrator](../pg_logical_migrator.jpg)

# Migration Workflow — 14 Steps

The `pg_logical_migrator` operates through a predefined 14-step sequence to ensure data integrity and minimal downtime. Each step maps to a specific function in the Python source code.

---

## Phase 1 — Pre-Flight Checks

### Step 1: Connectivity Check

- **Module**: `src/checker.py` → `DBChecker.check_connectivity()`
- **Purpose**: Verify network connectivity and authentication for both source and destination servers.
- **Action**: Attempt a connection using parameters from `config_migrator.ini`.
- **Outcome**: OK if both connections succeed; FAIL if either one fails.

### Step 2: Problematic Objects Analysis

- **Module**: `src/checker.py` → `DBChecker.check_problematic_objects()`
- **Purpose**: Identify potential migration blockers before starting replication.
- **Checks on Source**:
  - Tables without a Primary Key (`pg_class` + `pg_index`)
  - Count of Large Objects (`pg_largeobject_metadata`)
  - Tables with Identity Columns (`information_schema.columns`)
  - Sequences without an owning table (`pg_depend`)
  - Unlogged, Temporary, and Foreign tables
  - Materialized views
- **Outcome**: A diagnostic summary in the Result Zone.

### Step 3: Parameter Verification

- **Module**: `src/checker.py` → `DBChecker.check_replication_params()`
- **Purpose**: Ensure the source PostgreSQL server is configured for logical replication.
- **Checks**: `wal_level`, `max_replication_slots`, `max_wal_senders`, `max_worker_processes`, `server_version`.
- **Details**: See [Configuration Guide](CONFIGURATION.md).

---

## Phase 2 — Replication Setup

### Step 4a: Schema Pre-Data Migration

- **Module**: `src/migrator.py` → `Migrator.step4a_migrate_schema_pre_data()`
- **Purpose**: Replicate the pre-data schema structure (tables, schemas) to the destination.
- **Action**: Runs `pg_dump -s --section=pre-data --no-acl --no-owner` on the source and pipes the output to `psql` on the destination.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 5: Source Replication Setup

- **Module**: `src/migrator.py` → `Migrator.step5_setup_source()`
- **Purpose**: Prepare the source instance for data streaming.
- **Action**: Creates the logical Publication (for `ALL TABLES`) and the Replication Slot on the source.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 6: Destination Replication Setup

- **Module**: `src/migrator.py` → `Migrator.step6_setup_destination()`
- **Purpose**: Start data ingestion from the source.
- **Action**: Creates the logical Subscription on the destination server, linking it to the source publication.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 7: Replication Monitoring (Watch)

- **Module**: `src/migrator.py` → `Migrator.get_replication_status()`
- **Purpose**: Track the progress of initial data synchronization and ongoing replication.
- **Action**: Queries `pg_stat_subscription`, `pg_subscription_rel` on the destination, and `pg_stat_replication`, `pg_replication_slots`, `pg_publication_tables` on the source to display the current synchronization state of tables.
- **TUI/CLI**: Real-time monitoring in the TUI Result Zone or via the `repl-status` CLI command.

---

## Phase 3 — Post-Synchronization

> These steps are executed as part of the `post-migration` pipeline command after the initial data transfer is complete. They ensure consistency of non-replicated objects (sequences, materialized views, triggers).

### Step 4b: Schema Post-Data Migration

- **Module**: `src/migrator.py` → `Migrator.step4b_migrate_schema_post_data()`
- **Purpose**: Apply post-data schema objects (indexes, constraints) after data copy is complete.
- **Action**: Runs `pg_dump -s --section=post-data --no-acl --no-owner` on the source and pipes the output to `psql` on the destination.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 8: Materialized Views Refresh

- **Module**: `src/post_sync.py` → `PostSync.refresh_materialized_views()`
- **Purpose**: Synchronize non-table objects that are not replicated by logical subscription.
- **Action**: Queries all materialized views on the destination and executes `REFRESH MATERIALIZED VIEW CONCURRENTLY` for each.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 9: Sequence Synchronization (Fetch)

- **Module**: `src/post_sync.py` → `PostSync.sync_sequences()` (fetch phase)
- **Purpose**: Capture the current sequence values from the source to prevent ID collisions on the destination.
- **Action**: Fetches `last_value` for all sequences using `pg_sequences` on the source.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 10: Sequence Activation (Apply)

- **Module**: `src/post_sync.py` → `PostSync.sync_sequences()` (apply phase)
- **Purpose**: Update sequences on the destination to match the source's current state.
- **Action**: Executes `SELECT setval(...)` for each sequence using the values fetched in Step 9.
- **Returns**: `(success, message, commands_run, outputs)`

### Step 11: Trigger Activation

- **Module**: `src/post_sync.py` → `PostSync.enable_triggers()`
- **Purpose**: Re-enable business logic triggers that may have been disabled during the initial sync.
- **Action**: Executes `ALTER TABLE ... ENABLE TRIGGER ALL` for each user table on the destination.
- **Returns**: `(success, message, commands_run, outputs)`

---

## Phase 4 — Validation & Cutover

### Step 13: Object Audit

- **Module**: `src/validation.py` → `Validator.audit_objects()`
- **Purpose**: Verify 100% schema parity between source and destination.
- **Action**: Counts all objects (TABLE, VIEW, INDEX, SEQUENCE, FUNCTION) on both servers using `pg_class` and compares the totals.
- **Returns**: `(success, message, commands_run, outputs, report_list)`

### Step 14: Data Validation (Row Parity)

- **Module**: `src/validation.py` → `Validator.compare_row_counts()`
- **Purpose**: Confirm data consistency after synchronization.
- **Action**: Executes `SELECT count(*)` for every user table on both servers and compares the results. Reports OK or DIFF per table.
- **Returns**: `(success, message, commands_run, outputs, report_list)`

---

## Phase 5 — Cleanup

### Step 12: Replication Termination

- **Module**: `src/migrator.py` → `Migrator.step12_terminate_replication()`
- **Purpose**: Finalise the migration and free all replication resources.
- **Action**: Drops the Subscription on the destination, then drops the Publication and the Replication Slot on the source.
- **Returns**: `(success, message, commands_run, outputs)`

> **Note**: Step 12 is displayed last in the TUI sidebar because it is a destructive, one-way action. It should only be triggered after Steps 13 and 14 confirm full data parity.

---

## Incremental Pipeline Execution Order

The two-phase pipeline provides better safety and control than a single-shot automation.

### A. Initialization (`init-replication`)

Leaves replication active for continuous syncing.

```text
1 (Connectivity) → 2 (Diagnose) → 3 (Params) → 4a (Schema Pre-Data) → 5 (Pub) → 6 (Sub) → 7 (Polling Wait) → 13 (Audit) → 14 (Row Parity)
```

### B. Post Migration (`post-migration`)

Performs cleanup and finalizes destination objects.

```text
1 (Connectivity) → 12 (Stop Replication) → 4b (Schema Post-Data) → 8 (Refresh MatViews) → 9/10 (Sync Sequences) → 11 (Enable Triggers) → 13 (Audit) → 14 (Row Parity)
```

See [TOOLS.md](TOOLS.md) for full pipeline documentation.

---

[Return to Documentation Index](README.md)
