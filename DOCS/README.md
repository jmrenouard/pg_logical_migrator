# Documentation Hub

Welcome to the **pg_logical_migrator** documentation suite. This repository is organized to provide deep technical insights into our 17-step migration architecture and operational best practices.

### 🏗️ Architecture & Concepts
- **[CONCEPTS.md](CONCEPTS.md)**: Core principles of logical replication and our design philosophy.
- **[CODEBASE.md](CODEBASE.md)**: Technical overview of the module structure, class responsibilities, and internal APIs.
- **[WORKFLOW.md](WORKFLOW.md)**: Detailed breakdown of the standardized 17-step sequence with failure recovery strategies.

### ⚙️ Configuration & Setup
- **[CONFIGURATION.md](CONFIGURATION.md)**: Exhaustive reference for `config_migrator.ini` and required PostgreSQL parameters.
- **[DOCKER.md](DOCKER.md)**: Guide for containerized deployment, network optimization, and environment parity.

### 🛡️ Operations & Safety
- **[VALIDATION.md](VALIDATION.md)**: Checklists and methodologies for structural and data parity verification.
- **[LIMITATIONS.md](LIMITATIONS.md)**: Critical known constraints (PK requirements, LOB handling, DDL restrictions).
- **[LIFECYCLE.md](LIFECYCLE.md)**: Maintenance, upgrades, and rollback procedures.

### 🛠️ Developer Resources
- **[TOOLS.md](TOOLS.md)**: Guide for extending the tool, internal utilities, and local development setup.
- **[TESTING.md](TESTING.md)**: Complete test infrastructure reference — unit tests (279 tests, 96% coverage), GitHub Actions workflow tests, packaging validation, and CI/CD pipeline documentation.

---

### 🚀 Quick Links
- **[Root README](../README.md)**: Project overview, Demo, and Quickstart.
- **[HOWTO.md](../HOWTO.md)**: Step-by-step tutorial for your first migration.
- **[CONTRIBUTING.md](../CONTRIBUTING.md)**: Workflow for community contributions.
