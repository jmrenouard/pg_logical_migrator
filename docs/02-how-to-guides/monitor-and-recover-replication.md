# How to Monitor and Recover Replication

Use this procedure to inspect synchronization progress, pause active subscriptions, and manage rollback paths.

## Prerequisites

- Confirm an active publication and subscription exist on your databases.
- Confirm your `config_migrator.ini` file points to both clusters.

NOTE: For flag syntax and defaults, see [CLI Reference](../03-reference/cli-commands-and-configuration.md).

## Procedure

### Monitor Initial Copy Progress

1. Run the replication progress command to view table states and byte progress:

```bash
python pg_migrator.py -c config_migrator.ini repl-progress
```

2. If scripts require synchronous completion, run `wait-sync`:

```bash
python pg_migrator.py -c config_migrator.ini wait-sync
```

### Pause and Resume Replication

CAUTION: When you pause replication, WAL consumption stops on the destination. Long pauses increase retained WAL disk usage on the source server.

1. Disable the destination subscription to pause replication:

```bash
python pg_migrator.py -c config_migrator.ini stop-repl
```

2. Enable the destination subscription when ready to resume:

```bash
python pg_migrator.py -c config_migrator.ini start-repl
```

### Enable Reverse Replication for Rollback

1. If post-cutover rollback protection is needed, create reverse replication from destination to source:

```bash
python pg_migrator.py -c config_migrator.ini setup-reverse
```

## Validation

Run structural object audit and fast row-count validation to check cluster synchronization:

```bash
python pg_migrator.py -c config_migrator.ini audit-objects
python pg_migrator.py -c config_migrator.ini --use-stats validate-rows
```

Confirm both commands exit with status `0` and show zero discrepancies.

## Rollback

To discard the reverse replication channel after production stability is confirmed, run reverse cleanup:

```bash
python pg_migrator.py -c config_migrator.ini cleanup-reverse
```

WARNING: If you run `cleanup`, the command drops active forward replication subscriptions, publications, and slots permanently. Do not run `cleanup` until rollback is no longer needed.

To remove all forward replication artifacts, run `cleanup`:

```bash
python pg_migrator.py -c config_migrator.ini cleanup
```
