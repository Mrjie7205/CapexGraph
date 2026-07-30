# Live event gateway

This guide covers the implemented v0.5.1 M0-M7 path. It is a local, single-user market-signal
workspace. It does not place trades, treat aggregator content as Evidence, or complete the missing
v0.4 mainline policy.

## Three executable paths

| Path | Credential | Use |
| --- | --- | --- |
| Frozen dual-channel replay | none | demo, CI, rules/coverage/SSE/browser validation |
| Jin10 MCP | `JIN10_MCP_BEARER_TOKEN` | adaptive latest-page flash and calendar polling |
| Jin10 Open Platform WebSocket | `JIN10_WEBSOCKET_SECRET_KEY` | flash/calendar push and optional quotes |

MCP and WebSocket are equal-priority channels. They have independent credentials, loops,
checkpoints, freshness, budget/connection health, and failure states. One channel recovering or
failing never changes the other channel's role.

## Quick start without keys

Start API and Web with `scripts/dev.ps1`, open `http://127.0.0.1:5173`, and select **Live Desk**.
Click **Load no-key replay** to create three explicitly synthetic canonical signals:

- a cross-channel matched flash;
- a divergent cross-channel flash; and
- an MCP-only calendar event.

The same path is available from CLI:

```powershell
capexgraph live demo
capexgraph live status
capexgraph live providers
capexgraph live soak --mode fixture --cycles 6 --failure-every 3
capexgraph live doctor
```

The replay is not current market information. It is intentionally dated and labeled synthetic.

## Configure real channels

In the Cockpit, choose **Connections** from the top bar or Live Desk. The product setup flow:

1. accepts the MCP Bearer Token in a password field;
2. completes the standard MCP handshake and tool/resource discovery before saving it;
3. accepts the independent WebSocket Secret-Key for later live authentication; and
4. refreshes the running gateway without exposing either value in the response.

The browser submits each value once to the loopback backend and does not put it in local/session
storage. The backend atomically updates only allowlisted keys in the repository-local ignored
`.env`. Manual configuration remains available:

```dotenv
JIN10_MCP_BEARER_TOKEN=
JIN10_WEBSOCKET_SECRET_KEY=

CAPEXGRAPH_JIN10_MCP_ENABLED=1
CAPEXGRAPH_JIN10_WEBSOCKET_ENABLED=1
CAPEXGRAPH_JIN10_MCP_TIMEOUT_SECONDS=20
CAPEXGRAPH_JIN10_MCP_CALL_BUDGET=1200

CAPEXGRAPH_JIN10_WS_FLASH_CATEGORIES=1,4
CAPEXGRAPH_JIN10_WS_CALENDAR_CATEGORIES=cj
CAPEXGRAPH_JIN10_WS_QUOTE_CATEGORIES=
```

The local MCP budget must be between 1 and the provider's documented 1500 calls per tool per
Beijing day. The default target is 1200. Budget usage resets by UTC+8 calendar date. Flash and
calendar keep independent counters because the provider rate-limits per tool.

Status endpoints never return credentials. `live providers`, `/api/v1/live/status`, and
`/api/v1/connections` report only configured/missing/readiness state.

## Operate the gateway

One-shot MCP reads:

```powershell
capexgraph live poll --stream flash
capexgraph live poll --stream calendar
```

Continuous process:

```powershell
capexgraph live monitor
```

For a bounded smoke:

```powershell
capexgraph live monitor --cycles 2 --interval 1
```

The runtime uses 30 seconds for urgent activity when budget headroom permits, 120 seconds normally,
and 300 seconds under quota pressure or quiet conditions. Changing one channel never changes the
other channel's cadence.

`list_flash` pagination is historical: `next_cursor` retrieves older rows. Continuous operation
therefore polls the latest page without a cursor and performs local identity/content-hash
deduplication. The returned cursor remains in checkpoint metadata for a future explicit backfill;
it is never mistaken for a forward stream offset.

## Live Desk

Live Desk exposes:

- a productized Connection Center for Jin10 MCP, Jin10 WebSocket, and official Codex login/model
  selection;
- independent MCP, WebSocket, and SSE state;
- call-budget usage, freshness, unread alerts, and runtime controls;
- category/channel/search filters;
- canonical signals with matched, divergent, and channel-only state;
- every retained observation and its published/observed timestamps;
- overlap, MCP-only, WebSocket-only, and P50/P95 delivery delay;
- relevance, urgency, importance, novelty, entity/theme, exclusion, and injection-rule results;
- no-key rules analysis or an explicitly selected Codex/OpenAI model path;
- model/provider/prompt/call/failure lineage;
- Watch, Dismiss, and Mute actions;
- a human-gated Research Bridge for official-source tasks, guarded capture, Evidence review,
  immutable run context, and parent-preserving linked re-evaluation;
- the complete signal/observation/analysis/action/verification/run audit timeline; and
- browser notifications only after explicit permission.

Settings control channel switches, polling cadence, thresholds, cooldown, include/exclude keywords,
and notification preference. Credentials are managed separately in Connection Center and never
appear in settings responses.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/connections` | redacted local connection and Codex account/model readiness |
| `POST` | `/api/v1/connections/jin10-mcp` | verify then persist one MCP credential locally |
| `POST` | `/api/v1/connections/jin10-websocket` | persist one WebSocket credential locally |
| `POST/GET` | `/api/v1/connections/codex/login` | start/poll official Codex ChatGPT login |
| `POST` | `/api/v1/connections/codex/model` | persist an available Codex model selection |
| `GET` | `/api/v1/live/status` | runtime, independent channel state, unread and coverage |
| `GET` | `/api/v1/live/doctor` | local integrity, queue, channel, and release-gate diagnostics |
| `GET` | `/api/v1/live/soak-reports` | persisted bounded release-gate reports |
| `POST` | `/api/v1/live/demo` | persist the synthetic no-key replay |
| `POST` | `/api/v1/live/poll` | one MCP flash/calendar head poll |
| `POST` | `/api/v1/live/monitor/start\|stop` | control the local supervisor |
| `GET` | `/api/v1/live/events` | filter canonical current signals |
| `GET` | `/api/v1/live/events/{id}` | signal, observations, rules, analysis, alert, actions |
| `GET` | `/api/v1/live/coverage` | overlap/channel-only/divergence and delay metrics |
| `GET/PATCH` | `/api/v1/live/settings` | non-secret operator settings |
| `POST` | `/api/v1/live/events/{id}/analyze` | rules or explicit model impact analysis |
| `POST` | `/api/v1/live/events/{id}/actions` | read/watch/verify/dismiss/mute/ignore |
| `POST` | `/api/v1/live/events/{id}/verify` | confirmed official-source verification task |
| `GET` | `/api/v1/live/verification-tasks[/{id}]` | inspect the durable verification queue |
| `POST` | `/api/v1/live/verification-tasks/{id}/sources` | confirmed regulator/issuer source candidate |
| `POST` | `/api/v1/live/verification-tasks/{id}/capture` | guarded capture or visible retry |
| `POST` | `/api/v1/live/verification-tasks/{id}/review` | explicit approve/reject and Evidence gate |
| `POST` | `/api/v1/live/events/{id}/runs` | create a new linked Theme/Anchor research run |
| `POST` | `/api/v1/live/events/{id}/reevaluate` | create a child run without mutating the parent |
| `GET/POST` | `/api/v1/runs/{id}/live-context` | list or attach immutable signal snapshots |
| `GET` | `/api/v1/live/events/{id}/audit` | synthesized and persisted audit timeline |
| `GET` | `/api/v1/live/stream` | reconnectable SSE using `Last-Event-ID` |

SSE alert IDs are durable SQLite row IDs. Reconnect with `Last-Event-ID` to resume after the last
delivered canonical alert. Cross-channel revisions do not create duplicate alerts.

## Retention and trust

- `metadata_only` and `ephemeral` observations persist title/metadata/hash, not raw body text.
- Frozen fixtures may persist their synthetic content.
- Provider HTML is reduced to bounded plain text.
- Provider picture URLs are omitted and never hotlinked.
- Dead letters contain a payload hash and safe validation error only.
- Provider content is treated as hostile input and isolated from model instructions.
- An aggregator signal itself cannot become Evidence, an official event, or a
  medium/high-confidence relationship.

M7 adds the bridge without weakening that boundary:

1. a confirmed task moves the signal to `official_source_pending` by appending a signal version;
2. only recognized regulator or explicitly supplied issuer domains enter the task;
3. guarded capture remains `captured` until a human reviews the unchanged source hash;
4. approval creates a separate `LiveEvidenceLink` and a new `evidence_linked` signal version;
5. rejection creates no link;
6. run context is stored as an immutable snapshot and content hash; and
7. linked re-evaluation creates a new child run and leaves the parent unchanged.

Generic `attach` and `linked_reevaluation` actions still return a conflict. Callers must use the
dedicated endpoints so confirmation, source authority, human review, hash integrity, and audit
lineage cannot be skipped.

## Release and recovery gates

The no-key fixture soak repeatedly replays both channels, injects an alternating one-channel
failure, checks checkpoint isolation, and requires recovery plus stable canonical identity. It
uses a temporary exercise database and persists only a bounded report:

```powershell
capexgraph live soak --mode fixture --cycles 6 --failure-every 3
capexgraph live doctor
```

The credentialed provider soak requires both equal-priority channel credentials:

```powershell
capexgraph live soak --mode providers --cycles 30 --interval 10
```

Missing WebSocket access fails that credentialed gate explicitly; it does not downgrade MCP to a
fallback or manufacture a passing report. See [`LIVE_OPERATIONS.md`](LIVE_OPERATIONS.md) for
Windows process operation, backup/restore, restart, retry, and incident handling.

## Troubleshooting

| State | Meaning | Action |
| --- | --- | --- |
| `WAIT KEY` / `not_configured` | channel credential is absent | add only that channel's environment variable |
| `BUDGET HOLD` / `exhausted` | local MCP daily target reached | wait for Beijing-day reset or raise within 1500 |
| `DEGRADED` | transport/protocol/connection failure | inspect safe checkpoint error; other channel continues |
| `STANDBY` | configured but not polled/connected yet | poll once or start monitor |
| `REPLAY` | frozen synthetic source | do not interpret as current market data |

If WebSocket has no Secret-Key, frozen protocol/auth/subscription/reconnect tests still run and MCP
remains fully usable. Do not describe WebSocket as live-connected until a credentialed smoke passes.
