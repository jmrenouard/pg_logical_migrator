![pg_logical_migrator](../pg_logical_migrator.jpg)

# Project Documentation Index

Welcome to the `pg_logical_migrator` project documentation. These files define the technical standards, roadmap, and requirements for a mission-critical PostgreSQL migration tool.

## 🎯 Project Status: **COMPLETED (v1.0)**

All 6 milestones and all 14 migration steps are fully implemented, tested, and verified against the Pagila dataset.

## Documentation Map

- **[CONSTITUTION.md](file:///home/jmren/GIT_REPOS/pg_logical_migrator/PROJECT/CONSTITUTION.md)**: Core principles, technical standards, and project governance.
- **[SPECIFICATIONS.md](file:///home/jmren/GIT_REPOS/pg_logical_migrator/PROJECT/SPECIFICATIONS.md)**: Technical requirements, TUI design, and reporting framework.
- **[MILESTONES.md](file:///home/jmren/GIT_REPOS/pg_logical_migrator/PROJECT/MILESTONES.md)**: High-level developmental roadmap *(all milestones completed)*.
- **[TASKS.md](file:///home/jmren/GIT_REPOS/pg_logical_migrator/PROJECT/TASKS.md)**: Granular implementation checklist *(all tasks completed)*.
- **[PROGRESS.md](file:///home/jmren/GIT_REPOS/pg_logical_migrator/PROJECT/PROGRESS.md)**: Project health and milestone completion tracker.

## Quick Start

```bash
# Setup test environment
make env-up

# Run full automated migration with detailed HTML report
make test-report

# Run unit tests
make unit-test

# Open the latest report
ls RESULTS/
```
