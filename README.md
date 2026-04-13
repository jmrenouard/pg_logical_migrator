![pg_logical_migrator](pg_logical_migrator.jpg)

# pg_logical_migrator

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v10+-blue.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/jmrenouard/pg_logical_migrator?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/jmrenouard/pg_logical_migrator)
[![GitHub Container Registry](https://img.shields.io/badge/GHCR-jmrenouard%2Fpg__logical__migrator-blue?logo=github)](https://github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator)

**pg_logical_migrator** is a Python tool designed to simplify and automate PostgreSQL database migrations using **logical replication**. It provides a feature-rich CLI (`pg_migrator.py`) with individual step commands, a full-screen Terminal UI (TUI) for supervised migrations, and a multi-phase automated pipeline for integration.

---

## Key Features

- **Standardized 16-Step Workflow**: A robust, sequential process ensuring data integrity and minimal downtime.
- **Guided TUI Interface**: A step-by-step terminal dashboard (built with [Textual](https://textual.textualize.io/)) to supervise the migration process interactively.
- **Automated Pipelines**: One-command migration via `init-replication` and `post-migration` for non-interactive environments.
- **Deep Diagnostics**: Pre-flight checks for Primary Key coverage, Large Objects (LOBs), Identity columns, and unowned sequences.
- **Size Analysis**: Real-time database and table size breakdown (Data vs. Index) with % DB footprint.
- **Replication Progress**: Real-time byte-level and table-count tracking of the data synchronization.
- **Rollback Capability**: Optional reverse replication setup (`setup-reverse`) to sync changes back to the source after migration.
- **Validation Suite**: Structural parity audit and fast row count comparison (using statistics or exact count).
- **Audit-Ready HTML Reports**: Visual reports containing every executed command and its raw output.

---

## Architecture at a Glance

```text
pg_migrator.py              # CLI entry point with 16 subcommands
src/
├── config.py               # Multi-schema INI configuration management
├── db.py                   # psycopg v3 connection wrapper & pretty-size utilities
├── checker.py              # Steps 1–3: Connectivity, diagnostics, size analysis
├── migrator.py             # Steps 4–7, 12, 16: Schema, pub/sub, sync wait, cleanup
├── post_sync.py            # Steps 8–11, 13: MatViews, sequences, triggers, ownership
├── validation.py           # Steps 14–15: Object audit, row parity (stats supported)
├── report_generator.py     # HTML report engine
└── tui.py                  # TUI Application logic (Textual + Rich)
```

---

## Installation

### Option A — Docker (Recommended)

The Docker image ships with all dependencies pre-installed and requires **zero local setup**.

```bash
# Pull from Docker Hub
docker pull jmrenouard/pg_logical_migrator:latest

# Or from GitHub Container Registry (GHCR)
docker pull ghcr.io/jmrenouard/pg_logical_migrator:latest
```

| Registry | Link |
| :--- | :--- |
| **Docker Hub** | [hub.docker.com/r/jmrenouard/pg_logical_migrator](https://hub.docker.com/r/jmrenouard/pg_logical_migrator) |
| **GHCR** | [github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator](https://github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator) |

### Option B — Standalone Binaries

Native standalone binaries for **Linux (amd64)**, **Windows (exe)**, and **macOS (arm64)** are available on the [Releases Page](https://github.com/jmrenouard/pg_logical_migrator/releases).

### Option C — OS Packages (DEB / RPM)

Native packages for **Debian/Ubuntu** (`.deb`) and **RHEL/CentOS/Fedora** (`.rpm`) are provided for easy system-wide installation.

### Option D — Python Package (pip)

Install the wheel directly or from source:

```bash
# From local wheel
pip install pg_logical_migrator-1.3.0-py3-none-any.whl

# From source
git clone https://github.com/jmrenouard/pg_logical_migrator.git
cd pg_logical_migrator
make install
```

---

## Quick Start

1. **Configure**: `cp config_migrator.sample.ini config_migrator.ini`
2. **Diagnose**: `python pg_migrator.py diagnose`
3. **Replicate**: `python pg_migrator.py init-replication --drop-dest`
4. **Finalize**: `python pg_migrator.py post-migration`

---

## CLI Reference (17-Step Workflow)

| Command | Step | Description |
| :--- | :---: | :--- |
| `check` | 1 | Test connectivity |
| `diagnose` | 2 | Pre-migration diagnostics & size audit |
| `params` | 3 | Verify replication parameters |
| `migrate-schema-pre-data` | 4 | Copy schema structure (pre-data) |
| `setup-pub` | 5 | Create publication on source |
| `setup-sub` | 6 | Create subscription on destination |
| `repl-status` | 7 | Show replication status (Forward/Reverse) |
| `repl-progress` | — | Real-time byte-level copy progress |
| `refresh-matviews` | 8 | Refresh materialized views |
| `sync-sequences` | 9/10 | Synchronize sequence values |
| `enable-triggers` | 11 | Enable triggers on destination |
| `migrate-schema-post-data` | 12 | Copy indexes and constraints (post-data) |
| `reassign-owner` | 13 | Set correct object ownership |
| `audit-objects` | 14 | Compare object counts |
| `validate-rows` | 15 | Compare row counts (`--use-stats` available) |
| `cleanup` | 16 | Stop replication & free resources |
| `setup-reverse` | 17 | (Optional) Setup reverse sync for rollback |

---

## Documentation Index

| Document | Description |
| :--- | :--- |
| **[DOCS/WORKFLOW.md](DOCS/WORKFLOW.md)** | **Standardized 16-Step Sequence** with Mermaid diagrams |
| **[DOCS/CODEBASE.md](DOCS/CODEBASE.md)** | Technical reference and module responsibilities |
| **[HOWTO.md](HOWTO.md)** | Comprehensive testing and execution guide |
| **[DOCS/CONFIGURATION.md](DOCS/CONFIGURATION.md)** | `config_migrator.ini` reference and PG parameters |
| **[DOCS/DOCKER.md](DOCS/DOCKER.md)** | Running within isolated Docker containers |
| **[DOCS/VALIDATION.md](DOCS/VALIDATION.md)** | Checklists for schema and data verification |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
