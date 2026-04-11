![pg_logical_migrator](../pg_logical_migrator.jpg)

# Codebase Architecture & Reference

This document provides a comprehensive overview of the `pg_logical_migrator` codebase. It details the project's architecture, core modules, classes, and their responsibilities to help developers navigate and extend the tool.

---

## High-Level Architecture

The project is structured as a modular Python application that provides both a Command Line Interface (CLI) and a Terminal User Interface (TUI). It is built around a set of single-responsibility classes that manage the different phases of logical replication (diagnostics, setup, post-sync, and validation).

### Directory Structure

```text
pg_logical_migrator/
├── pg_migrator.py           # Main CLI entry point
├── src/                     # Core Python modules
│   ├── config.py            # Configuration management
│   ├── db.py                # Database interaction wrapper
│   ├── checker.py           # Pre-flight diagnostics and parameter checks
│   ├── migrator.py          # Core replication and schema setup
│   ├── post_sync.py         # Sequences, triggers, materialized views
│   ├── validation.py        # Object and data parity auditing
│   ├── report_generator.py  # HTML audit report generation
│   ├── main.py              # Textual TUI Application
│   └── cli/                 # CLI-specific logic
│       ├── commands.py      # Individual step command wrappers
│       ├── pipelines.py     # Orchestrated multi-step pipelines
│       └── helpers.py       # Shared CLI formatting and logging
├── tests/                   # Test suite (Unit, Integration, E2E)
└── test_env/                # Docker Compose environment for testing
```

---

## Core Modules & Classes

### 1. Configuration (`src/config.py`)
- **Class `Config`**: Responsible for reading the `config_migrator.ini` file. It parses connection details for the source and destination databases and prepares the replication settings.
- **Multi-Schema Support**: The `target_schema` setting in the `[replication]` section now supports:
    - `public`: Migrates only the public schema (default).
    - `all`: Migrates all user schemas (excluding `pg_catalog` and `information_schema`).
    - `schema1, schema2`: A comma-separated list of specific schemas to migrate.
- **Method `get_target_schemas()`**: Returns a list of strings representing the selected schemas or `['all']`.

### 2. Database Interaction (`src/db.py`)
- **Class `PostgresClient`**: A wrapper around `psycopg` (v3). It manages database connections and provides robust methods for executing SQL queries (`execute_query`) and scripts (`execute_script`). It handles connection lifecycle, error logging, and cursor management.

### 3. Diagnostics & Pre-flight (`src/checker.py`)
- **Class `DBChecker`**: Conducts the initial safety checks.
  - `check_connectivity()`: Ensures both databases are reachable.
  - `check_problematic_objects()`: Scans for tables missing primary keys, large objects, identity columns, unowned sequences, and unsupported table types (unlogged, temporary, foreign).
  - `check_replication_params()`: Verifies that the source database has the correct `wal_level`, `max_replication_slots`, and `max_wal_senders`.

### 4. Migration Execution (`src/migrator.py`)
- **Class `Migrator`**: Handles the heavy lifting of schema copying and replication setup.
  - **Dynamic Schema Arguments**: `pg_dump` calls in `step4a` and `step4b` now dynamically build `--schema` arguments based on the user's selection. If `all` is selected, no `--schema` flags are passed, allowing a full database schema dump.
  - `step5_setup_source()`: Creates the PostgreSQL Publication (`CREATE PUBLICATION ... FOR ALL TABLES`). It also automatically sets `REPLICA IDENTITY FULL` for any tables without Primary Keys within the selected schemas.
  - `step6_setup_destination()`: Creates the PostgreSQL Subscription on the target.
  - `step12_terminate_replication()`: Cleans up by dropping the subscription and publication.

### 5. Post-Synchronization (`src/post_sync.py`)
- **Class `PostSync`**: Manages objects not automatically handled by logical replication.
  - `refresh_materialized_views()`: Runs `REFRESH MATERIALIZED VIEW` on the target.
  - `sync_sequences()`: Fetches `last_value` from source sequences and applies them to the target using `setval()`.
  - `enable_triggers()`: Re-enables triggers on the destination (`ALTER TABLE ... ENABLE TRIGGER ALL`).
  - `reassign_ownership()`: Corrects object ownership on the destination database.

### 6. Validation & Auditing (`src/validation.py`)
- **Class `Validator`**: Ensures the migration was successful and complete.
  - `audit_objects()`: Counts all schemas, tables, views, indexes, sequences, and functions on both ends to ensure structural parity.
  - `compare_row_counts()`: Executes `SELECT count(*)` on all user tables on both source and destination to guarantee data integrity.

### 7. Reporting Engine (`src/report_generator.py`)
- **Class `ReportGenerator`**: Generates the final audit-ready HTML reports (`report_init.html` and `report_post.html`). It collects execution steps, status messages, raw SQL/shell commands, and standard outputs, formatting them into a styled Jinja2 template.

---

## User Interfaces

### Command Line Interface (CLI)
- **`pg_migrator.py`**: Uses `argparse` to provide access to individual steps (e.g., `check`, `diagnose`, `validate-rows`) and orchestrated pipelines.
- **`src/cli/pipelines.py`**: Contains the two main automated workflows:
  - `cmd_init_replication()`: Orchestrates steps 1 through 7, plus initial validation.
  - `cmd_post_migration()`: Orchestrates steps 8 through 14, terminating replication and finalizing the target.

### Terminal User Interface (TUI)
- **`src/main.py`**: Built with the `Textual` framework. It provides a full-screen, interactive dashboard (`MigratorApp`). It features a step-by-step sidebar, a main Result Zone for summaries, and a real-time Command Output Zone for logs.

---

## Testing Framework (`tests/`)

The project uses `pytest` and is divided into three tiers:
1. **Unit Tests (`tests/unit/`)**: Tests individual methods using mocked database clients.
2. **Integration Tests (`tests/integration/`)**: Requires the Docker `test_env/`. It executes individual steps against live PostgreSQL 16 and 17 containers using the `pagila` dataset.
3. **End-to-End Tests (`tests/e2e/`)**: Runs the full `init-replication` and `post-migration` pipelines as subprocesses, verifying the generation of HTML reports and final data parity.

---

## Error Handling and Logging

- **Logging**: Configured in `src/cli/helpers.py`. All output is logged to `pg_migrator.log` inside a timestamped `RESULTS/` directory.
- **Error Handling**: Database operations in `src/db.py` catch `psycopg.Error` and raise custom exceptions. The CLI pipelines wrap execution in `try/except` blocks to gracefully fail and generate an error report (`report_init_error.html`) if a critical step (like connectivity) fails.
