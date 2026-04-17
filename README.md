![pg_logical_migrator](pg_logical_migrator.jpg)

# pg_logical_migrator

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v10+-blue.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/jmrenouard/pg_logical_migrator?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/jmrenouard/pg_logical_migrator)
[![GitHub Container Registry](https://img.shields.io/badge/GHCR-jmrenouard%2Fpg__logical__migrator-blue?logo=github)](https://github.com/jmrenouard/pg_logical_migrator/pkgs/container/pg_logical_migrator)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-orange?logo=buy-me-a-coffee)](https://buymeacoffee.com/jmrenouard)

**pg_logical_migrator** is a Python tool designed to simplify and automate PostgreSQL database migrations using **logical replication**. It provides a feature-rich CLI (`pg_migrator.py`) with individual step commands, a full-screen Terminal UI (TUI) for supervised migrations, and a multi-phase automated pipeline for integration.

---

## 🎥 Démonstration

Découvrez comment **pg_logical_migrator** orchestre une migration de base de données complexe sans aucune interruption de service (zero-downtime), automatisée via nos tests de bout en bout (e2e).

[![asciicast](https://asciinema.org/a/ID.svg)](https://asciinema.org/a/ID)

*Alternativement, visualisez le processus via ce GIF de démonstration :*
![Migration Demo Placeholder](https://via.placeholder.com/800x400.png?text=Migration+Demo+GIF+Placeholder)

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

```mermaid
graph TD
    CLI[CLI pg_migrator.py] --> TUI[TUI src/tui.py]
    CLI --> CMD[Commands src/cli/commands.py]
    CMD --> CFG[Config src/config.py]
    CMD --> DB[DB src/db.py]
    CMD --> CHK[Checker src/checker.py]
    CMD --> MIG[Migrator src/migrator.py]
    CMD --> PSY[Post-Sync src/post_sync.py]
    CMD --> VAL[Validation src/validation.py]
    CMD --> RPT[Report src/report_generator.py]

    subgraph "Core Logic"
    CHK
    MIG
    PSY
    VAL
    end

    subgraph "External"
    SRC[(Source DB)]
    DST[(Dest DB)]
    end

    MIG --> SRC
    MIG --> DST
```

---

## Use Cases

- **Zero-Downtime Migration**: Migrate large databases to new infrastructure (Cloud, On-premise) while keeping the application online.
- **Major Version Upgrade**: Upgrade PostgreSQL versions (e.g., v12 to v16) with minimal interruption using logical replication.
- **Infrastructure Migration**: Move from on-premise to managed services (RDS, Cloud SQL) or between cloud providers.
- **Database Refactoring**: Change hardware or storage engines while maintaining data availability.

---

## Installation

### Option A — Docker (Recommended)

The Docker image ships with all dependencies pre-installed and requires **zero local setup**.

```bash
# Pull from Docker Hub
docker pull jmrenouard/pg_logical_migrator:latest
```

---

## Quick Start (3 steps)

```bash
cp config_migrator.sample.ini config_migrator.ini # 1. Configure your DBs
python pg_migrator.py init-replication           # 2. Start logical replication
python pg_migrator.py post-migration             # 3. Finalize and cutover
```

---

## Demo Environment

You can easily test **pg_logical_migrator** using the provided `test_env`:

1.  **Start the databases**: `cd test_env && ./setup_pagila.sh`
2.  **Run the migrator**: Use the TUI or CLI to migrate the `pagila` database from the source container to the destination container.

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

## 👨‍💻 À propos de l'auteur

Architecte Web et Expert en Bases de Données (Cassandra, MongoDB, MySQL, PostgreSQL, Redis) basé à Rennes, je suis passionné par l'univers DevDataOps. Auteur de plusieurs ouvrages techniques (éditions ENI, Eyrolles), je m'efforce de partager mon expertise pour simplifier la gestion et la migration des données à grande échelle.

| Canal | URL | Détails |
| :--- | :--- | :--- |
| 🌐 Site / Blog | [www.jmrenouard.fr](https://www.jmrenouard.fr) | Présentation, bio, contact pro |
| 💼 LinkedIn | [jmrenouard](https://www.linkedin.com/in/jmrenouard) | Profil DBA, DevDataOps |
| 🐦 X (Twitter) | [@jmrenouard](https://x.com/jmrenouard) | Tech OSS, BDD, Langages |
| 🐙 GitHub | [jmrenouard](https://github.com/jmrenouard) | Projets open source |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
