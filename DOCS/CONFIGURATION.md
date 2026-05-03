# Configuration Reference

The behavior of **pg_logical_migrator** is controlled through a standard `.ini` configuration file. This file defines the connection parameters, replication settings, and operational logging.

### 🔌 [source] & [destination]
These sections define how the orchestrator connects to each PostgreSQL instance.

- **host**: Address of the database instance.
- **port**: Connection port (default: 5432).
- **user**: PostgreSQL role with replication privileges.
- **password**: Password for the user.
- **database**: Name of the target database.

### 🔄 [replication]
Critical settings for the logical replication pipeline.

- **publication_name**: Unique name for the publication on the source.
- **subscription_name**: Unique name for the subscription on the destination.
- **target_schema**: Use `all` for the whole database or a comma-separated list of specific schemas (e.g., `public, api_v1`).
- **source_host / source_port**: Host/Port used by the **destination** container to reach the **source** DB. *Crucial for Docker networks.*
- **dest_host_for_src / dest_port_for_src**: Host/Port used by the **source** to reach the **destination** during **reverse** replication.

### 📝 [logging]
- **loglevel**: Controls output verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- **log_file**: Path to the persistent log file.

### ⚙️ Mandatory PostgreSQL Parameters
The following settings **must** be configured on both source and destination instances:

- `wal_level = logical`
- `max_replication_slots = 10+`
- `max_wal_senders = 10+`
- `max_worker_processes = 10+`

### 💡 Best Practices
- **Isolation**: Always use a dedicated replication role with the `REPLICATION` attribute and `SELECT` permissions on target schemas.
- **SSL**: For production migrations, ensure `sslmode=require` is configured in your connection strings or environment.
- **WAL Retention**: Ensure the source has sufficient disk space for WAL files if the subscriber lags.
