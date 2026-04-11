# HOWTO: Testing pg_logical_migrator

This guide explains how to test the `pg_logical_migrator` in various modes, from the isolated test environment to full production-like pipelines.

---

## 1. Prerequisites

- **Docker & Docker Compose**: For running the test databases.
- **Python 3.10+**: With a virtual environment.
- **PostgreSQL Client Tools**: `pg_dump` and `psql` must be in your PATH.

---

## 2. Setting Up the Test Environment

Before running any tests (except unit tests), you must start the Docker-based PostgreSQL environment.

```bash
# Start PG 16 (Source) and PG 17 (Target) containers
# This also initializes the 'pagila' dataset and extra test scenarios
make env-up
```

This command creates:
- **Source DB**: `localhost:5432` (user: postgres, pass: secret, db: test_migration)
- **Target DB**: `localhost:5433` (user: postgres, pass: secret, db: test_migration)

---

## 3. Execution Modes

### A. Automated Pipeline (CLI)
This is the recommended way for non-interactive migrations or CI/CD integration. It is split into two phases.

**Phase 1: Initialize Replication**
```bash
PYTHONPATH=. venv/bin/python pg_migrator.py init-replication --drop-dest
```
- Performs diagnostics and parameter checks.
- Migrates schema (pre-data).
- Sets up Publication and Subscription.
- **Result**: Replication is active and data is syncing.

**Phase 2: Finalize Migration**
```bash
PYTHONPATH=. venv/bin/python pg_migrator.py post-migration
```
- Stops replication.
- Migrates remaining schema (post-data: indexes, foreign keys).
- Syncs sequences and refreshes materialized views.
- Reassigns object ownership.
- Performs final validation.

### B. Interactive Terminal UI (TUI)
For supervised, step-by-step migrations with a real-time dashboard.

```bash
PYTHONPATH=. venv/bin/python pg_migrator.py tui
```
- Use the sidebar buttons to run steps individually.
- Enable **"Use Stats for Counts"** for faster validation on large tables.
- Use the **"Initial Copy Progress"** button to monitor data sync in real-time.

### C. Manual Step-by-Step (CLI)
You can run any of the 14 steps individually for granular control.

```bash
# Example: Just run diagnostics
PYTHONPATH=. venv/bin/python pg_migrator.py diagnose

# Example: Check replication progress (Bytes + Tables)
PYTHONPATH=. venv/bin/python pg_migrator.py repl-progress

# Example: Fast row count validation
PYTHONPATH=. venv/bin/python pg_migrator.py validate-rows --use-stats
```

---

## 4. Testing Multi-Schema Support

To test the migration of all schemas or specific ones:

1. Edit `config_migrator.ini`.
2. Change `target_schema`:
   - `target_schema = public` (Default)
   - `target_schema = all` (Migrates every user schema)
   - `target_schema = public, test_schema` (Comma-separated list)
3. Run `init-replication`.

---

## 5. Automated Test Suite

We use `pytest` for internal validation.

```bash
# Run everything (Unit + Integration + E2E)
make test-all

# Run only unit tests (Mocks, no DB required)
make test-unit

# Run integration tests (Requires docker env-up)
make test-integration

# Run full End-to-End test
make test-e2e
```

---

## 6. Monitoring & Reports

Every run (TUI or Pipeline) generates artifacts in the `RESULTS/` directory:
- **`pg_migrator.log`**: Detailed execution log.
- **`report_init.html`**: Visual audit report for the initialization phase.
- **`report_post.html`**: Visual audit report for the finalization phase.

Open the HTML files in any browser to see every command executed and its raw output.
