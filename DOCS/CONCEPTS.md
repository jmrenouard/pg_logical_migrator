# Core Concepts & Architecture

**pg_logical_migrator** is built on the foundation of **PostgreSQL Logical Replication**, designed specifically for low-downtime migrations between heterogeneous infrastructures or major versions.

### 🛡️ Design Philosophy

- **Stability Over Speed**: Every step is validated. We prioritize data integrity and structural parity over the absolute speed of initial copy.
- **Surgical Transparency**: Every SQL command is logged, and HTML reports are generated for post-migration audits.
- **Stateless Orchestration**: The tool acts as a stateless orchestrator, maintaining all state within the source and destination PostgreSQL instances.

### 🔄 The Logical Flow

Logical replication works by decoding the Write-Ahead Log (WAL) into a stream of logical changes (INSERT, UPDATE, DELETE). This allows for:
1.  **Baseline Copy**: Initial snapshot of data is transferred using `COPY`.
2.  **Streaming Delta**: Real-time changes are streamed and applied incrementally.
3.  **Cross-Version Parity**: Moving data between different major PG versions (e.g., PG12 to PG17).

### 🏗️ Workflow Structure

The migration is divided into three logical phases:
1.  **Preparation (Steps 1-4)**: Connectivity checks, compatibility diagnostics, and structural (schema) setup.
2.  **Execution (Steps 5-7)**: Initial data synchronization and continuous delta streaming.
3.  **Finalization (Steps 8-16)**: Final data audit, object parity checks, and sequence synchronization before application cutover.

### ⚖️ Reliability & Rollback

We include a built-in **Reverse Replication** capability. Once the primary migration is complete, the tool can configure the new instance as a publisher and the old instance as a subscriber. This ensures a safe "exit strategy" (Rollback) with zero data loss in the event of an application-level failure after the cutover.
