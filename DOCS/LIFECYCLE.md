# Migration Lifecycle Management

The lifecycle of a logical migration with **pg_logical_migrator** is divided into four distinct phases. Following this structured approach minimizes operational risk and ensures zero-data-loss cutovers.

### 🧪 Phase 1: Preparation (Pre-Migration)
During this phase, the infrastructure is prepared for logical replication. No data is moved.

- **Source Configuration**: Set `wal_level = logical` and allocate sufficient replication slots and worker processes.
- **Access Control**: Configure `pg_hba.conf` on the source to allow the destination instance to connect.
- **Identity Verification**: Ensure all tables have a Primary Key or identify those requiring `REPLICA IDENTITY FULL`.
- **Pre-Data Schema**: Deploy the base structural objects (schemas, tables, types) on the target instance using `migrate-schema-pre-data`.

### ⚡ Phase 2: Activation (Initial Sync)
This phase begins the heavy lifting of data movement.

- **Publication Setup**: Create the logical publication on the source instance.
- **Subscription Creation**: Define the subscription on the destination instance, triggering the initial `COPY` phase for all tables.
- **Monitoring**: Track synchronization progress via the TUI or `repl-progress` command.

### 🏁 Phase 3: Finalization (Cutover)
The most critical phase where application traffic is redirected.

- **Freeze Traffic**: Terminate or set application access to read-only on the source instance.
- **Drain WAL**: Monitor replication lag until it reaches zero, ensuring all pending changes are applied to the destination.
- **Object Synchronization**: Perform manual syncs that logical replication misses:
    - **Sequences**: Synchronize all sequence values (`sync-sequences`).
    - **Large Objects**: Manually migrate binary data (`sync-lobs`).
    - **UNLOGGED Tables**: Manually migrate data for unlogged tables (`sync-unlogged`).
    - **Materialized Views**: Refresh data on the target (`refresh-matviews`).
- **Post-Data Schema**: Create indexes and constraints (`terminate-repl`) once initial data is landed.
- **Verification**: Perform final object audits and row count parity checks.
- **Cutover**: Point the application connection string to the new destination instance.

### 🧹 Phase 4: Cleanup (Post-Migration)
Decommissioning the migration artifacts.

- **Replication Termination**: Drop the subscription and publication using the `cleanup` command.
- **Rollback Preparation**: (Optional) Configure reverse replication (`setup-reverse`) to maintain a fallback path to the old source if unforeseen application issues arise.
- **Auditing**: Archive the generated HTML reports and logs for compliance.

---
[Return to Documentation Index](README.md)
