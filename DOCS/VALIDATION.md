# Critical Schema Control Points (Verification Checklist)

Check these points on the **Target** database before implementing logical replication.

| Schema Element | Rule / State on Target | Impact if Not Respected |
| :--- | :--- | :--- |
| **Table Structure (DDL)** | **Manually created prior** | **Immediate Blocking**: Replication stops if a table/column is missing. |
| **Data Types** | **Exact match** | **Type Error**: Incompatible data will be rejected. |
| **Primary Keys (PK)** | **Essential Presence** | **DML Blocking**: `UPDATE`/`DELETE` will fail without a PK or `REPLICA IDENTITY`. |
| **Constraints** | **More permissive or equal** | **Constraint Violation**: If target is more restrictive (e.g., `NOT NULL` on target but allow `NULL` on source), sync will fail. |
| **Unique Constraints** | **Non-restrictive** | **Uniqueness Conflict**: Incoming rows might violate target-specific uniqueness rules. |
| **Foreign Keys** | **Scope consistency** | **Integrity Violation**: Replicated `TRUNCATE` fails if target has links to non-subscribed tables. |
| **Triggers** | **Disabled by default** | **Missing Logic**: Standard triggers don't fire during replication unless set to `ENABLE REPLICA`. |
| **Sequences** | **Not synchronized** | **Duplicate IDs**: Cutover will fail with duplicate key errors if not manually synced. |
| **Partitioning** | **Structure matching** | **Data Loss**: If leaf partitions don't exist on target, data cannot be inserted. |

---
[Return to Documentation Index](README.md)
