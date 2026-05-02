![pg_logical_migrator](../pg_logical_migrator.jpg)

# Codebase Architecture & Reference

This document provides a comprehensive overview of the `pg_logical_migrator` codebase. It details the project's architecture, core modules, classes, and their responsibilities.

---

## High-Level Architecture

The project is a modular Python application providing both a Command Line Interface (CLI) and a Terminal User Interface (TUI). It is built around single-responsibility classes managing logical replication phases (diagnostics, setup, post-sync, and validation).

### Directory Structure

```text
pg_logical_migrator/
├── pg_migrator.py           # Main CLI entry point
├── src/                     # Core Python modules
│   ├── config.py            # Configuration management
│   ├── db.py                # Database interaction wrapper & utilities
│   ├── checker.py           # Pre-flight diagnostics and size analysis
│   ├── migrator.py          # Core replication and schema setup
│   ├── post_sync.py         # Sequences, triggers, materialized views, ownership
│   ├── validation.py        # Object and data parity auditing
│   ├── report_generator.py  # HTML audit report generation
│   ├── tui.py               # Textual TUI Application logic
│   ├── main.py              # TUI entry point
│   └── cli/                 # CLI-specific logic
│       ├── commands.py      # Individual step command wrappers
│       ├── pipelines.py     # Orchestrated multi-step pipelines (init-replication, post-migration)
│       └── helpers.py       # Shared CLI formatting and logging utilities
├── tests/                   # Test suite (Unit, Integration, E2E, Workflow)
│   ├── unit/                # 279 unit tests — no Docker required (96% src/ coverage)
│   ├── integration/         # Database connectivity tests (requires Docker)
│   └── e2e/                 # Full 17-step migration tests (requires Docker + Pagila)
├── .github/workflows/       # CI/CD pipelines
│   ├── python-package.yml   # Lint, test, Docker GHCR, Python assets
│   ├── pyinstaller-publish.yml  # Standalone binaries + DEB/RPM + GitHub Release
│   └── docker-publish.yml   # Docker Hub publish
└── test_env/                # Docker Compose environment for testing
```

---

## Core Modules & Classes

### 1. Configuration (`src/config.py`)
- **Class `Config`**: Reads `config_migrator.ini`.
- **Multi-Schema Support**: The `target_schema` setting supports `public` (default), `all` (every user schema), or a comma-separated list.
- **Method `get_target_schemas()`**: Returns the list of targeted schemas or `['all']`.

### 2. Database Interaction (`src/db.py`)
- **Class `PostgresClient`**: Wrapper around `psycopg` (v3) for SQL execution and connection management.
- **Utility `pretty_size(bytes)`**: Formats byte counts into human-readable strings (kB, MB, GB).

### 3. Diagnostics & Pre-flight (`src/checker.py`)
- **Class `DBChecker`**:
  - `check_problematic_objects()`: Scans for missing PKs, LOBs, identity columns, etc.
  - `get_database_size_analysis()`: Calculates total database size and per-table breakdown (Data, Index, % DB footprint).
  - All diagnostics respect the `target_schema` filtering when a `Config` object is provided.

### 4. Migration Execution (`src/migrator.py`)
- **Class `Migrator`**:
  - `step4a_...()` & `step4b_...()`: Subprocess-based `pg_dump` for pre-data and post-data schema sections.
  - `step5_setup_source()`: Creates the Publication. Uses `FOR TABLES IN SCHEMA` if specific schemas are targeted.
  - `wait_for_sync(timeout, show_progress=True)`: Polls `pg_subscription_rel` until all tables are ready. Displays real-time progress.
  - `get_initial_copy_progress()`: Returns detailed byte-level and table-count synchronization status.

### 5. Post-Synchronization (`src/post_sync.py`)
- **Class `PostSync`**:
  - `refresh_materialized_views()`, `sync_sequences()`, `enable_triggers()`.
  - `reassign_ownership(target_owner)`: Changes owner for all migrated objects, intelligently excluding internal table-row types.
  - All operations filter by the targeted schemas defined in the config.

### 6. Validation & Auditing (`src/validation.py`)
- **Class `Validator`**:
  - `audit_objects()`: Structural parity check (TABLE, VIEW, INDEX, etc.).
  - `compare_row_counts(use_stats=False)`: Data parity check. If `use_stats` is True, uses `pg_stat_user_tables` for near-instant estimation on large tables.

---

## User Interfaces

### Command Line Interface (CLI)
- **`pg_migrator.py`**: Entry point using `argparse`.
- **`src/cli/pipelines.py`**: Orchestrates high-level workflows:
  - `init-replication`: Steps 1-6 + `wait_for_sync` + Validation. Includes `--no-wait` option.
  - `post-migration`: `wait_for_sync` + Step 16 (Stop) + Step 12 (Post-Data) + Post-sync + Validation.

### Terminal User Interface (TUI)
- **`src/tui.py`**: A full-screen dashboard with a 17-step interactive sidebar.
- Features real-time progress widgets, size analysis tables, and toggleable options (Stats counting, Verbose mode).
- Uses `rich` components (Panel, Table) for robust, styled rendering.

---

## Error Handling and Logging

- **Logging**: Centrally configured in `src/cli/helpers.py` via `setup_logging()`. Both console and file handlers are supported.
- **Pipeline Reliability**: Automated pipelines wrap critical steps in `try/except` blocks and generate `report_init_error.html` or `report_post_error.html` on fatal failures.

---

## Test Infrastructure

The project maintains **96% unit test coverage** across `src/`. See [DOCS/TESTING.md](TESTING.md) for the full reference.

### Makefile Targets

| Target | Description |
|---|---|
| `make test-unit` | Run 279 unit tests (no Docker) |
| `make test-coverage` | Unit tests + coverage report (HTML + terminal) |
| `make test-integration` | Integration tests (requires Docker) |
| `make test-e2e` | End-to-end migration test (requires Docker) |
| `make test-packaging` | Binary + DEB/RPM + wheel packaging validation |
| `make test-all` | All of the above in sequence |
| `make test-report` | Unit tests + HTML report + full pipeline run |
| `make env-up` | Start Docker test environment (PostgreSQL × 2 + Pagila) |
| `make env-down` | Tear down Docker environment |
