![pg_logical_migrator](../pg_logical_migrator.jpg)

# Project Tasks

## Block 1: Foundation & Test Environment

- [x] Initialize Python environment and `requirements.txt`.
- [x] Create `test_env/` with Docker Compose for PG 16 & 17.
- [x] Implement `test_env/setup_pagila.sh` for dataset loading.
- [x] Design and create `config_migrator.sample.ini`.
- [x] Implement `src/config.py` for config loading.
- [x] Setup `src/main.py` with Argument Parser (CLI vs TUI, `--auto`).
- [x] Implement TUI shell using `textual` or `rich`.

## Block 2: 14-Step Migration Workflow Implementation

- [x] **Step 1**: Implement `check_connectivity()` in `src/db_checks.py`.
- [x] **Step 2**: Implement `check_problematic_objects()` (No PKs, Large Objects, Unowned Seqs).
- [x] **Step 3**: Implement `check_pg_parameters()` (`wal_level`, etc.).
- [x] **Step 4**: Implement `migrate_schema()` using `pg_dump -s`.
- [x] **Step 5**: Implement `setup_source_replication()` (Publication/Slot).
- [x] **Step 6**: Implement `setup_dest_replication()` (Subscription).
- [x] **Step 7**: Implement `monitor_replication()` (Watch mode in TUI).
- [x] **Step 8**: Implement `refresh_materialized_views()`.
- [x] **Step 9**: Implement `sync_sequences_fetch()` (Fetch source values).
- [x] **Step 10**: Implement `sync_sequences_apply()` (Update target values).
- [x] **Step 11**: Implement `activate_triggers()`.
- [x] **Step 12**: Implement `terminate_replication()` (Cleanup).
- [x] **Step 13**: Implement `audit_objects()` (Count/List all objects).
- [x] **Step 14**: Implement `validate_data()` (Row count comparison).

## Block 3: UI & Automation

- [x] Implement TUI "Result Zone" for summary reports.
- [x] Implement TUI "Command Output Zone" for real-time logs.
- [x] Implement `--auto` mode logic to chain all 14 steps.
- [x] Ensure all operations log to `pg_migrator.log`.

## Block 4: Reporting & Observability

- [x] **Reporting Engine**: Implement HTML report generator with:
  - [x] Migration execution audit trails (all 14 steps).
  - [x] Execution Logs (commands and outputs) for auditability.
  - [x] Premium styling (Outfit font, color-coded blocks).

## Block 5: Testing & Quality Assurance

- [x] **Unit Testing**: Implement `tests/unit/` for all core modules.
- [x] **E2E Testing**: Implement `tests/e2e/test_full_migration.py`.
- [x] **Results Management**: Implement timestamped results in `RESULTS/`.
- [x] **Makefile**: Implement `Makefile` for project orchestration.

## Block 6: Documentation & Polishing

- [x] Add robust error handling and rollbacks for critical steps.
- [x] Finalize README and user guides.
- [x] Verification of full migration report with command details.
