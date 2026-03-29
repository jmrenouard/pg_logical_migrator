# pg_logical_migrator

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v10+-blue.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**pg_logical_migrator** is a Python tool designed to simplify and automate PostgreSQL database migrations using **logical replication**. It provides a full-screen Terminal UI (TUI) for supervised, step-by-step migrations and an automated mode (`--auto`) for pipeline integration.

---

## Key Features

- **Guided TUI Interface**: A step-by-step terminal dashboard (built with [Textual](https://textual.textualize.io/)) to supervise the migration process interactively.
- **Automated Mode**: One-command migration via `--auto` for non-interactive pipelines.
- **Deep Diagnostics**: Pre-flight checks for Primary Key coverage, Large Objects, Identity columns, and unowned sequences.
- **Replication Parameter Audit**: Verifies `wal_level`, `max_replication_slots`, `max_wal_senders`, etc. before starting.
- **Post-Sync Automation**: Automatic refresh of materialized views, sequence synchronization, and trigger activation after initial sync.
- **Data Validation Suite**: Row count comparison (Step 14) and schema object parity audit (Step 13) for full verification.
- **Audit-Ready HTML Reports**: Self-contained HTML report containing every executed command, its raw output, and a status badge.

---

## Architecture at a Glance

```text
src/
├── config.py           # INI file reader
├── db.py               # PostgreSQL connection wrapper (psycopg v3)
├── checker.py          # Steps 1–3: Connectivity, diagnostics, param checks
├── migrator.py         # Steps 4–7, 12: Schema, pub/sub setup, cleanup
├── post_sync.py        # Steps 8–11: MatViews, sequences, triggers
├── validation.py       # Steps 13–14: Object audit, row parity
├── report_generator.py # HTML report engine
└── main.py             # TUI App + --auto orchestrator (entry point)
```

---

## Quick Start

### 1. Installation

```bash
git clone https://github.com/jmrenouard/pg_logical_migrator.git
cd pg_logical_migrator
make install
```

### 2. Configuration

Copy and edit the sample configuration file:

```bash
cp config_migrator.sample.ini config_migrator.ini
```

Edit the `[source]`, `[destination]`, and `[replication]` sections with your connection details.
> The source PostgreSQL user must have `REPLICATION` privilege. See [Configuration Guide](DOCS/CONFIGURATION.md).

### 3. Run

```bash
# Interactive TUI (supervised mode)
venv/bin/python src/main.py

# Fully automated mode (pipeline-friendly)
make run-auto
# or:
venv/bin/python src/main.py --auto --results-dir /var/reports/migration_run_1
```

---

## Documentation

| Document | Description |
| :--- | :--- |
| **[DOCS/TOOLS.md](DOCS/TOOLS.md)** | CLI flags, Makefile targets, TUI walkthrough, automated mode, output artifacts |
| **[DOCS/WORKFLOW.md](DOCS/WORKFLOW.md)** | Deep dive into every one of the 14 migration steps with module references |
| **[DOCS/CONCEPTS.md](DOCS/CONCEPTS.md)** | PostgreSQL logical replication: publish/subscribe, WAL, replication slots |
| **[DOCS/CONFIGURATION.md](DOCS/CONFIGURATION.md)** | Required PostgreSQL server parameters and `config_migrator.ini` reference |
| **[DOCS/LIFECYCLE.md](DOCS/LIFECYCLE.md)** | High-level migration phases from preparation to final cutover |
| **[DOCS/VALIDATION.md](DOCS/VALIDATION.md)** | Critical control points and schema verification checklist |
| **[DOCS/LIMITATIONS.md](DOCS/LIMITATIONS.md)** | Constraints, unsupported objects, and the row identification problem |

Full documentation index: **[DOCS/README.md](DOCS/README.md)**

---

## Testing

```bash
# Unit tests only
make test-unit

# Full test suite (requires Docker: make env-up first)
make env-up
make test-all
make env-down

# Generate timestamped HTML test + migration reports
make test-report
```

Reports are saved to `RESULTS/<timestamp>/`.

---

## Development Progress

Current status and milestones are tracked in **[PROJECT/PROGRESS.md](PROJECT/PROGRESS.md)**.
Technical specifications are in **[PROJECT/SPECIFICATIONS.md](PROJECT/SPECIFICATIONS.md)**.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
