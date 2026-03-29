# Project Specifications

## Overview

`pg_logical_migrator` is a Python-based CLI tool that automates PostgreSQL database migrations using **logical replication** (publish/subscribe). It provides a Textual Terminal User Interface (TUI) for interactive step-by-step execution and an automated mode (`--auto`) for hands-off pipelines.

- **Language**: Python ≥ 3.10
- **Key Libraries**: `textual`, `rich`, `psycopg` (v3), `psycopg-binary`
- **PostgreSQL**: Source and destination must be PostgreSQL 10 or higher with `wal_level = logical`

---

## Source Code Architecture

| Module | Class / Function | Responsibility |
| :--- | :--- | :--- |
| `src/config.py` | `Config` | Reads and validates `config_migrator.ini` |
| `src/db.py` | `PostgresClient` | Low-level connection management and query execution |
| `src/checker.py` | `DBChecker` | Steps 1–3: Connectivity, diagnostics, parameter checks |
| `src/migrator.py` | `Migrator` | Steps 4–7, 12: Schema migration, pub/sub setup, cleanup |
| `src/post_sync.py` | `PostSync` | Steps 8–11: MatViews refresh, sequence sync, trigger activation |
| `src/validation.py` | `Validator` | Steps 13–14: Object audit and row parity comparison |
| `src/report_generator.py` | `ReportGenerator` | Generates self-contained HTML audit reports |
| `src/main.py` | `MigratorApp` / `run_automated()` | TUI entry point and `--auto` orchestrator |

---

## Configuration (`.ini`)

The tool reads all runtime parameters from `config_migrator.ini` (copy from `config_migrator.sample.ini`).

### Sections

| Section | Key Parameters |
| :--- | :--- |
| `[source]` | `host`, `port`, `user`, `password`, `database` |
| `[destination]` | `host`, `port`, `user`, `password`, `database` |
| `[replication]` | `publication_name`, `subscription_name`, `target_schema`, `loglevel`, `log_file` |

### Minimum PostgreSQL requirements on source

| Parameter | Required Value |
| :--- | :--- |
| `wal_level` | `logical` |
| `max_replication_slots` | ≥ 1 |
| `max_wal_senders` | ≥ 1 |

---

## CLI Interface

Entry point: `src/main.py`

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--config PATH` | string | `config_migrator.ini` | Path to the INI configuration file |
| `--auto` | flag | `False` | Non-interactive automated mode |
| `--results-dir PATH` | string | `RESULTS/<timestamp>` | Output directory for logs and HTML reports |

---

## TUI (Terminal User Interface)

Built with the [`textual`](https://textual.textualize.io/) framework. Launched when `--auto` is not specified.

- **Sidebar**: 14 step-buttons, color-coded by phase (blue = checks, orange = replication setup, green = monitoring, purple = post-sync, yellow = validation, red = cleanup).
- **Result Zone**: Displays step output as a `Panel` or `Table` (Rich components).
- **Log Area**: Live scrolling log of all step executions.

---

## Automated Mode (`--auto`)

Executes the full pipeline non-interactively in this order:

```text
Step 1 (Connectivity) →
Step 4 (Schema Migration) →
Step 5 (Source Pub/Slot) →
Step 6 (Destination Sub) →
[10-second wait for initial sync] →
Step 8 (MatViews Refresh) →
Steps 9/10 (Sequence Sync) →
Step 11 (Trigger Activation) →
Step 13 (Object Audit) →
Step 14 (Row Parity) →
Step 12 (Replication Cleanup)
```

All steps are wrapped in a `try/except` block. On any fatal exception, a partial error report is written to `RESULTS/<timestamp>/migration_report_error.html`.

---

## Results & Artifacts

All run outputs are stored in timestamped directories under `RESULTS/`.

| Artifact | Path | Description |
| :--- | :--- | :--- |
| `pg_migrator.log` | `RESULTS/<timestamp>/` | Full structured log with timestamps |
| `migration_report.html` | `RESULTS/<timestamp>/` | Self-contained HTML audit report |
| `unit_tests.html` | `RESULTS/<timestamp>/` | Pytest HTML output (via `make test-report`) |

Each HTML report step entry contains:

- Status badge (OK / FAIL / ERROR)
- Human-readable summary message
- Exact shell and SQL commands executed
- Raw command output for independent verification

---

## Quality Assurance & Testing

### Unit Tests (`tests/unit/`)

- **Framework**: `pytest` with `unittest.mock`
- **Coverage**: All `src/` modules are tested with mocked database connections.
- **Run**: `make test-unit`

### End-to-End Tests (`tests/e2e/`)

- **Dataset**: Pagila (PostgreSQL sample database with movies, actors, rental data)
- **Environment**: Docker Compose (PostgreSQL 16 source + PostgreSQL 17 destination)
- **Verification**: Row count parity and object consistency after full sync.
- **Run**: `make test-e2e` (requires `make env-up` first)

---

## Project Orchestration (Makefile)

| Target | Description |
| :--- | :--- |
| `make install` | Create `venv/` and install Python dependencies |
| `make env-up` | Start Docker test containers and load the Pagila dataset |
| `make env-down` | Stop and remove Docker test containers |
| `make test-unit` | Run unit tests |
| `make test-integration` | Run integration tests (requires Docker env) |
| `make test-e2e` | Run full end-to-end migration test |
| `make test-all` | Run all tests (unit + integration + e2e) |
| `make test-report` | Run unit tests + automated migration; generate HTML reports |
| `make run-auto` | Run a full automated migration against `config_migrator.ini` |
| `make clean` | Remove `RESULTS/`, logs, and `__pycache__` directories |

---

## Limitations

Logical replication in PostgreSQL has inherent constraints. See [LIMITATIONS.md](../DOCS/LIMITATIONS.md) for the full list, including:

- Tables **without a Primary Key** are not replicated (UPDATE and DELETE are unsupported).
- **Large Objects** (LOBs / `oid` columns) are not replicated.
- **DDL changes** (schema modifications) are not replicated — only DML (INSERT, UPDATE, DELETE).
- **Sequences** must be synchronized manually (hence Steps 9 & 10).
- **Materialized Views** must be refreshed manually after sync (Step 8).
