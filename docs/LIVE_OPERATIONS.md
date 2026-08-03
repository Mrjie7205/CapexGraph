# Live gateway operations

This is the operating and recovery runbook for the v0.5.1 live-event gateway. The gateway is a
local, single-user research service. It creates research priorities and auditable context; it does
not place orders, manage positions, or treat aggregator messages as Evidence.

## Release gate without provider keys

Run the deterministic, isolated failure exercise before upgrading or handing off a build:

```powershell
capexgraph live soak --mode fixture --cycles 6 --failure-every 3
capexgraph live doctor
```

The fixture soak:

- replays both channels repeatedly to exercise observation and signal idempotency;
- injects an alternating single-channel read failure;
- checks that the other checkpoint is byte-for-byte unchanged by that failure;
- requires the failed channel to recover on a later cycle;
- requires the canonical signal count to remain stable; and
- runs its synthetic observations in a temporary database, persisting only the bounded
  `LiveSoakReport` to the selected workspace.

`live doctor` is read-only apart from applying safe additive migrations when the store is first
opened. It checks SQLite `quick_check`, schema level, non-secret provider configuration, persisted
channel health, failed official-source tasks, and the latest soak report. `ready=true` means the
local release gates pass. Missing live-provider credentials remain visible warnings and are not
misrepresented as connected channels.

## Credentialed provider soak

MCP and WebSocket are equal-priority channels. The provider soak therefore requires both
credentials instead of silently testing only one:

```dotenv
JIN10_MCP_BEARER_TOKEN=...
JIN10_WEBSOCKET_SECRET_KEY=...
```

```powershell
capexgraph live soak --mode providers --cycles 30 --interval 10
capexgraph live doctor
```

If either credential is absent, the command exits with an explicit configuration gate and does not
create a passing live report. A frozen/mock WebSocket test proves protocol behavior, not live
connectivity. Until a Secret-Key is available and this soak passes, report WebSocket as
`WAIT KEY` / contract-tested / live-smoke pending.

## Daily operation

Open the Cockpit **Connections** panel for credential-safe onboarding and readiness checks. MCP is
verified before persistence. WebSocket remains `WAIT KEY` / `待启动验证` until the monitor completes
a real authenticated connection. The Codex card is independent of these market-data channels.

Inspect configuration without revealing credential values:

```powershell
capexgraph live providers
capexgraph live status
```

One-shot MCP reads:

```powershell
capexgraph live poll --stream flash
capexgraph live poll --stream calendar
```

Continuous equal-priority supervisor:

```powershell
capexgraph live monitor
```

The process must remain running for continuous collection. On Windows, start it from a dedicated
Task Scheduler entry or service wrapper under the same user account that owns the repository-local
`.env` and state database. Configure:

- the repository as the working directory;
- the installed virtual-environment interpreter or `capexgraph` executable;
- restart-on-failure with a bounded delay;
- one instance only; and
- stdout/stderr to an operator-owned log directory that is not committed.

Do not copy credentials into command-line arguments, task names, logs, or browser storage.
Connection Center is the only frontend credential-entry surface: it sends each value once to the
loopback backend, never reads it back, and leaves ongoing processes to read the ignored local
backend environment.

## Research Bridge operation

In Live Desk, select a signal and open **Research bridge**:

1. choose an existing research run or create a new linked Theme/Anchor run;
2. explicitly create the official-source verification task;
3. add a regulator URL, or a company URL plus its issuer domain;
4. capture the source through the guarded downloader;
5. inspect the captured material and explicitly approve or reject it; and
6. attach an immutable context snapshot to an existing run or create a child re-evaluation.

Important state rules:

- `pending` and `official_source_pending` mean a source is still missing;
- `captured` means bytes were captured and hashed, not approved;
- only unchanged `reviewed` Evidence from a regulator/issuer source can create a
  `LiveEvidenceLink`;
- approving Evidence appends a new signal version; it never rewrites the prior signal;
- attaching context stores a content hash and snapshot; context integrity is checked when research
  prompts are built; and
- child re-evaluation creates a new run and records `parent_run_id`; the parent payload is not
  changed.

Every state-changing bridge action requires explicit confirmation and enters the event audit
timeline. Generic `attach` or `linked_reevaluation` actions remain blocked so callers cannot skip
these gates.

## Restart and recovery

Channel checkpoints are independent. After restart:

1. run `capexgraph live doctor`;
2. inspect `capexgraph live status`;
3. perform one MCP head poll;
4. start the supervisor; and
5. confirm each configured channel reaches `ACTIVE` or an expected explicit state.

Interpret channel states:

| State | Meaning | Action |
| --- | --- | --- |
| `WAIT KEY` / `not_configured` | credential absent | configure only that channel; do not call it live |
| `BUDGET HOLD` / `exhausted` | local MCP target reached | wait for Beijing-day reset or adjust within the hard limit |
| `DEGRADED` | source read, protocol, or connection failure | inspect the safe error; verify the other channel remained unchanged |
| `STANDBY` | configured but no successful read/connect yet | poll once or start the supervisor |
| `REPLAY` | frozen synthetic source | never interpret as current market data |

A failed official-source capture remains retryable. The task keeps a redacted, bounded failure
message and attempt count. Rejecting a captured source creates no Evidence link. If the last open
task is rejected, the signal returns to `signal_only` through a new signal version.

## Database upgrade, backup, and restore

Before a release or schema upgrade:

```powershell
capexgraph db status
capexgraph db backup --output .\backup\capexgraph-before-live.db
capexgraph db upgrade
capexgraph live doctor
```

Schema version 8 is additive. It adds verification tasks, reviewed Evidence links, immutable run
context links, bridge audit entries, and soak reports. It does not rewrite earlier runs, Evidence,
observations, signal versions, corporate events, financial/market facts, or tracking history.

To restore, stop API/Web/live processes first:

```powershell
capexgraph db restore .\backup\capexgraph-before-live.db --force
capexgraph live doctor
```

Restore uses SQLite backup and `quick_check`, replaces the target atomically, and applies registered
safe migrations.

## Incident checklist

1. Preserve the database and logs; do not delete checkpoints to make the UI green.
2. Run `live doctor` and save its credential-safe output.
3. Identify the affected provider/channel/stream.
4. Confirm whether the other equal-priority channel continued independently.
5. Check freshness, quota date/calls, retry state, and bounded checkpoint error.
6. For data disagreement, preserve `divergent`; do not overwrite one observation with the other.
7. For Evidence incidents, compare the stored source hash before any review or attachment.
8. Back up before recovery changes.
9. Re-run fixture soak, targeted provider smoke, Python tests, Web build, and wheel gate.

Never put Bearer Tokens, Secret-Keys, licensed raw messages, or full provider responses into issue
reports or public artifacts.
