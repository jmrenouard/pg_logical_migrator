# Limitations & Pitfalls

PostgreSQL logical replication is a powerful tool but has several key limitations and constraints that must be understood to avoid migration failure or performance degradation.

## 1. Common Restrictions

- **No DDL Replication**: `CREATE`, `ALTER`, or `DROP` commands are not replicated. Structural changes (like adding a column) must be manually applied on both instances.
- **No Automatic Additions**: New tables created after the publication is established aren't added automatically unless `FOR ALL TABLES` is used.
- **Large Objects (LO)**: Binary blobs in `pg_largeobjects` are NOT replicated.
- **Views & MatViews**: Only base tables are replicated. Views and Materialized Views must be manually refreshed or recreated.
- **No Multi-master per Table**: Built-in multi-directional replication for the same table isn't supported natively.

## 2. Row Identification (UPDATE/DELETE)

PostgreSQL must be able to identify unique rows for updates or deletes using a Unique Constraint (usually the Primary Key).

- If no Primary Key exists, you can use `REPLICA IDENTITY FULL`, which records the entire row contents in the WAL.
- **Extreme Caution**: `REPLICA IDENTITY FULL` can carry **severe performance impacts** for large tables.
- Certain data types (e.g., `point`, `box`) without default B-tree/Hash operator classes will fail `UPDATE`/`DELETE` even with `REPLICA IDENTITY FULL`.

## 3. Performance & Hardware Impact

- **Severe Degradation**: Using `REPLICA IDENTITY FULL` on tables with millions of rows can drastically slow down the source database, potentially causing resource exhaustion.
- **Hardware Costs**: Logical replication involves significant CPU and I/O overhead on both nodes. Closely monitor system resources on smaller server configurations.

---

## 4. Deep Dive: REPLICA IDENTITY FULL

While it provides a solution for tables without primary keys, the overhead is substantial:
1.  **Performance**: For tables with millions of rows, it is highly detrimental.
2.  **Implementation**: Requires direct modification of the source database schema.
3.  **Incompatibility**: Many third-party replication tools (like `pglogical`) do not support this mode.

---
[Return to Documentation Index](README.md)
