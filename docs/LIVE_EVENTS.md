# Live event gateway

This guide covers the implemented v0.5.1 M0-M6 path. It is a local, single-user market-signal
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
```

The replay is not current market information. It is intentionally dated and labeled synthetic.

## Configure real channels

Put credentials only in the repository-local ignored `.env`:

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

The frontend never accepts or returns credentials. `live providers` and `/api/v1/live/status`
report only configured/missing state.

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

- independent MCP, WebSocket, and SSE state;
- call-budget usage, freshness, unread alerts, and runtime controls;
- category/channel/search filters;
- canonical signals with matched, divergent, and channel-only state;
- every retained observation and its published/observed timestamps;
- overlap, MCP-only, WebSocket-only, and P50/P95 delivery delay;
- relevance, urgency, importance, novelty, entity/theme, exclusion, and injection-rule results;
- no-key rules analysis or an explicitly selected Codex/OpenAI model path;
- model/provider/prompt/call/failure lineage;
- Watch, Verify, Dismiss, and Mute actions; and
- browser notifications only after explicit permission.

Settings control channel switches, polling cadence, thresholds, cooldown, include/exclude keywords,
and notification preference. They never contain credentials.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/live/status` | runtime, independent channel state, unread and coverage |
| `POST` | `/api/v1/live/demo` | persist the synthetic no-key replay |
| `POST` | `/api/v1/live/poll` | one MCP flash/calendar head poll |
| `POST` | `/api/v1/live/monitor/start\|stop` | control the local supervisor |
| `GET` | `/api/v1/live/events` | filter canonical current signals |
| `GET` | `/api/v1/live/events/{id}` | signal, observations, rules, analysis, alert, actions |
| `GET` | `/api/v1/live/coverage` | overlap/channel-only/divergence and delay metrics |
| `GET/PATCH` | `/api/v1/live/settings` | non-secret operator settings |
| `POST` | `/api/v1/live/events/{id}/analyze` | rules or explicit model impact analysis |
| `POST` | `/api/v1/live/events/{id}/actions` | read/watch/verify/dismiss/mute/ignore |
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
- A signal cannot become Evidence, an official event, or a medium/high-confidence relationship.

M7 will add explicit official-source tasks, reviewed Evidence attachment, and linked re-evaluation.
M6 intentionally returns a conflict if a caller requests `attach` or `linked_reevaluation`.

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
