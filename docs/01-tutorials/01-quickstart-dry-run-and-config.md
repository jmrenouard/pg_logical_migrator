# Tutorial 1: Config Generation and Safe Dry-Run Previews

In this tutorial, we explore the **pg_logical_migrator** CLI safely without needing a running PostgreSQL cluster. By the end, you will generate a configuration file, inspect command help, and preview both automated pipelines in `--dry-run` mode.

## Prerequisites

- Python 3.9 or newer with dependencies installed (`pip install -r requirements.txt`) or access to the Docker image.
- Note for Linux/macOS shells: `src/cli/wizard.py` uses Python's `readline` module (`pg_migrator.py --help` runs natively on Linux/macOS and inside Docker/WSL).

## Step 1: Verify CLI Installation and Version

Check the installed CLI version and top-level help:

```bash
python pg_migrator.py --version
python pg_migrator.py --help
```

Expected version output matches the package release:

```text
pg_migrator.py 1.4.1
```

## Step 2: Generate a Configuration File

Create a clean starting configuration file using `generate-config`:

```bash
python pg_migrator.py generate-config --output /tmp/tutorial_migrator.ini
```

Inspect the generated file. It defines three core sections:

```ini
[source]
host = localhost
port = 5432
user = postgres
password = secret
database = source_db

[destination]
host = localhost
port = 5433
user = postgres
password = secret
database = dest_db

[replication]
publication_name = migrator_pub
subscription_name = migrator_sub
target_schema = public
loglevel = INFO
log_file = pg_migrator.log
```

## Step 3: Preview `init-replication` in Dry-Run Mode

Run `init-replication` with `-n` / `--dry-run` pointing to your tutorial config and a temporary results directory:

```bash
python pg_migrator.py init-replication -c /tmp/tutorial_migrator.ini --results-dir /tmp/tutorial_results --dry-run
```

Notice that `--dry-run` executes zero SQL statements. It prints the 9 planned steps in the initialization sequence (`1`, `2`, `3`, `4`, `5`, `6`, wait `--sync-delay`, `14`, `15`):

```text
  Mode        : DRY-RUN (no changes)
  [DRY-RUN] Step  1 : Connectivity Check
  [DRY-RUN] Step  2 : Pre-Migration Diagnostics
  [DRY-RUN] Step  3 : Replication Parameters Check
  [DRY-RUN] Step  4 : Schema Migration (Pre-Data)
  [DRY-RUN] Step  5 : Create Publication
  [DRY-RUN] Step  6 : Create Subscription
  [DRY-RUN] Step -- : Wait 3600s for initial sync
  [DRY-RUN] Step 14 : Object Audit
  [DRY-RUN] Step 15 : Row Parity Check
  No changes were made.
```

## Step 4: Preview `post-migration` in Dry-Run Mode

Preview the cutover pipeline without modifying databases:

```bash
python pg_migrator.py post-migration -c /tmp/tutorial_migrator.ini --results-dir /tmp/tutorial_results --dry-run
```

```text
  Mode        : DRY-RUN (no changes)
  [DRY-RUN] Step  1 : Connectivity Check
  [DRY-RUN] Step 10 : Terminate Replication & Schema Post-Data
  [DRY-RUN] Step 11 : Large Object Sync
  [DRY-RUN] Step  8 : Refresh Materialized Views
  [DRY-RUN] Step  9 : Sync Sequences
  [DRY-RUN] Step 12 : Enable Triggers
  [DRY-RUN] Step 13 : Reassign Ownership
  [DRY-RUN] Step 14 : Object Audit
  [DRY-RUN] Step 15 : Row Parity Check
  No changes were made.
```

## Next Steps

- Continue to [Tutorial 2: Interactive Wizard and Two-Phase Pagila Pipeline](02-interactive-wizard-and-two-phase-pipeline.md) to run live Docker migrations.
- Browse all 27 subcommands and INI options in [CLI Commands and Configuration Reference](../03-reference/cli-commands-and-configuration.md).
