![pg_logical_migrator](pg_logical_migrator.jpg)

# pg_logical_migrator

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v10+-blue.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/jmrenouard/pg_logical_migrator?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/jmrenouard/pg_logical_migrator)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-orange?logo=buy-me-a-coffee)](https://buymeacoffee.com/jmrenouard)

**pg_logical_migrator** is a Python-based orchestrator designed to automate PostgreSQL database migrations using **logical replication**. It provides a standardized **17-step sequential workflow**, a refactored **centralized TUI dashboard**, and automated pipelines for complex infrastructure migrations.

---

## 🎥 Lifecycle Demonstration

Watch how **pg_logical_migrator** orchestrates an end-to-end database migration, including **Large Object (LOB) synchronization** and real-time parity audits.

[![asciicast](https://asciinema.org/a/2XCuo1WYnRZZfo5o.svg)](https://asciinema.org/a/2XCuo1WYnRZZfo5o)

---

## Key Features

- **Standardized 17-Step Workflow**: A strictly defined, repeatable process ensuring maximum data integrity.
- **Refactored TUI Dashboard**: A modern, result-centric interface with action tabs and an **interactive action history**.
- **Large Object (LOB) Synchronization**: Manually migrates binary data (OIDs) and restores table references.
- **Deep Pre-flight Diagnostics**: Scans for Primary Key coverage, LOBs, and unowned sequences.
- **Replication Byte-level Tracking**: Real-time progress monitoring of the initial data copy.
- **Post-Migration Parity Audits**: Structural parity checks and exhaustive row count comparison.
- **Automated Rollback Path**: Integrated setup for reverse replication to sync changes back to the source.
- **Audit-Ready HTML Reports**: Detailed visual reports containing every executed SQL command and its output.

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

## Deployment Options

### Option A — Docker (Recommended)
The official image ships with all dependencies pre-installed. No local Python configuration is required.

```bash
docker pull jmrenouard/pg_logical_migrator:latest
```

### Option B — Local Python Setup
For local development, ensure you have Python 3.9+ and the required drivers.

```bash
git clone https://github.com/jmrenouard/pg_logical_migrator
pip install -r requirements.txt
```

---

## Quick Start (3 Steps)

### 1. Configure Connection Parameters
Create a `config_migrator.ini` file based on the provided sample. Ensure both databases are reachable and have `wal_level = logical`.

### 2. Initialize Replication
Start the initial data copy and streaming delta.
```bash
python pg_migrator.py init-replication --drop-dest
```

### 3. Finalize Cutover
Once synchronization is complete, finalize the schema, sequences, and triggers.
```bash
python pg_migrator.py post-migration
```

---

## Documentation Index

| Resource | Description |
| :--- | :--- |
| **[DOCS/WORKFLOW.md](DOCS/WORKFLOW.md)** | **Standardized 16-Step Sequence** with technical deep-dives. |
| **[DOCS/CONFIGURATION.md](DOCS/CONFIGURATION.md)** | `config_migrator.ini` reference and PG parameters. |
| **[DOCS/LIMITATIONS.md](DOCS/LIMITATIONS.md)** | Critical constraints (PK, LOBs, DDL restrictions). |
| **[DOCS/DOCKER.md](DOCS/DOCKER.md)** | Running within isolated containerized environments. |
| **[DOCS/README.md](DOCS/README.md)** | **Complete Documentation Hub**. |

---

## 🔒 Security & Support

- **Vulnerability Reporting**: Please refer to [SECURITY.md](SECURITY.md) for our responsible disclosure policy.
- **Contributions**: Guidelines for submitting PRs and bug reports are in [CONTRIBUTING.md](CONTRIBUTING.md).

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
