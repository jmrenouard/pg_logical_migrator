![pg_logical_migrator](../pg_logical_migrator.jpg)

# Core Concepts of Logical Replication

Logical replication in PostgreSQL is a method of replicating data objects and their changes based on their replication identity (usually a primary key). It allows for cross-version migration, granular control, and minimal downtime.

## Core Architecture

Logical replication uses a **publish-and-subscribe** model:

- **Publication**: Defined on the **Source** database (Publisher). It specifies which tables' changes should be replicated.
- **Subscription**: Defined on the **Destination** database (Subscriber). It connects to the publication and pulls changes.
- **Replication Slot**: Created on the source server to ensure that WAL (Write-Ahead Log) files are not discarded until they have been successfully processed by the subscriber.

## How it Works

1.  **Logical Decoding**: The source server decodes the binary WAL into a logical format (insert, update, delete).
2.  **Streaming**: The decoded changes are sent over a standard connection to the subscriber.
3.  **Application**: The subscriber applies the changes to its local tables in the same order they occurred.

---
[Return to Documentation Index](README.md)
