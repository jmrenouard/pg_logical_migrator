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
graph LR
    subgraph UI [User Interfaces]
        CLI([fa:fa-terminal CLI]):::ui
        TUI([fa:fa-desktop TUI]):::ui
    end

    subgraph Engine [Migration Engine]
        direction TB
        CMD{fa:fa-cog Orchestrator}:::core
        
        subgraph Logic [Migration Steps]
            direction LR
            CHK(fa:fa-clipboard-check Checker)
            MIG(fa:fa-exchange-alt Migrator)
            PSY(fa:fa-sync Post-Sync)
            VAL(fa:fa-shield-alt Validation)
        end
        
        RPT(fa:fa-file-alt HTML Report):::util
    end

    subgraph Data [Infrastructure]
        SRC[(fa:fa-database Source DB)]:::db
        DST[(fa:fa-database Target DB)]:::db
    end

    %% Flow
    CLI & TUI --> CMD
    CMD --> Logic
    Logic --> SRC
    Logic --> DST
    Logic -.-> RPT

    %% Styling
    classDef ui fill:#e1f5fe,stroke:#01579b,stroke-width:2px,color:#01579b
    classDef core fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100
    classDef logic fill:#f1f8e9,stroke:#33691e,stroke-width:1px,color:#33691e
    classDef db fill:#eceff1,stroke:#455a64,stroke-width:2px,color:#455a64
    classDef util fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1px,color:#7b1fa2
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

## 🤝 Contributing

Contributions are welcome! Whether it's reporting a bug, suggesting a feature, or submitting a pull request, your help is appreciated. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to get started.

---

## 🔒 Security

Security is a top priority for this project. If you discover any security-related issues, please follow the guidelines in our [SECURITY.md](SECURITY.md) to report them responsibly.

---

## 📬 Contact Me

| Channel | Link |
| :--- | :--- |
| 🌐 Website | [www.jmrenouard.fr](https://www.jmrenouard.fr) |
| 💼 LinkedIn | [jmrenouard](https://www.linkedin.com/in/jmrenouard) |
| 🐦 X (Twitter) | [@jmrenouard](https://x.com/jmrenouard) |
| 🐙 GitHub | [jmrenouard](https://github.com/jmrenouard) |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
