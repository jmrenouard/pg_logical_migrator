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
- **source_host / source_port**: Host/Port used by the **destination** container to reach the **source** DB. *Crucial for Docker networks.*
- **dest_host_for_src / dest_port_for_src**: Host/Port used by the **source** to reach the **destination** during **reverse** replication.

#### 🗂️ Target Schema & Database Topology Configuration
The migrator is highly flexible and supports various replication topologies configured via the `.ini` file:

1. **Single Schema / Single Database**
   Configure your global `[source]` and `[destination]` blocks targeting a single database. Under `[replication]`, define exactly one schema:
   `target_schema = public`

2. **Multiple Schemas / Single Database**
   Under `[replication]`, define a comma-separated list of schemas:
   `target_schema = public, auth, data`

3. **Multiple Databases**
   To replicate multiple databases simultaneously, define database-specific overrides in your `.ini` file using the `[database:<dbname>]` section syntax. This will override global settings for each specified database.
   ```ini
   [source]
   host = global-db.internal
   
   [database:crm_db]
   target_schema = public, crm_data
   
   [database:billing_db]
   target_schema = invoices
   ```

4. **All Schemas (Single or Multi-DB)**
   Use `all` or `*` to automatically discover and replicate all user schemas in the target database(s) (ignoring system/extension schemas like `pg_catalog`, `postgis`, etc.):
   `target_schema = all`

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
