# Explanation

Conceptual and architectural deep dives explaining how **pg_logical_migrator** orchestrates low-downtime PostgreSQL migrations and preserves data integrity.

## Articles

- **[Architecture and Replication Lifecycle](architecture-and-replication-lifecycle.md)**: Modular engine design, schema split (`pre-data` vs `post-data`), cutover ordering rationale, and out-of-band object synchronization.

## Related Quadrants

- Exact CLI flags and INI keys: [Reference](../03-reference/index.md).
- Step-by-step execution runbooks: [How-To Guides](../02-how-to-guides/index.md).
