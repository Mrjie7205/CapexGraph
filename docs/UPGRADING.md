# Database upgrade, backup, and restore

CapexGraph keeps research runs, checkpoints, and tracking state in one SQLite database. Starting
with v0.3, that database has an ordered migration history in `schema_migrations`.

## Inspect before changing a workspace

```powershell
capexgraph db status
capexgraph db backup --output .\backup\capexgraph.db
capexgraph db upgrade
```

An unversioned v0.2 database is reported as `legacy=True`, version `0`, with migrations pending.
The baseline migration creates only missing tables and indexes, then records its checksum. Existing
runs, checkpoints, tracked candidates, snapshots, and trigger events are not rewritten.

The v0.3.0 schema reaches version 3:

1. the v0.2 run/checkpoint/tracking baseline;
2. the persistent source-suggestion queue; and
3. immutable, source-linked financial facts.

All three are additive and safe for startup. The legacy-upgrade test verifies that the original
run, checkpoint, tracked candidate, snapshot, and trigger-event counts remain unchanged.

The in-development v0.4 schema adds version 4:

4. normalized daily `market_bars` and hashed `market_quality_reports`.

It is also additive and safe for startup. Upgrading creates the two tables and indexes without
rewriting v0.3 run, checkpoint, tracking, source-suggestion, or financial-fact records. Licensed raw
provider responses remain files under the ignored runtime directory; they are not embedded into the
portable database migration.

The v0.5 event foundation adds version 5:

5. append-only `corporate_event_versions` with stable event keys, semantic version hashes,
   source/system timestamps, lifecycle state, and source/Evidence references.

Version 5 is additive and safe for startup. It does not rewrite earlier event knowledge because no
event table existed before it, and it does not modify runs, source suggestions, financial facts,
market bars, or tracking history.

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

## Moving from v0.2 to v0.3

1. stop the API and Cockpit;
2. create a backup with the v0.2 or v0.3 CLI;
3. install v0.3;
4. run `capexgraph db status` and `capexgraph db upgrade`; and
5. start the API, inspect an older run, and verify its tracking card.

Older run payloads are preserved. New v0.3 manifest keys such as `evidence_mode`, provider records,
and coverage are populated when a run is created, executed, or inspected; the upgrader does not
fabricate historical provider metadata.
