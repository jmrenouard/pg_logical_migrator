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
The migrator is highly flexible and supports various replication topologies configured via the `.ini` file. Below are full examples of each supported configuration.

---

### Case 1: Single Schema / Single Database
Replicating a single schema (e.g. `public`) from a single database.

```ini
[source]
host = 192.168.1.100
port = 5432
user = rep_user
password = rep_pass
database = my_database

[destination]
host = 10.0.0.50
port = 5432
user = rep_user
password = rep_pass

[replication]
publication_name = pub_single
subscription_name = sub_single
target_schema = public
```

---

### Case 2: Multiple Schemas / Single Database
Replicating specific schemas (e.g., `public`, `auth`, `data`) from a single database.

```ini
[source]
host = 192.168.1.100
user = rep_user
password = rep_pass
database = monolith_db

[destination]
host = 10.0.0.50
user = rep_user
password = rep_pass

[replication]
publication_name = pub_multi_schema
subscription_name = sub_multi_schema
# Use a comma-separated list of schemas
target_schema = public, auth, data
```

---

### Case 3: Multiple Databases (Multi-Tenant)
Replicating multiple databases simultaneously. The orchestrator allows you to define a baseline global configuration and override specific settings (like schemas or specific source connection details) per database using the `[database:<dbname>]` section syntax.

```ini
[source]
# Global defaults for all databases
host = global-source.internal
user = rep_user
password = rep_pass

[destination]
# Global destination defaults
host = global-dest.internal
user = rep_user
password = rep_pass

[replication]
publication_name = pub_global
subscription_name = sub_global

# Database 1: CRM Database overrides
[database:crm_db]
target_schema = public, crm_data

# Database 2: Billing Database overrides
[database:billing_db]
target_schema = invoices
source_port = 5433  # Overriding the port just for billing_db
```

---

### Case 4: All Schemas (Single or Multi-DB)
Automatically discovers and replicates all user-defined schemas in the target database(s). System and extension schemas (like `pg_catalog`, `information_schema`, `postgis`) are safely excluded.

```ini
[source]
host = 192.168.1.100
user = rep_user
password = rep_pass
database = legacy_db

[destination]
host = 10.0.0.50
user = rep_user
password = rep_pass

[replication]
publication_name = pub_all
subscription_name = sub_all
# Replicate everything
target_schema = all
```

---

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
