# Database upgrade, backup, and restore

CapexGraph keeps research runs, checkpoints, and tracking state in one SQLite database. Starting
with v0.3, that database has an ordered migration history in `schema_migrations`.

## Inspect before changing a workspace

```powershell
capexgraph db status
capexgraph db backup --output .\backup\capexgraph.db
capexgraph db upgrade
```

An unversioned v0.2 database is reported as `legacy=True`, version `0`, with migration `1` pending.
The baseline migration creates only missing tables and indexes, then records its checksum. Existing
runs, checkpoints, tracked candidates, snapshots, and trigger events are not rewritten.

Safe additive migrations may run automatically when the API, CLI, or Web-backed store first opens
the database. A future migration that is not safe for startup will stop with an explicit instruction
to run `capexgraph db upgrade`.

## Restore

Stop the API and Web development processes before replacing their active database:

```powershell
capexgraph db restore .\backup\capexgraph.db --force
```

Restore verifies the source with SQLite `quick_check`, copies through the SQLite backup API, replaces
the target atomically, verifies it again, and applies any currently registered migrations. Without
`--force`, an existing target is never overwritten.

Use `--path` on any database command when operating on a workspace other than
`CAPEXGRAPH_STATE_DB` or `runs/capexgraph.db`.
