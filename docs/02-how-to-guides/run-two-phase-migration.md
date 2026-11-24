# How to Run a Two-Phase Migration

Use this procedure to migrate a PostgreSQL database with `init-replication` and `post-migration`.

## Prerequisites

- Confirm Python 3.9 or newer is installed.
- Confirm `pg_dump` and `psql` client tools are installed on the host.
- Confirm source PostgreSQL uses `wal_level = logical`.
- Create a valid INI configuration file (`config_migrator.ini`).

NOTE: To check flags and defaults, see [CLI Reference](../03-reference/cli-commands-and-configuration.md). To read design details, see [Lifecycle Explanation](../04-explanation/architecture-and-replication-lifecycle.md).

## Procedure

### Phase 1: Run Pre-Flight Checks

1. Run connectivity validation on both database servers:

```bash
python pg_migrator.py check -c config_migrator.ini
```

2. Run source object diagnostics:

```bash
python pg_migrator.py diagnose -c config_migrator.ini
```

3. Verify replication parameters on both servers:

```bash
python pg_migrator.py params -c config_migrator.ini
```

If parameters fail, update `postgresql.conf` and restart PostgreSQL before Phase 2.

### Phase 2: Initialize Logical Replication

1. Preview the initialization steps in dry-run mode:

```bash
python pg_migrator.py init-replication -c config_migrator.ini --dry-run
```

CAUTION: The `--drop-dest` option deletes and recreates the destination database. Do not use `--drop-dest` on shared production databases unless you accept full replacement.

2. Start schema deployment and logical replication:

```bash
python pg_migrator.py init-replication -c config_migrator.ini --wait
```

NOTE: Omit `--wait` to return control immediately during large initial copies.

### Phase 3: Finalize Cutover

WARNING: Stop writes on the source database before cutover to prevent split-brain data loss. Do not execute `post-migration` while applications still write to the source database.

1. Set source applications to read-only mode or stop client traffic.
2. Wait until replication lag reaches zero:

```bash
python pg_migrator.py wait-sync -c config_migrator.ini
```

3. Run the finalization pipeline:

```bash
python pg_migrator.py post-migration -c config_migrator.ini
```

## Validation

Verify that object counts and table row counts match across both servers:

```bash
python pg_migrator.py audit-objects -c config_migrator.ini
python pg_migrator.py validate-rows -c config_migrator.ini
```

Open the latest `RESULTS/<timestamp>/report_post.html` file and confirm zero `FAIL` or `ERROR` rows.

## Rollback

If application checks fail after cutover, configure reverse replication before you direct traffic back to the source:

```bash
python pg_migrator.py setup-reverse -c config_migrator.ini
```

Keep client writes on the new database until reverse sync catches up.

If migration aborts before cutover, remove replication objects from both clusters:

```bash
python pg_migrator.py cleanup -c config_migrator.ini
```
