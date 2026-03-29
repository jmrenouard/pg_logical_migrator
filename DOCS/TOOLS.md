# Tools & Usage Guide

This document covers all the ways to invoke and operate `pg_logical_migrator`, from the interactive Terminal UI (built with [Textual](https://textual.textualize.io/)) to fully automated CI/CD pipelines.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Configuration File](#2-configuration-file)
3. [Makefile Targets (Recommended Entry Point)](#3-makefile-targets)
4. [CLI — Direct Invocation](#4-cli--direct-invocation)
5. [Interactive TUI Mode](#5-interactive-tui-mode)
6. [Automated Mode (`--auto`)](#6-automated-mode---auto)
7. [Output Artifacts](#7-output-artifacts)

---

## 1. Prerequisites

| Requirement | Description |
| --- | --- |
| Python ≥ 3.10 | Interpreter for all tool logic (`textual` requires ≥ 3.10) |
| `pg_dump` / `psql` | PostgreSQL client tools (≥ v10) — must be on `PATH` |
| `psycopg` v3 | Python PostgreSQL driver — installed via `requirements.txt` |
| Docker + Compose | Required **only** for the integrated test environment |
| `python3-venv` | For isolated dependency management |

Install Python dependencies into an isolated virtual environment:

```bash
make install
```

This creates `venv/` and installs everything listed in `requirements.txt`.

---

## 2. Configuration File

All connection parameters are read from an `.ini` file. Copy the sample before first use:

```bash
cp config_migrator.sample.ini config_migrator.ini
```

Then edit the three sections:

```ini
[source]
host     = <source_host>
port     = 5432
user     = postgres
password = <password>
database = <db_name>

[destination]
host     = <dest_host>
port     = 5433
user     = postgres
password = <password>
database = <db_name>

[replication]
publication_name  = migrator_pub          # Name of the logical publication on source
subscription_name = migrator_sub          # Name of the logical subscription on destination
target_schema     = public                # Schema to migrate (default: public)
loglevel          = INFO                  # DEBUG | INFO | WARNING | ERROR
log_file          = pg_migrator.log       # Default log path (overridden in --auto mode)
```

> **Important**: The PostgreSQL user must have `REPLICATION` privilege on the source and `SUPERUSER` (or appropriate `pg_hba.conf` replication entry) for the destination.

You can point to a different config file with the `--config` flag at runtime.

---

## 3. Makefile Targets

The `Makefile` is the primary orchestration interface.

```bash
make help
```

| Target | Description |
| --- | --- |
| `make install` | Create `venv/` and install all Python dependencies |
| `make env-up` | Start Docker test containers and load the Pagila dataset |
| `make env-down` | Stop and remove Docker test containers |
| `make test-unit` | Run unit tests (`tests/unit/`) |
| `make test-integration` | Run integration tests (requires running Docker env) |
| `make test-e2e` | Run end-to-end migration test (requires Docker env) |
| `make test-all` | Run the full test suite: unit + integration + e2e |
| `make test-report` | Run tests and the automated migration, then generate HTML reports |
| `make run-auto` | Run a full automated migration using `config_migrator.ini` |
| `make clean` | Remove `RESULTS/`, `pg_migrator.log`, and `__pycache__` directories |

### Quick-start for a real migration

```bash
make install          # one-time setup
# edit config_migrator.ini
make run-auto         # run automated pipeline
```

### Quick-start for development/testing

```bash
make install
make env-up           # start source + destination containers
make test-all         # run full test suite
make env-down         # clean up containers
```

---

## 4. CLI — Direct Invocation

The entry point is `src/main.py`. It accepts the following arguments:

```bash
venv/bin/python src/main.py [OPTIONS]
```

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--config PATH` | string | `config_migrator.ini` | Path to the `.ini` configuration file |
| `--auto` | flag | `False` | Run in non-interactive automated mode |
| `--results-dir PATH` | string | `RESULTS/<timestamp>` | Directory where logs and HTML reports are written |

### Examples

```bash
# Interactive TUI with default config
venv/bin/python src/main.py

# Interactive TUI with a custom config
venv/bin/python src/main.py --config /etc/pg_migrator/prod.ini

# Fully automated run, results in a custom directory
venv/bin/python src/main.py --auto --results-dir /var/reports/migration_prod

# Automated run, results auto-named by timestamp
venv/bin/python src/main.py --auto
```

---

## 5. Interactive TUI Mode

Launched by default (without `--auto`). Presents a full-screen terminal dashboard built with the `textual` framework.

```text
┌──────────────────── PostgreSQL Logical Migrator ────────────────────┐
│ Sidebar (steps)              │ Content Area                         │
│                              │                                      │
│  [1. Check Connectivity]  🔵 │  ┌── Result Panel ──────────────┐   │
│  [2. Run Diagnostics]     🔵 │  │                              │   │
│  [3. Verify Parameters]   🔵 │  │  Step output shown here      │   │
│  [4. Copy Schema]         🟠 │  └──────────────────────────────┘   │
│  [5. Setup Publication]   🟠 │                                      │
│  [6. Setup Subscription]  🟠 │  ┌── Live Log ──────────────────┐   │
│  [7. Replication Status]  🟢 │  │ > TUI Initialized. Ready...  │   │
│  [8. Sync Sequences]      🟣 │  │ > Running Step 1...          │   │
│  [9. Activate Seqs]       🟣 │  └──────────────────────────────┘   │
│  [10. Enable Triggers]    🟣 │                                      │
│  [11. Refresh MatViews]   🟣 │                                      │
│  [13. Object Audit]       🟡 │                                      │
│  [14. Row Parity]         🟡 │                                      │
│  [12. STOP/CLEANUP]       🔴 │                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Color coding**: 🔵 Pre-flight checks · 🟠 Replication setup · 🟢 Monitoring · 🟣 Post-sync · 🟡 Validation · 🔴 Destructive cleanup

> **Note**: Step 12 (STOP/CLEANUP) appears last intentionally — it is a destructive operation that drops the subscription, publication, and replication slot. Always run Steps 13 & 14 first to confirm data parity.

**Usage**: Click any button to execute that migration step. Each step displays its result in the Result Panel (as a Rich `Panel` or `Table`) and logs activity to the Live Log. Steps can be run individually or in sequence.

**Exit**: Press `q` or `Ctrl+C` to quit the TUI.

---

## 6. Automated Mode (`--auto`)

Runs the full migration pipeline non-interactively in a predefined sequence:

| Step | Module Call | Action |
| --- | --- | --- |
| 1 | `checker.check_connectivity()` | Connectivity check |
| 4 | `migrator.step4_migrate_schema()` | Schema migration (`pg_dump -s` → destination) |
| 5 | `migrator.step5_setup_source()` | Create Publication + Replication Slot on source |
| 6 | `migrator.step6_setup_destination()` | Create Subscription on destination |
| — | `time.sleep(10)` | Wait 10 seconds for initial table sync |
| 8 | `post_sync.refresh_materialized_views()` | Refresh materialized views on destination |
| 9/10 | `post_sync.sync_sequences()` | Fetch & apply sequence values |
| 11 | `post_sync.enable_triggers()` | Re-enable triggers on destination |
| 13 | `validator.audit_objects()` | Schema object parity check |
| 14 | `validator.compare_row_counts()` | Row count comparison per table |
| 12 | `migrator.step12_terminate_replication()` | Drop Sub, Pub, and Replication Slot |

A timestamped HTML report is generated at completion. If any step raises a fatal exception, a partial error report is written instead.

**Example output directory**:

```text
RESULTS/
└── 20260329_221400/
    ├── pg_migrator.log
    └── migration_report.html
```

---

## 7. Output Artifacts

| Artifact | Location | Description |
| --- | --- | --- |
| `pg_migrator.log` | `RESULTS/<timestamp>/` (auto) or project root (TUI) | Full structured log of all SQL and shell commands with timestamps |
| `migration_report.html` | `RESULTS/<timestamp>/` | Self-contained, audit-ready HTML report of every step |
| `unit_tests.html` | `RESULTS/<timestamp>/` | Generated by `make test-report`; pytest HTML output |

The HTML report contains, for each step:

- Status (OK / FAIL / ERROR)
- Human-readable summary message
- Exact shell and SQL commands executed
- Raw command outputs for independent verification

---

[Return to Documentation Index](README.md)
