# pg_logical_migrator — Project Context

## Project Overview
**pg_logical_migrator** is a Python-based orchestrator designed to automate PostgreSQL database migrations using **logical replication**. It provides a standardized **17-step sequential workflow**, a refactored **centralized TUI dashboard**, and automated pipelines for complex infrastructure migrations.

### Core Technologies
- **Language**: Python 3.9+
- **Database Driver**: `psycopg` (v3)
- **UI/TUI**: `rich` and `textual`
- **Templating**: `jinja2` (for audit reports)
- **Packaging**: `pyinstaller` (for standalone binaries)

---

## 17-Step Workflow
The tool follows a strictly defined lifecycle to ensure data integrity:

### Phase 1: Preparation
1.  **Check**: Verify connectivity to source and destination.
2.  **Diagnose**: Scan for Primary Key coverage, LOBs, sequences, and unlogged tables.
3.  **Params**: Verify mandatory PostgreSQL replication parameters (`wal_level`, etc.).
4.  **Schema (Pre-data)**: Deploy schemas, tables, types, and views.

### Phase 2: Execution
5.  **Setup Publication**: Create logical publication on the source.
6.  **Setup Subscription**: Create subscription on the destination and trigger initial COPY.
7.  **Monitor Progress**: Real-time tracking of table synchronization.

### Phase 3: Finalization (Cutover)
8.  **Refresh Matviews**: Refresh materialized views on the destination.
9.  **Sync Sequences**: Synchronize sequence values from source to destination.
10. **Terminate Replication**: Stop replication and deploy indexes, FKs, and constraints.
11. **Sync LOBs & Unlogged**: Manually sync binary data (OIDs) and UNLOGGED tables.
12. **Enable Triggers**: Restore application-level triggers.
13. **Reassign Owner**: Set correct role owners for all database objects.

### Phase 4: Validation & Cleanup
14. **Audit Objects**: Structural parity check (tables, indexes, views, sequences).
15. **Validate Rows**: Exhaustive row count comparison.
16. **Cleanup**: Decommission replication objects (slots, publications, subscriptions).
17. **Setup Reverse**: (Optional) Setup reverse replication for rollback path.

---

## Getting Started

### Installation
```bash
# Clone the repository
git clone https://github.com/jmrenouard/pg_logical_migrator
cd pg_logical_migrator

# Install dependencies
pip install -r requirements.txt
```

### Configuration
Create a `config_migrator.ini` based on `config_migrator.sample.ini`.
```bash
python pg_migrator.py generate-config --output my_config.ini
```

---

## Key Commands

### Automated Pipelines
Most users will use these two commands for automation:
- **Phase 1 & 2**: `python pg_migrator.py init-replication --drop-dest`
- **Phase 3 & 4**: `python pg_migrator.py post-migration`

### Interactive TUI & Wizard
Launch the graphical dashboard or the guided assistant:
```bash
python pg_migrator.py tui
python pg_migrator.py wizard
```

### Development Workflows (Makefile)
- `make install`: Setup venv and dependencies.
- `make test-unit`: Run unit tests.
- `make test-all`: Run unit, integration, and E2E tests (requires Docker).
- `make env-up` / `make env-down`: Manage Docker test environment (source/dest DBs).
- `make build`: Bundle into a single executable using PyInstaller.

---

## Project Structure
- `pg_migrator.py`: Main CLI entry point.
- `src/main.py`: Main TUI entry point.
- `src/cli/`: Subcommand logic and helper functions.
- `src/tui.py`: Textual-based TUI implementation.
- `src/db.py`: PostgreSQL interaction layer.
- `src/migrator.py`: Core migration logic.
- `tests/`: Comprehensive test suite (unit, integration, e2e).
- `test_env/`: Dockerized test infrastructure (Pagila dataset).
- `RESULTS/`: Default directory for logs and HTML audit reports.

---

## Important Conventions
- **Naming**: Use snake_case for Python files and functions.
- **Logging**: Use the centralized logging setup in `src/cli/helpers.py`.
- **Error Handling**: Use exit codes (0: success, 1: error, 2: fatal, 130: interrupt).
- **Reports**: Every migration step should contribute to the final HTML audit report generated in the `RESULTS` directory.
