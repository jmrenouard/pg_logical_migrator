# pg_logical_migrator: Comprehensive Guide & Technical Reference

`pg_logical_migrator` is a high-performance, automated tool designed to migrate PostgreSQL databases with minimal downtime using native logical replication. It handles complex object types, provides real-time monitoring, and ensures data integrity through exhaustive validation.

---

## 🚀 Quick Start (Automated Pipeline)

The tool is organized into two primary phases to manage the migration lifecycle.

### Phase 1: Initialize Replication
Sets up the infrastructure and starts data streaming.
```bash
PYTHONPATH=. venv/bin/python pg_migrator.py init-replication --drop-dest
```
- **Adaptive Strategy**: Automatically detects tables without Primary Keys and sets `REPLICA IDENTITY FULL`.
- **Dynamic Cleanup**: Use `--drop-dest` to automatically wipe the target DB and orphaned replication slots.
- **Non-Blocking**: By default, it returns control immediately after setup. Use `--wait` for a synchronous run.

### Phase 2: Finalize Migration (Cutover)
Synchronizes remaining objects and prepares the new database for application traffic.
```bash
PYTHONPATH=. venv/bin/python pg_migrator.py post-migration
```
- **Zero-Data-Loss Cutover**: Blocks until the very last WAL record is applied.
- **Complex Object Sync**: Migrates Large Objects (LOBs/OIDs) and `UNLOGGED` tables manually.
- **Integrity Restore**: Rebuilds indexes, re-enables triggers, and refreshes materialized views.

---

## 🛠️ Core Capabilities

### 1. Advanced Compatibility Handling
Postgres logical replication has native limitations. `pg_logical_migrator` solves them:
- **Large Objects (LOBs)**: Streams OID-based binary data from source to target.
- **UNLOGGED Tables**: Manually copies tables that Postgres excludes from WAL logs.
- **Tables without PK**: Automatically configures `REPLICA IDENTITY FULL` to allow updates/deletes.
- **Sequences**: Updates sequence values during cutover to prevent PK collisions on new inserts.

### 2. Multi-Target Orchestration
- **Multi-Schema**: Migrate specific schemas, a list, or `*` (all user schemas).
- **Multi-Database (Auto-Discovery)**: Use `databases = *` in your config to automatically find and migrate every database on your source cluster.
- **Container-Aware**: Specific options (`source_host`, `dest_host` in `[replication]`) allow the target DB to reach the source through internal Docker networks while you run the tool from your host.

### 3. Safety & Validation
- **Dry-Run Mode (`-n`)**: See exactly what SQL and shell commands would be executed without touching your data.
- **Fast Validation (`--use-stats`)**: Perform row-count checks on millions of rows in milliseconds using Postgres internal statistics.
- **Structural Audit**: Compares counts of tables, indexes, views, and sequences between clusters.
- **Detailed Reporting**: Generates interactive HTML reports (`RESULTS/report_init.html`) with every command executed and its result.

### 4. Monitoring & Rollback
- **Independent Monitor**: Run `pg_migrator.py repl-progress` at any time for a real-time dashboard of copy progress (bytes and tables).
- **Rollback Path (Reverse Sync)**: Use `pg_migrator.py setup-reverse` after cutover. This keeps your old source in sync with your new target, allowing an instant fail-back if needed.

---

## ⌨️ Command Reference

| Command | Description |
|:---|:---|
| `check` | Connectivity test for source and destination. |
| `diagnose` | Scan for potential issues (No PK, LOBs, Unlogged, etc.). |
| `params` | Verify mandatory Postgres settings (`wal_level`, slots, workers). |
| `migrate-schema-pre-data` | Deploy base structures (schemas, tables, types). |
| `setup-pub / setup-sub` | Manual creation of Publication and Subscription. |
| `repl-progress` | Interactive real-time copy progress monitor. |
| `refresh-matviews` | Refresh all materialized views on destination. |
| `sync-sequences` | Bring all sequence values up to date. |
| `terminate-repl` | Stop replication and deploy indexes/foreign keys. |
| `sync-lobs / sync-unlogged` | Manually migrate specialized table data. |
| `enable-triggers` | Restore application-level trigger logic. |
| `reassign-owner` | Set correct role owners for all migrated objects. |
| `audit-objects` | Verify parity of object counts (Tables, Indexes, etc.). |
| `validate-rows` | Row count parity check (Exact or Stat-based). |
| `cleanup` | Decommission all replication objects (Pubs, Subs, Slots). |
| `setup-reverse` | **Safety**: Setup rollback replication path. |
| `tui` | Launch the interactive Terminal User Interface. |

---

## 📊 Global Configuration Flags

| Flag | Effect |
|:---|:---|
| `-c, --config FILE` | Path to your configuration (Default: `config_migrator.ini`). |
| `-n, --dry-run` | Preview mode. No changes applied. |
| `-v, --verbose` | Debug mode. Prints every SQL command and output. |
| `--use-stats` | Speeds up row parity checks using internal PG stats. |
| `--results-dir DIR` | Custom location for logs and HTML reports. |
| `--loglevel LEVEL` | Set log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 🐳 Running in Docker

To start the built-in test environment (PG 16 Source → PG 17 Target):
```bash
make env-up
```
This loads the `pagila` sample database and configures special edge cases (LOBs, Unlogged, etc.) for validation.
