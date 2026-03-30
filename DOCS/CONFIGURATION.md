# Prerequisites & Database Parameters

Before starting a migration, several parameters in the `postgresql.conf` file of both databases must be precisely configured. Most of these changes **require a restart** of the PostgreSQL instance.

## Source Server (Publisher)

These settings ensure the source can generate and hold logical decoding data.

| Parameter | Recommended Value | Description |
| :--- | :--- | :--- |
| `wal_level` | `logical` | **CRUCIAL**: Enables logical decoding of WAL. (Default is often `replica`). |
| `max_replication_slots` | `>= 1` | Maximum number of replication slots. Must be at least equal to the number of subscriptions. (Default: 10). |
| `max_wal_senders` | `>= 1` | Maximum number of WAL sender processes. Should be `>= max_replication_slots` plus any physical replicas. (Default: 10). |
| `max_worker_processes` | Sized for load | Total background worker processes. Must support the replication load and match the target server. |

### Security (`pg_hba.conf`)

You must explicitly authorize the target server's IP to connect using a user with `REPLICATION` or `SUPERUSER` privileges.

---

## Destination Server (Subscriber)

These settings ensure the target can ingest and apply the replicated changes.

| Parameter | Recommended Value | Description |
| :--- | :--- | :--- |
| `wal_level` | `logical` | Recommended to set to `logical` even on the subscriber for consistency. |
| `max_replication_slots` | `>= 1` | Maximum active subscriptions + `tablesync` workers. (Default: 10). |
| `max_logical_replication_workers` | `>= 1` | Maximum processes dedicated to applying replication. (Default: 4). |
| `max_sync_workers_per_subscription` | `>= 4` | Parallelism specifically for the initial data copy phase. |
| `max_worker_processes` | Sized for load | Should be `>=` source server to avoid connection refusals. |

---
[Return to Documentation Index](README.md)
