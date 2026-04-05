![pg_logical_migrator](../pg_logical_migrator.jpg)

# Project Milestones

## Milestone 1: Foundation & Testbed (M1) — ✅ COMPLETED

- [x] Initialized Python environment.
- [x] Docker orchestration for PG16 and PG17.
- [x] Pagila dataset loading.
- [x] Basic TUI structure.

## Milestone 2: Diagnostics (M2) — ✅ COMPLETED

- [x] Step 1: Connectivity check.
- [x] Step 2: Problematic elements detection (LO, PK, Sequences).
- [x] Step 3: Parameter validation (`wal_level`, etc.).

## Milestone 3: Schema & Replication (M3) — ✅ COMPLETED

- [x] Step 4: Schema migration (`pg_dump -s`).
- [x] Step 5: Source Publication/Slot creation.
- [x] Step 6: Destination Subscription creation.

## Milestone 4: Advanced Sync (M4) — ✅ COMPLETED

- [x] Step 7: Replication Monitoring (Watch).
- [x] Step 8: Materialized Views Refresh.
- [x] Step 9: Sequence Synchronization (Fetch source values).
- [x] Step 10: Sequence Activation (Apply to destination).
- [x] Step 11: Trigger Activation.

## Milestone 5: Finalization & Validation (M5) — ✅ COMPLETED

- [x] Step 12: Replication Termination (Cleanup).
- [x] Step 13: Object Audit (Tables, Views, Indexes, Sequences, Functions).
- [x] Step 14: Data Validation (Row count parity comparison).

## Milestone 6: UX & Readiness (M6) — ✅ COMPLETED

- [x] Execution report in HTML with premium styling.
- [x] Detailed Execution Logs (commands + outputs) in reports.
- [x] Automated mode implementation (`--auto`) chaining all 14 steps.
- [x] CLI polish and documentation.
- [x] Makefile orchestration (`make test-report`, `make env-up`, etc.).
- [x] Unit tests for all core modules.
- [x] E2E integration tests with Pagila dataset.
- [x] Timestamped results management in `RESULTS/`.
