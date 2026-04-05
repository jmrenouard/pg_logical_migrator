![pg_logical_migrator](pg_logical_migrator.jpg)

# pg_logical_migrator

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v10+-blue.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/jmrenouard/pg_logical_migrator?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/jmrenouard/pg_logical_migrator)
[![GitHub Container Registry](https://img.shields.io/badge/GHCR-jmrenouard%2Fpg__logical__migrator-blue?logo=github)](https://github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator)

**pg_logical_migrator** is a Python tool designed to simplify and automate PostgreSQL database migrations using **logical replication**. It provides a feature-rich CLI (`pg_migrator.py`) with individual step commands, a full-screen Terminal UI (TUI) for supervised migrations, and an automated mode for pipeline integration.

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
pg_migrator.py              # CLI entry point with all commands & options
src/
├── config.py               # INI file reader
├── db.py                   # PostgreSQL connection wrapper (psycopg v3)
├── checker.py              # Steps 1–3: Connectivity, diagnostics, param checks
├── migrator.py             # Steps 4–7, 12: Schema, pub/sub setup, cleanup
├── post_sync.py            # Steps 8–11: MatViews, sequences, triggers
├── validation.py           # Steps 13–14: Object audit, row parity
├── report_generator.py     # HTML report engine
└── main.py                 # TUI App (Textual)
```

---

## Installation

There are several ways to install and run `pg_logical_migrator`. Choose the method that best suits your environment.

### Option A — Docker (recommended)

The Docker image ships with all dependencies pre-installed (Python, `psycopg`, `pg_dump`, `psql`) and requires **zero local setup**.

```bash
# Pull the latest stable image from Docker Hub
docker pull jmrenouard/pg_logical_migrator:latest

# Or from GitHub Container Registry (GHCR)
docker pull ghcr.io/jmrenouard/pg_logical_migrator:latest

# Pull a specific version
docker pull jmrenouard/pg_logical_migrator:1.0.0
```

Run a command directly via Docker:

```bash
docker run -it --rm \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  -v $(pwd)/RESULTS:/app/RESULTS \
  jmrenouard/pg_logical_migrator check
```

| Registry | Image | Link |
| :--- | :--- | :--- |
| **Docker Hub** | `jmrenouard/pg_logical_migrator` | [hub.docker.com/r/jmrenouard/pg_logical_migrator](https://hub.docker.com/r/jmrenouard/pg_logical_migrator) |
| **GHCR** | `ghcr.io/jmrenouard/pg_logical_migrator` | [github.com/…/pkgs/container/pg_logical_migrator](https://github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator) |

> Full Docker usage guide: **[DOCS/DOCKER.md](DOCS/DOCKER.md)**

### Option B — Standalone Binary (PyInstaller)

A pre-built Linux `amd64` binary is attached to every [GitHub Release](https://github.com/jmrenouard/pg_logical_migrator/releases). It bundles the Python runtime and all dependencies into a single executable — **no Python installation required**.

```bash
# Download the binary from the latest release
curl -Lo pg_migrator \
  "https://github.com/jmrenouard/pg_logical_migrator/releases/latest/download/pg_migrator"

chmod +x pg_migrator
./pg_migrator --help
```

> **Note:** The host still needs `pg_dump` and `psql` binaries (from the `postgresql-client` package) to perform schema migration.

### Option C — Install from Source (pip)

This is the standard developer setup. It requires **Python 3.10+** and the PostgreSQL client tools.

```bash
# 1. Clone the repository
git clone https://github.com/jmrenouard/pg_logical_migrator.git
cd pg_logical_migrator

# 2. Create a virtual environment and install dependencies
make install

# 3. Verify
venv/bin/python pg_migrator.py --help
```

**Manual install (without Make):**

```bash
git clone https://github.com/jmrenouard/pg_logical_migrator.git
cd pg_logical_migrator

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify
python pg_migrator.py --help
```

### Option D — Build Your Own Binary Locally

You can build the standalone executable yourself using PyInstaller:

```bash
make build        # produces dist/pg_migrator
./dist/pg_migrator --help
```

Or build a local Docker image:

```bash
docker build -t pg_logical_migrator .
docker run --rm pg_logical_migrator --help
```

### Prerequisites Summary

| Method | Python | pg_dump / psql | Docker |
| :--- | :---: | :---: | :---: |
| Docker | — | — | ✅ |
| Standalone binary | — | ✅ | — |
| From source (pip) | ✅ 3.10+ | ✅ | — |
| Local build | ✅ 3.10+ | ✅ | Optional |

---

## Quick Start

### 1. Configuration

Copy and edit the sample configuration file:

```bash
cp config_migrator.sample.ini config_migrator.ini
```

Edit the `[source]`, `[destination]`, and `[replication]` sections with your connection details.
> The source PostgreSQL user must have `REPLICATION` privilege. See [Configuration Guide](DOCS/CONFIGURATION.md).

### 3. Run

```bash
# Check connectivity first
python pg_migrator.py check

# Pre-flight diagnostics
python pg_migrator.py diagnose

# Dry-run the pipeline (simulate steps 1-3)
python pg_migrator.py diagnose

# Initialize replication (and drop existing DB)
python pg_migrator.py init-replication --drop-dest

# Finalize migration
python pg_migrator.py post-migration

# Interactive TUI (supervised mode)
python pg_migrator.py tui

# Or use the Makefile shortcut:
make run-pipeline
```

---

## CLI Quick Reference

```bash
python pg_migrator.py [OPTIONS] <command>
```

| Command | Step | Description |
| :--- | :--- | :--- |
| `check` | 1 | Test source/destination connectivity |
| `diagnose` | 2 | Pre-migration diagnostics (PK, LOBs, sequences) |
| `params` | 3 | Verify replication parameters |
| `apply-params` | 3 | Apply required replication parameters to target |
| `migrate-schema` | 4 | Copy schema (`pg_dump -s \| psql`) |
| `setup-pub` | 5 | Create publication on source |
| `setup-sub` | 6 | Create subscription on destination |
| `repl-status` | 7 | Show replication status |
| `sync-sequences` | 8/9 | Synchronize sequence values |
| `enable-triggers` | 10 | Enable triggers on destination |
| `disable-triggers` | — | Disable triggers (utility) |
| `refresh-matviews` | 11 | Refresh materialized views |
| `audit-objects` | 13 | Compare object counts |
| `validate-rows` | 14 | Compare row counts per table |
| `cleanup` | 12 | Drop sub/pub/slot (destructive) |
| `init-replication` | 1-7 | Initialize replication and sync schema |
| `post-migration` | 8-14 | Finalize migration and cleanup |
| `tui` | — | Interactive Terminal UI |
| `generate-config` | — | Generate sample config file |

**Global options**: `--config`, `--dry-run`, `--loglevel`, `--log-file`, `--results-dir`, `--sync-delay`, `--version`

Full CLI documentation: **[DOCS/TOOLS.md](DOCS/TOOLS.md)**

---

## Documentation

| Document | Description |
| :--- | :--- |
| **[DOCS/TOOLS.md](DOCS/TOOLS.md)** | CLI commands, global options, Makefile targets, TUI walkthrough, automated mode |
| **[DOCS/WORKFLOW.md](DOCS/WORKFLOW.md)** | Deep dive into every one of the 14 migration steps with module references |
| **[DOCS/CONCEPTS.md](DOCS/CONCEPTS.md)** | PostgreSQL logical replication: publish/subscribe, WAL, replication slots |
| **[DOCS/CONFIGURATION.md](DOCS/CONFIGURATION.md)** | Required PostgreSQL server parameters and `config_migrator.ini` reference |
| **[DOCS/DOCKER.md](DOCS/DOCKER.md)** | Building and running the application within an isolated Docker container |
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
