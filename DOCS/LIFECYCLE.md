# Migration Lifecycle Overview

A successful migration follows a set of distinct phases. Each phase ensures data integrity and consistency between the source and target.

| Phase | Instance | Actions & Description |
| :--- | :--- | :--- |
| **1. Preparation** | **Source** | Configure `wal_level = logical`, `max_wal_senders`, and `max_replication_slots`. **Restart Required**. |
| | **Source** | Create replication user with `REPLICATION` role and `GRANT SELECT` on tables. |
| | **Source** | Update `pg_hba.conf` for the target IP and reload. |
| | **Target** | Initialize schema via `pg_dump --schema-only` (as DDL is not replicated). |
| **2. Activation** | **Source** | `CREATE PUBLICATION nom_pub FOR ALL TABLES;` (or specific tables). |
| | **Target** | `CREATE SUBSCRIPTION nom_sub CONNECTION '...' PUBLICATION nom_pub;`. Triggers initial copy. |
| **3. Finalization** | **Both** | Monitor `pg_subscription_rel` (state 'r' for ready) and lag in `pg_stat_replication`. |
| | **Source** | Cut off application access (e.g., via `pg_hba.conf`) to freeze database state. |
| | **Source/Target**| Sync sequences: Capture values on source and apply to target. |
| | **Target** | Redirect application traffic to the new instance. |
| **4. Cleanup** | **Target** | `DROP SUBSCRIPTION nom_sub;`. (Note: use `SET (slot_name=NONE)` if source is already down). |
| | **Source** | `DROP PUBLICATION nom_pub;` if continuing old source instance lifecycle. |

---
[Return to Documentation Index](README.md)
