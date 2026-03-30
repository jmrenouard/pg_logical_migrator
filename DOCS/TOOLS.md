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
8. [Incremental Pipeline Mode](#8-incremental-pipeline-mode)
9. [Output Artifacts](#9-output-artifacts)
10. [Building a Standalone Executable](#10-building-a-standalone-executable)

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
log_file          = pg_migrator.log       # Default log path
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
| `make install` | Create `venv/` and install all Python dependencies (includes PyInstaller) |
| `make build` | Bundle the tool into a self-contained single-file executable (`dist/pg_migrator`) |
| `make build-clean` | Remove PyInstaller build artefacts (`build/`, `dist/`, `*.spec`) |
| `make env-up` | Start Docker test containers and load the Pagila dataset |
| `make env-down` | Stop and remove Docker test containers |
| `make test-unit` | Run unit tests (`tests/unit/`) |
| `make test-integration` | Run integration tests (requires running Docker env) |
| `make test-e2e` | Run end-to-end migration test (requires Docker env) |
| `make test-all` | Run the full test suite: unit + integration + e2e |
| `make test-report` | Run tests and the pipelined migration, then generate HTML reports |
| `make run-pipeline` | Run a full incremental pipeline migration using `config_migrator.ini` |
| `make clean` | Remove `RESULTS/`, `pg_migrator.log`, `__pycache__`, and build artefacts |

### Quick-start for a real migration

```bash
make install          # one-time setup
# edit config_migrator.ini
make run-pipeline     # run incremental pipeline
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
| `--log-file FILE` | — | string | pg_migrator.log | Path to the log file |
| `--sync-delay SECONDS` | — | integer | `10` | Seconds to wait after subscription creation for initial sync |
| `--dry-run` | `-n` | flag | `False` | Simulate execution without making any changes |

### Examples with global options

```bash
# Use a custom config and DEBUG logging
python pg_migrator.py -c /etc/pg_migrator/prod.ini --loglevel DEBUG check

# Dry-run the initialization phase with a 20s sync delay
python pg_migrator.py --dry-run --sync-delay 20 init-replication

# Store results in a custom directory
python pg_migrator.py --results-dir /var/reports/migration_001 post-migration
```

---

## 6. Available Commands

Each command corresponds to one or more steps in the 14-step migration workflow. Use `python pg_migrator.py <command> --help` for per-command details.

### Pre-Flight Checks (Steps 1–3)

| Command | Step | Server | Description |
| --- | --- | --- | --- |
| `check` | 1 | **SOURCE + DEST** | Test connectivity to source and destination databases |
| `diagnose` | 2 | **SOURCE** | Pre-migration diagnostics: tables without PK, LOBs, identity columns, unowned sequences, unlogged/temp/foreign tables, materialized views (queries `pg_class`, `pg_largeobject_metadata`, `information_schema.columns` on **SOURCE**) |
| `params` | 3 | **SOURCE + DEST** | Verify replication parameters (`wal_level`, `max_replication_slots`, `max_wal_senders`) — queries `pg_settings` on **SOURCE** and on **DEST** |
| `apply-params` | — | **SOURCE + DEST** | Utility: execute `ALTER SYSTEM SET` on **SOURCE** and/or **DEST** to fix missing parameters |

```bash
python pg_migrator.py check            # SOURCE + DEST
python pg_migrator.py diagnose         # SOURCE
python pg_migrator.py params           # SOURCE + DEST
python pg_migrator.py apply-params     # SOURCE + DEST
```

### Replication Setup (Steps 4–7)

| Command | Step | Server | Description |
| --- | --- | --- | --- |
| `migrate-schema` | 4 | **SOURCE → DEST** | `pg_dump -s` on **SOURCE** piped into `psql` on **DEST**. With `--drop-dest`: `DROP DATABASE` + `CREATE DATABASE` on **DEST** |
| `setup-pub` | 5 | **SOURCE** | `DROP PUBLICATION IF EXISTS` + `CREATE PUBLICATION … FOR ALL TABLES` on **SOURCE** |
| `setup-sub` | 6 | **DEST** | `DROP SUBSCRIPTION IF EXISTS` + `CREATE SUBSCRIPTION … CONNECTION '…' PUBLICATION …` on **DEST** |
| `repl-status` | 7 | **SOURCE + DEST** | Query `pg_stat_subscription` on **DEST** and `pg_stat_replication`, `pg_replication_slots` on **SOURCE** |

```bash
python pg_migrator.py migrate-schema   # SOURCE → DEST
python pg_migrator.py setup-pub        # SOURCE
python pg_migrator.py setup-sub        # DEST
python pg_migrator.py repl-status      # SOURCE + DEST
```

### Post-Sync Operations (Steps 8–11)

| Command | Step | Server | Description |
| --- | --- | --- | --- |
| `sync-sequences` | 8/9 | **SOURCE → DEST** | `SELECT last_value, is_called` on **SOURCE**, then `SELECT setval(…)` on **DEST** |
| `enable-triggers` | 10 | **DEST** | `ALTER TABLE … ENABLE TRIGGER ALL` on every user table on **DEST** |
| `disable-triggers` | — | **DEST** | Utility: `ALTER TABLE … DISABLE TRIGGER ALL` on every user table on **DEST** |
| `refresh-matviews` | 11 | **DEST** | `REFRESH MATERIALIZED VIEW` for every materialized view on **DEST** |

```bash
python pg_migrator.py sync-sequences     # SOURCE → DEST
python pg_migrator.py enable-triggers    # DEST
python pg_migrator.py refresh-matviews   # DEST
```

### Validation (Steps 13–14)

| Command | Step | Server | Description |
| --- | --- | --- | --- |
| `audit-objects` | 13 | **SOURCE + DEST** | Same object-count query (tables, views, indexes, sequences, functions) run on **SOURCE** and on **DEST**, results compared |
| `validate-rows` | 14 | **SOURCE + DEST** | `SELECT COUNT(*)` on every table executed on **SOURCE** and on **DEST**, row counts compared |

```bash
python pg_migrator.py audit-objects     # SOURCE + DEST
python pg_migrator.py validate-rows    # SOURCE + DEST
```

### Cleanup (Step 12)

| Command | Step | Server | Description |
| --- | --- | --- | --- |
| `cleanup` | 12 | **DEST + SOURCE** | `DROP SUBSCRIPTION IF EXISTS` on **DEST**, then `DROP PUBLICATION IF EXISTS` on **SOURCE** (**destructive**) |

> **Warning**: Always run `audit-objects` and `validate-rows` **before** `cleanup` to confirm data parity.

```bash
python pg_migrator.py cleanup          # DEST + SOURCE
```

### Pipeline & UI Commands

| Command | Description |
| --- | --- |
| `init-replication` | Initialize replication and validate, leaving it active |
| `post-migration` | Finish replication sync and complete validations, destructive cleanup |
| `tui` | Launch the interactive Terminal UI (Textual) for supervised migration |
| `generate-config` | Generate a sample `config_migrator.ini` file |

```bash
# Incremental Pipeline Commands
python pg_migrator.py init-replication
python pg_migrator.py post-migration

# Dry-run (shows steps without executing)
python pg_migrator.py --dry-run init-replication

# Interactive TUI
python pg_migrator.py tui

# Generate a config file
python pg_migrator.py generate-config --output my_config.ini
```

---

## 7. Interactive TUI Mode

Launched via `python pg_migrator.py tui`. Presents a full-screen terminal dashboard built with the `textual` framework.

```text
┌────────────────────── PostgreSQL Logical Migrator ──────────────────────┐
│ Sidebar                         │ Content Area                          │
│                                 │                                       │
│  ── OPTIONS ────────────────    │  ┌── Result Panel ──────────────────┐ │
│  [ ] Drop Dest Schema          │  │                                  │ │
│  [ ] Monitor Replication        │  │  Step output shown here (Panel   │ │
│                                 │  │  or Rich Table)                  │ │
│  ── STEPS ──────────────────    │  └──────────────────────────────────┘ │
│  [1. Check Connectivity]    🔵  │                                       │
│  [2. Run Diagnostics]       🔵  │  ┌── Live Log ─────────────────────┐ │
│  [3. Verify Parameters]     🔵  │  │ > TUI Initialized. Ready...    │ │
│  [➤ Apply Parameters]       🔵  │  │ > Running Step 1...            │ │
│  [4. Copy Schema]           🟠  │  │ > ✔ Step 1 completed.          │ │
│  [5. Setup Publication]     🟠  │  └──────────────────────────────────┘ │
│  [6. Setup Subscription]    🟠  │                                       │
│  [7. Replication Status]    🟢  │                                       │
│  [8/9. Sync Sequences]      🟣  │                                       │
│  [10. Enable Triggers]      🟣  │                                       │
│  [➤ Disable Triggers]       🟣  │                                       │
│  [11. Refresh MatViews]     🟣  │                                       │
│  [13. Object Audit]         🟡  │                                       │
│  [14. Row Parity]           🟡  │                                       │
│  [12. STOP/CLEANUP]         🔴  │                                       │
│                                 │                                       │
│  ── AUTOMATION & UTILS ─────    │                                       │
│  [▶ Init Replication]       🟩  │                                       │
│  [▶ Post Migration]         🟩  │                                       │
│  [⚙ Generate Config]        ⬜  │                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Sidebar Sections

**OPTIONS** — Checkboxes that modify the behavior of certain steps:

| Checkbox | Effect |
| --- | --- |
| `Drop Dest Schema` | When checked, Step 4 (Copy Schema) and `init-replication` pipeline will drop and recreate the destination database before migrating the schema |
| `Monitor Replication` | When checked, the Result Panel auto-refreshes every 2 seconds with live `pg_stat_subscription` status |

**STEPS** — One button per migration step, plus utility commands:

| Button | CLI Equivalent | Server | Description |
| --- | --- | --- | --- |
| 1. Check Connectivity | `check` | **SOURCE + DEST** | Test connectivity to source and destination |
| 2. Run Diagnostics | `diagnose` | **SOURCE** | Pre-migration diagnostics (PK, LOBs, sequences, unlogged/temp/foreign tables, materialized views) |
| 3. Verify Parameters | `params` | **SOURCE + DEST** | Verify replication parameters (`wal_level`, etc.) |
| ➤ Apply Parameters | `apply-params` | **SOURCE + DEST** | Apply missing replication parameters via `ALTER SYSTEM` |
| 4. Copy Schema | `migrate-schema` | **SOURCE → DEST** | `pg_dump -s` on SOURCE piped to `psql` on DEST. Honors `Drop Dest Schema` checkbox |
| 5. Setup Publication | `setup-pub` | **SOURCE** | Create publication on SOURCE |
| 6. Setup Subscription | `setup-sub` | **DEST** | Create subscription on DEST (runs asynchronously) |
| 7. Replication Status | `repl-status` | **SOURCE + DEST** | Query `pg_stat_subscription` on **DEST** and `pg_stat_replication`, `pg_replication_slots` on **SOURCE** |
| 8/9. Sync Sequences | `sync-sequences` | **SOURCE → DEST** | Read sequence values from SOURCE, apply on DEST |
| 10. Enable Triggers | `enable-triggers` | **DEST** | Enable all triggers on DEST tables |
| ➤ Disable Triggers | `disable-triggers` | **DEST** | Disable all triggers on DEST tables |
| 11. Refresh MatViews | `refresh-matviews` | **DEST** | Refresh materialized views on DEST |
| 13. Object Audit | `audit-objects` | **SOURCE + DEST** | Compare object counts between databases |
| 14. Row Parity | `validate-rows` | **SOURCE + DEST** | Compare row counts per table |
| 12. STOP/CLEANUP | `cleanup` | **DEST + SOURCE** | `DROP SUBSCRIPTION` on DEST, `DROP PUBLICATION` on SOURCE |

**AUTOMATION & UTILS** — Pipeline and utility commands:

| Button | CLI Equivalent | Description |
| --- | --- | --- |
| ▶ Init Replication | `init-replication` | Runs schema migration, setups pub/sub, syncs objects and validates |
| ▶ Post Migration | `post-migration` | Cleans up replication objects and ensures final completeness |
| ⚙ Generate Config | `generate-config` | Write a sample `config_migrator.sample.ini` to disk |

### Color Coding

🔵 Pre-flight checks · 🟠 Replication setup · 🟢 Monitoring · 🟣 Post-sync · 🟡 Validation · 🔴 Destructive cleanup · 🟩 Automation · ⬜ Utility

> **Note**: Step 12 (STOP/CLEANUP) appears last in the STEPS section intentionally — it is a destructive operation that drops the subscription, publication, and replication slot. Always run Steps 13 & 14 first to confirm data parity.

### Asynchronous Steps

Step 6 (Setup Subscription), Init Replication, and Post Migration run **asynchronously** in a background thread to avoid blocking the TUI. The Result Panel and Live Log update in real time as these operations progress.

**Usage**: Click any button to execute that migration step. Each step displays its result in the Result Panel (as a Rich `Panel` or `Table`) and logs activity to the Live Log. Steps can be run individually or in sequence.

**Exit**: Press `q` or `Ctrl+C` to quit the TUI.

---

## 8. Incremental Pipeline Mode

Runs the migration pipeline non-interactively in an incremental sequence via two commands: `init-replication` and `post-migration`.

### A. Initialization (`init-replication`)

1. **Connectivity Check** (`checker.check_connectivity()` on **SOURCE + DEST**)
2. **Pre-Migration Diagnostics** (`checker.check_problematic_objects()` on **SOURCE**)
3. **Replication Parameters Check** (`checker.check_replication_params()` on **SOURCE + DEST**)
4. **Schema Migration** (`migrator.step4_migrate_schema()` on **SOURCE → DEST**)
5. **Setup Publication** (`migrator.step5_setup_source()` on **SOURCE**)
6. **Setup Subscription** (`migrator.step6_setup_destination()` on **DEST**)
7. **Initial Data Sync Wait** (`migrator.wait_for_sync()` polling **DEST**)
8. **Object Audit** (`validator.audit_objects()` on **SOURCE + DEST**)
9. **Row Parity Check** (`validator.compare_row_counts()` on **SOURCE + DEST**)

### B. Post Migration (`post-migration`)

1. **Connectivity Check** (`checker.check_connectivity()` on **SOURCE + DEST**)
2. **Cleanup Replication** (`migrator.step12_terminate_replication()` on **DEST + SOURCE**)
3. **Refresh Materialized Views** (`post_sync.refresh_materialized_views()` on **DEST**)
4. **Sync Sequences** (`post_sync.sync_sequences()` on **SOURCE → DEST**)
5. **Enable Triggers** (`post_sync.enable_triggers()` on **DEST**)
6. **Object Audit** (`validator.audit_objects()` on **SOURCE + DEST**)
7. **Row Parity Check** (`validator.compare_row_counts()` on **SOURCE + DEST**)

A timestamped HTML report is generated at the completion of *both* commands. If any step raises a fatal exception, a partial error report is written instead.

**Example output directory**:

```text
RESULTS/
└── 20260329_221400/
    ├── pg_migrator.log
    └── migration_report.html
```

**Dry-run mode**: Use `--dry-run` to preview the sequence without executing any step:

```bash
python pg_migrator.py --dry-run init-replication
```

---

## 9. Output Artifacts

| Artifact | Location | Description |
| --- | --- | --- |
| `pg_migrator.log` | `RESULTS/<timestamp>/` (pipeline) or project root (TUI) | Full structured log of all SQL and shell commands with timestamps |
| `migration_report.html` | `RESULTS/<timestamp>/` | Self-contained, audit-ready HTML report of every step |
| `unit_tests.html` | `RESULTS/<timestamp>/` | Generated by `make test-report`; pytest HTML output |

The HTML report contains, for each step:

- Status (OK / FAIL / ERROR)
- Human-readable summary message
- Exact shell and SQL commands executed
- Raw command outputs for independent verification

---

## 10. Building a Standalone Executable

The `make build` target uses [PyInstaller](https://pyinstaller.org/) to package the entire migration tool — including all Python dependencies — into a **single self-contained binary**. The resulting file can be copied to any Linux machine without requiring a Python installation or a virtual environment.

### Build

```bash
make build
```

This command:

1. Creates (or reuses) the `venv/` virtual environment and installs all dependencies plus `pyinstaller`.
2. Runs PyInstaller in `--onefile` mode, bundling:
   - `pg_migrator.py` — the CLI entry point
   - `src/` — all migration modules (`migrator.py`, `main.py`, `checker.py`, `post_sync.py`, `validation.py`, …)
   - `config_migrator.sample.ini` — the sample configuration template
3. Writes the executable to **`dist/pg_migrator`**.

### Deployment

After a successful build, deploy to a target host:

```bash
# Copy the binary and a configuration file
scp dist/pg_migrator  ops@target:/usr/local/bin/pg_migrator
scp config_migrator.sample.ini  ops@target:/etc/pg_migrator/config_migrator.ini

# Edit the config on the target
ssh ops@target
vi /etc/pg_migrator/config_migrator.ini

# Run using an explicit config path
pg_migrator --config /etc/pg_migrator/config_migrator.ini init-replication
```

> **Note**: `pg_dump` and `psql` are **not** bundled — they are called as external processes and must be installed on the target machine (any PostgreSQL client package ≥ v10).

### Directory layout after build

```text
.
├── dist/
│   └── pg_migrator          ← standalone binary (~50–80 MB)
├── build/                   ← PyInstaller work directory (safe to delete)
└── pg_migrator.spec         ← generated PyInstaller spec (safe to delete)
```

### Cleaning build artefacts

```bash
make build-clean   # removes build/ dist/ and pg_migrator.spec
make clean         # also includes build-clean, plus logs and __pycache__
```

### Limitations

| Limitation | Detail |
| --- | --- |
| Linux only | The binary is platform-specific. Build on Linux to target Linux; macOS and Windows require separate builds. |
| `config_migrator.ini` not embedded | The live configuration file is read at runtime from `--config` (default: `./config_migrator.ini`). It must be provided alongside the binary. |
| `pg_dump` / `psql` required | PostgreSQL client tools must be installed separately on the target host. |
| Binary size | The binary embeds the Python interpreter and all dependencies; expect ~50–80 MB. |

---

[Return to Documentation Index](README.md)
