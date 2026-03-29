# Tools & Usage Guide

This document covers all the ways to invoke and operate `pg_logical_migrator`, from single-step commands to the interactive Terminal UI and fully automated CI/CD pipelines.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Configuration File](#2-configuration-file)
3. [Makefile Targets](#3-makefile-targets)
4. [CLI — pg_migrator.py](#4-cli--pg_migratorpy)
5. [Global Options](#5-global-options)
6. [Available Commands](#6-available-commands)
7. [Interactive TUI Mode](#7-interactive-tui-mode)
8. [Automated Mode (auto)](#8-automated-mode-auto)
9. [Output Artifacts](#9-output-artifacts)

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

All connection parameters are read from an `.ini` file. Generate or copy the sample before first use:

```bash
# Generate a new sample config
python pg_migrator.py generate-config --output config_migrator.ini

# Or copy the existing sample
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

---

## 3. Makefile Targets

The `Makefile` provides quick-access orchestration targets.

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

## 4. CLI — pg_migrator.py

The primary entry point is `pg_migrator.py` at the project root. It uses subcommands to expose every migration step individually, plus the full pipeline and TUI modes.

```bash
python pg_migrator.py --help
python pg_migrator.py <command> [options]
```

> **Note**: The legacy entry point `src/main.py` is still functional but `pg_migrator.py` is now the recommended CLI with richer options.

---

## 5. Global Options

These options apply to **all** commands and must be placed **before** the subcommand:

```bash
python pg_migrator.py [GLOBAL OPTIONS] <command> [COMMAND OPTIONS]
```

| Option | Short | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--version` | `-V` | flag | — | Display the program version and exit |
| `--config FILE` | `-c` | string | `config_migrator.ini` | Path to the `.ini` configuration file |
| `--results-dir DIR` | — | string | `RESULTS/<timestamp>` | Directory for storing results and HTML reports |
| `--loglevel LEVEL` | — | choice | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--log-file FILE` | — | string | auto | Path to the log file |
| `--sync-delay SECONDS` | — | integer | `10` | Seconds to wait after subscription creation for initial sync |
| `--dry-run` | `-n` | flag | `False` | Simulate execution without making any changes |

### Examples with global options

```bash
# Use a custom config and DEBUG logging
python pg_migrator.py -c /etc/pg_migrator/prod.ini --loglevel DEBUG check

# Dry-run the full pipeline with a 20s sync delay
python pg_migrator.py --dry-run --sync-delay 20 auto

# Store results in a custom directory
python pg_migrator.py --results-dir /var/reports/migration_001 auto
```

---

## 6. Available Commands

Each command corresponds to one or more steps in the 14-step migration workflow. Use `python pg_migrator.py <command> --help` for per-command details.

### Pre-Flight Checks (Steps 1–3)

| Command | Step | Description |
| --- | --- | --- |
| `check` | 1 | Test connectivity to source and destination databases |
| `diagnose` | 2 | Pre-migration diagnostics: tables without PK, LOBs, identity columns, unowned sequences |
| `params` | 3 | Verify replication parameters (`wal_level`, `max_replication_slots`, `max_wal_senders`) |

```bash
python pg_migrator.py check
python pg_migrator.py diagnose
python pg_migrator.py params
```

### Replication Setup (Steps 4–7)

| Command | Step | Description |
| --- | --- | --- |
| `migrate-schema` | 4 | Copy schema from source to destination (`pg_dump -s \| psql`) |
| `setup-pub` | 5 | Create publication (`FOR ALL TABLES`) on the source |
| `setup-sub` | 6 | Create subscription on the destination |
| `repl-status` | 7 | Show current logical replication status from `pg_stat_subscription` |

```bash
python pg_migrator.py migrate-schema
python pg_migrator.py setup-pub
python pg_migrator.py setup-sub
python pg_migrator.py repl-status
```

### Post-Sync Operations (Steps 8–11)

| Command | Step | Description |
| --- | --- | --- |
| `sync-sequences` | 8/9 | Read current sequence values from source and apply on destination |
| `enable-triggers` | 10 | `ALTER TABLE … ENABLE TRIGGER ALL` on every user table |
| `disable-triggers` | — | Utility: disable all triggers (inverse of Step 10) |
| `refresh-matviews` | 11 | `REFRESH MATERIALIZED VIEW` for every materialized view |

```bash
python pg_migrator.py sync-sequences
python pg_migrator.py enable-triggers
python pg_migrator.py refresh-matviews
```

### Validation (Steps 13–14)

| Command | Step | Description |
| --- | --- | --- |
| `audit-objects` | 13 | Compare object counts (tables, views, indexes, sequences, functions) between source and destination |
| `validate-rows` | 14 | `SELECT COUNT(*)` on every table in both databases and report differences |

```bash
python pg_migrator.py audit-objects
python pg_migrator.py validate-rows
```

### Cleanup (Step 12)

| Command | Step | Description |
| --- | --- | --- |
| `cleanup` | 12 | Drop subscription, publication, and replication slot (**destructive**) |

> **Warning**: Always run `audit-objects` and `validate-rows` **before** `cleanup` to confirm data parity.

```bash
python pg_migrator.py cleanup
```

### Pipeline & UI Commands

| Command | Description |
| --- | --- |
| `auto` | Run the full 14-step automated pipeline with HTML report generation |
| `tui` | Launch the interactive Terminal UI (Textual) for supervised migration |
| `generate-config` | Generate a sample `config_migrator.ini` file |

```bash
# Full automated pipeline
python pg_migrator.py auto

# Dry-run (shows steps without executing)
python pg_migrator.py --dry-run auto

# Interactive TUI
python pg_migrator.py tui

# Generate a config file
python pg_migrator.py generate-config --output my_config.ini
```

---

## 7. Interactive TUI Mode

Launched via `python pg_migrator.py tui`. Presents a full-screen terminal dashboard built with the `textual` framework.

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

## 8. Automated Mode (auto)

Runs the full migration pipeline non-interactively in a predefined sequence:

| Step | Module Call | Action |
| --- | --- | --- |
| 1 | `checker.check_connectivity()` | Connectivity check |
| 4 | `migrator.step4_migrate_schema()` | Schema migration (`pg_dump -s` → destination) |
| 5 | `migrator.step5_setup_source()` | Create Publication + Replication Slot on source |
| 6 | `migrator.step6_setup_destination()` | Create Subscription on destination |
| — | `time.sleep(sync_delay)` | Wait for initial table sync (default: 10s, configurable via `--sync-delay`) |
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

**Dry-run mode**: Use `--dry-run` to preview the sequence without executing any step:

```bash
python pg_migrator.py --dry-run auto
```

Output:

```text
============================================================
  pg_logical_migrator — Automated Pipeline v1.0.0
  Config      : config_migrator.ini
  Results dir : RESULTS/20260329_231754
  Log level   : INFO
  Sync delay  : 10s
  Mode        : DRY-RUN (no changes)
============================================================

  [DRY-RUN] Step  1 : Connectivity Check
  [DRY-RUN] Step  4 : Schema Migration (pg_dump -s | psql)
  [DRY-RUN] Step  5 : Create Publication
  [DRY-RUN] Step  6 : Create Subscription
  [DRY-RUN] Step -- : Wait 10s for initial sync
  [DRY-RUN] Step  8 : Refresh Materialized Views
  [DRY-RUN] Step  9 : Sync Sequences
  [DRY-RUN] Step 10 : Enable Triggers
  [DRY-RUN] Step 13 : Object Audit
  [DRY-RUN] Step 14 : Row Parity Check
  [DRY-RUN] Step 12 : Cleanup Replication

  No changes were made.
```

---

## 9. Output Artifacts

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
