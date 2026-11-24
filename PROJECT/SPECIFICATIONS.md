![pg_logical_migrator](../pg_logical_migrator.jpg)

# Project Specifications

## Overview

`pg_logical_migrator` is a Python-based CLI tool that automates PostgreSQL database migrations using **logical replication** (publish/subscribe). It provides a step-by-step Wizard for interactive execution and incremental pipeline commands (`init-replication`, `post-migration`) for hands-off migrations.

- **Language**: Python ≥ 3.9
- **Key Libraries**: `rich`, `psycopg` (v3), `psycopg-binary`
- **PostgreSQL**: Source and destination must be PostgreSQL 10 or higher with `wal_level = logical`

---

## Source Code Architecture

| Module | Class / Function | Responsibility |
| :--- | :--- | :--- |
| `src/config.py` | `Config` | Reads and validates `config_migrator.ini` |
| `src/db.py` | `PostgresClient` | Connection pooling, identifier sanitization, password redaction |
| `src/schema_utils.py` | `SchemaFilterMixin` | Schema-filter SQL builders (`public`, list, or `all`) |
| `src/checker.py` | `DBChecker` | Steps 1–3: Connectivity, diagnostics, parameter checks |
| `src/migrator.py` | `Migrator` | Facade composing `src/migrator_components/` (`schema`, `replication`, `monitoring`, `data_sync`) |
| `src/post_sync.py` | `PostSync` | Steps 8, 9, 12, 13: MatViews refresh, sequence sync, triggers, ownership |
| `src/validation.py` | `Validator` | Steps 14–15: Object audit and row parity comparison |
| `src/report_generator.py` | `ReportGenerator` | Generates self-contained HTML audit reports |
| `src/cli/wizard.py` | `MigrationWizard`, `WizardModel`, `WizardView` | Rich MVC interactive migration assistant |

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

Entry point: `pg_migrator.py` (project root).

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--config PATH` / `-c` | string | `config_migrator.ini` | Path to the INI configuration file |
| `--results-dir PATH` | string | `RESULTS/<timestamp>` | Output directory for logs and HTML reports |
| `--loglevel LEVEL` | choice | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--log-file FILE` | string | `pg_migrator.log` | Path to the log file |
| `--sync-delay SECONDS` | integer | `3600` | Max seconds to wait for initial sync to complete |
| `--dry-run` / `-n` | flag | `False` | Preview steps without executing any changes |
| `--verbose` / `-v` | flag | `False` | Print executed SQL commands, results, and errors to stderr |
| `--use-stats` | flag | `False` | Use `pg_stat_user_tables` estimates instead of `COUNT(*)` |
| `--version` / `-V` | flag | — | Display version and exit |

---

## Step-by-Step Wizard

Launched via `python pg_migrator.py wizard` (supports `--non-interactive`). Provides a Rich MVC assistant (`WizardModel`, `WizardView`, `MigrationWizard`) for guided step-by-step execution.

---

## Incremental Pipeline Mode

### `init-replication`

Executes **Phase 1** and **Phase 2**:
- `check` (Step 1)
- `diagnose` (Step 2)
- `params` (Step 3)
- `migrate-schema-pre-data` (Step 4, optional `--drop-dest`)
- `setup-pub` (Step 5)
- `setup-sub` (Step 6)
- `wait_for_sync` (Step 7, when `--wait` is set)
- `audit-objects` (Step 14)
- `validate-rows` (Step 15, when `--wait` is set)

### `post-migration`

Executes **Phase 3** and **Phase 4**:
- `check` (Step 1)
- `wait_for_sync` (Sync catch-up)
- `terminate-repl` (Step 10)
- `refresh-matviews` (Step 8)
- `sync-sequences` (Step 9)
- `migrate-schema-post-data` (Step 10.2)
- `sync-lobs` (Step 11a)
- `sync-unlogged` (Step 11b)
- `enable-triggers` (Step 12)
- `reassign-owner` (Step 13)
- `audit-objects` (Step 14)
- `validate-rows` (Step 15)

All steps are wrapped in a `try/except` block. On any fatal exception, a partial error report is written to `RESULTS/<timestamp>/report_init_error.html` or `report_post_error.html`.

---

## Results & Artifacts

All run outputs are stored in timestamped directories under `RESULTS/`.

| Artifact | Path | Description |
| :--- | :--- | :--- |
| `pg_migrator.log` | `RESULTS/<timestamp>/` | Full structured log with timestamps |
| `report_init.html` | `RESULTS/<timestamp>/` | Self-contained HTML audit report for `init-replication` |
| `report_post.html` | `RESULTS/<timestamp>/` | Self-contained HTML audit report for `post-migration` |
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
| `make install` | Create `venv/` and install Python dependencies (includes PyInstaller) |
| `make build` | Bundle the tool into a self-contained single-file binary (`dist/pg_migrator`) |
| `make build-clean` | Remove PyInstaller artefacts (`build/`, `dist/`, `*.spec`) |
| `make env-up` | Start Docker test containers and load the Pagila dataset |
| `make env-down` | Stop and remove Docker test containers |
| `make test-unit` | Run unit tests |
| `make test-integration` | Run integration tests (requires Docker env) |
| `make test-e2e` | Run full end-to-end migration test |
| `make test-all` | Run all tests (unit + integration + e2e) |
| `make test-report` | Run unit tests + automated migration; generate HTML reports |
| `make run-pipeline` | Run an automated migration via `init-replication` and `post-migration` |
| `make clean` | Remove `RESULTS/`, logs, `__pycache__`, and build artefacts |

---

## Standalone Executable

The tool can be packaged into a single self-contained binary using PyInstaller:

```bash
make build          # produces dist/pg_migrator
```

The binary embeds the Python interpreter, all dependencies, the `src/` modules, and `config_migrator.sample.ini`. It targets the **build platform** (Linux → Linux binary). A `config_migrator.ini` and PostgreSQL client tools (`pg_dump`, `psql`) must be present on the target host.

---

## Limitations

Logical replication in PostgreSQL has inherent constraints. See [LIMITATIONS.md](../DOCS/LIMITATIONS.md) for the full list, including:

- Tables **without a Primary Key** are not replicated (UPDATE and DELETE are unsupported).
- **Large Objects** (LOBs / `oid` columns) are not replicated.
- **DDL changes** (schema modifications) are not replicated — only DML (INSERT, UPDATE, DELETE).
- **Sequences** must be synchronized manually (hence Steps 9 & 10).
- **Materialized Views** must be refreshed manually after sync (Step 8).
