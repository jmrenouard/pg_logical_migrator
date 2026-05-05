# Design: E2E TUI Monkey Migration Test

## Overview
This test performs a full migration using the TUI of `pg_logical_migrator` while injecting random "monkey" interactions to ensure stability and responsiveness under stress.

## Goals
- Verify that the TUI can successfully drive a real migration using the `INIT` and `POST` automation pipelines.
- Ensure the TUI does not crash or deadlock when bombarded with random inputs during asynchronous operations.
- Confirm data integrity at the end of the migration.

## Test Environment
- **Source Database:** PostgreSQL 16 (localhost:5432)
- **Target Database:** PostgreSQL 17 (localhost:5433)
- **Data:** Pre-loaded via `test_env/setup_pagila.sh`.

## Implementation Strategy

### 1. Monkey Stressor
A function `monkey_stress` will be called at regular intervals. It will:
- Press random keys (`tab`, `enter`, `up`, `down`, `space`).
- Click random buttons.
- Switch between tabs (`Prepare`, `Replicate`, `Finalize`, `Audit`, `AUTOMATION`, `Config Gen`, `SQL Shell`).
- Type into focused or random `Input` widgets.

### 2. Migration Flow
- **Step 1: Cleanup.** Click "Drop Dest" in the "Prepare" tab to ensure a clean slate.
- **Step 2: Init Pipeline.** 
    - Switch to "AUTOMATION" tab.
    - Click "INIT PIPELINE".
    - Wait for completion while stressing the UI.
- **Step 3: Post Pipeline.**
    - Click "POST PIPELINE".
    - Wait for completion while stressing the UI.

### 3. Verification
- Use `psycopg2` or `PostgresClient` to check:
    - Table count in `public` schema on target.
    - Row count for a sample table (e.g., `actor`).
    - Existence of materialized views or sequences if applicable.

## Reliability
- Use `pilot.wait_for_scheduled_tasks()` and custom polling with `pilot.pause()` to check the UI state.
- Check `Static` widget content or `ListView` history for success messages.

## File Location
`tests/e2e/test_tui_monkey_migration.py`
