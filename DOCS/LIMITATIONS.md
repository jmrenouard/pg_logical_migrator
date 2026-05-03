# Technical Limitations & Constraints

While **pg_logical_migrator** provides a highly automated workflow, logical replication has inherent technical constraints that must be understood before initiating a production migration.

### 🛡️ Mandatory Primary Keys
Logical replication **requires** a Primary Key or a unique, non-null index to replicate `UPDATE` and `DELETE` operations.
- **Problem**: Tables without a PK will block replication if any data changes occur during the migration.
- **Workaround**: We automatically attempt to set `REPLICA IDENTITY FULL` for tables without a PK (Step 5). This allows replication to proceed but **severely impacts performance** on the subscriber as it must perform a sequential scan for every update/delete.

### 🐘 Large Objects (LOBs / BLOBs)
Standard logical replication **does not** support PostgreSQL "Large Objects" (stored in `pg_largeobject`).
- **Detection**: Our `diagnose` command identifies if LOBs are present.
- **Solution**: We provide specialized **`sync-lobs`** (Step 11a) and **`sync-unlogged`** (Step 11b) commands. The `sync-lobs` command manually exports LOBs from the source, imports them into the destination (generating new OIDs), and updates the referencing `OID` columns in your tables using Primary Key matching. The `sync-unlogged` command manually truncates and copies data for UNLOGGED tables that cannot be replicated.
- **Requirement**: Target tables must have a Primary Key for the update to succeed.

### 🏗️ DDL (Data Definition Language)
Schema changes (e.g., `ALTER TABLE`, `CREATE INDEX`) are **not** replicated.
- **Constraint**: The schema must remain static during the migration process.
- **Risk**: Any DDL executed on the source after Step 4a will result in replication errors or data loss.

### 🔄 Sequences
Sequences are not automatically synchronized in real-time.
- **Behavior**: Sequences remain at their initial values on the destination throughout the replication.
- **Step 9/10**: We provide a explicit synchronization step to read current sequence values from the source and apply them to the destination just before cutover.

### 📉 Unlogged Tables
Data in `UNLOGGED` tables is not written to the WAL and therefore cannot be replicated.
- **Behavior**: These tables will be created on the destination, but will remain empty.

### 🛡️ Triggers and Foreign Keys
- **Triggers**: By default, triggers (like those for auditing or denormalization) are **not** executed on the subscriber to avoid duplicate actions.
- **Foreign Keys**: These are checked only when data is initially copied, or when the `REPLICA IDENTITY` is set.
- **Strategy**: We recommend disabling triggers and foreign key checks during the initial copy (handled in Step 4a/12) and re-enabling them after the data is fully synchronized (Step 11).

### 🌐 Multi-Database Migration Architecture
- **Capability**: The tool now supports cross-database batch execution. By defining multiple databases (or `*` for auto-discovery) in `config_migrator.ini`, `pg_logical_migrator` iterates through them efficiently in a single pass.
- **Complexity**: Setting up replication for multiple databases sequentially requires one publication/subscription pair per database.
- **Constraint**: Migrating a large number of databases may temporarily increase memory footprint and connection overhead. Monitoring both source and destination connection limits is required during wide-scale automated initialization pipelines.
