![pg_logical_migrator](../pg_logical_migrator.jpg)

# Project Constitution

## Core Principles

### I. Mission-Critical Reliability

The migration of production databases is a high-risk operation. Every action taken by this tool must be:

- **Verified**: Prerequisites are checked before any state change.
- **Atomic**: Each step is designed to be complete or non-damaging.
- **Recoverable**: Clear paths for replication cleanup and rollback must exist.

### II. Intuitive UX for Complex Workflows

A terminal interface should never be an obstacle. The TUI must:

- **Zones of Visibility**: Provide dedicated areas for command execution logs ("Command Output") and distilled migration findings ("Result Zone").
- **Manual Control**: Allow expert users to selectively re-run steps or override findings.
- **State Awareness**: Clearly indicate the current phase and health of the migration lifecycle.

### III. Automated QA & Visual Reporting

Features are not considered functional until they are validated against a live environment:

- **TDD Mandatory**: New check and sync logic must include unit/integration tests before implementation.
- **Visual Evidence**: Both **test cycles** and **actual migration executions** must generate HTML reports to allow stakeholders to verify readiness and results.
- **Docker-First Verification**: All features must pass on the target PostgreSQL version matrix (16 & 18).

### IV. Proactive Diagnostics & Pre-flight Reporting

Preventing failure is the primary goal of the "Prerequisite" phase:

- **Blocker Identification**: Automatically detect missing Primary Keys, unsupported data types, and mismatched parameters.
- **Detailed Audits**: Provide lists and counts of all database objects to ensure 100% schema parity BEFORE replication starts.

### V. Deep Observability & Audit Logs

Migration history is critical for post-mortem analysis and compliance:

- **Structured Logging**: All database interactions and shell calls are logged to `pg_migrator.log` with human-readable timestamps.
- **Rich Telemetry**: Provide "Watch" mode monitoring for replication lag, slots, and subscription health, with a record saved in the HTML execution report.

## Development Standards

### Technology Stack

- **Language**: Python 3.9+
- **Database**: PostgreSQL 16+ (Source), 17/18+ (Destination)
- **UI Framework**: Textual / Rich for TUI components.
- **Test Infrastructure**: Docker-based orchestration with `pagila` dataset.

### Code Quality Gates

- **Linting**: 100% pass rate on standard Python linters (Ruff/Flake8).
- **Test Coverage**: Focus on 100% coverage for the core `src/replication.py` and `src/db_checks.py`.

## Governance

This Constitution establishes the technical and philosophical boundaries for `pg_logical_migrator`.

- **Supremacy**: All architectural decisions must align with these Principles.
- **Evolution**: Amendments require documented rationale and validation against the "Mission-Critical Reliability" core principle.

**Version**: 1.1.0 | **Ratified**: 2026-03-28 | **Last Amended**: 2026-03-28
