# CapexGraph

**Evidence-first supply-chain investment research.**

CapexGraph turns an investment theme or market anchor into an auditable research run: a grounded
supply-chain graph, candidate verdicts, invalidation conditions, and forward tracking.

> 证据优先的供应链投资研究系统：从主题或热门个股出发，构建可审计的产业链图谱，寻找值得继续验证的瓶颈环节和相邻标的，并持续记录判断是否兑现。

## Why CapexGraph

Most financial agent projects start with a ticker and end with a buy/sell opinion. CapexGraph
starts one level earlier:

1. Where is capital expenditure flowing?
2. Which supply-chain relationships are actually evidenced?
3. Which nodes are hard to substitute?
4. What has the market already priced in?
5. What would prove the thesis wrong?

The project is independent from `serenity-bottleneck-hunter`. That skill remains a self-contained,
low-friction project; CapexGraph is a separate professional research system.

## v0.3 capabilities

CapexGraph `0.3.0` is an **alpha research workspace** with:

- seven-stage Theme and Anchor Scan agent workflows;
- typed, schema-validated outputs and code-enforced integrity checks;
- curated no-key semiconductor-wafer and 兆易创新 golden cases;
- three explicit model channels: no-key fixtures, the official local Codex CLI using a ChatGPT
  subscription, and the
  separately billed OpenAI Responses API;
- resumable foreground or background execution with SQLite checkpoints;
- SSRF-safe HTML/PDF evidence capture, hashing, and explicit review;
- deterministic ticker identity, no-key market snapshots, and legacy financial imports;
- a React/Vite Cockpit with run history, polling, dynamic graphs, and evidence review;
- candidate/benchmark tracking, alpha scorecards, triggers, and stage boards;
- self-contained HTML research reports;
- SEC/EDGAR and manual official-source suggestion queues with explicit capture and review;
- partial and strict evidence modes, bounded source-text context, provider/version manifests, and
  code-enforced confidence gates;
- automatic SEC Company Facts extraction with period/unit validation, restatement history, explicit
  missing values, derived formulas, and source locators;
- coverage, provider failure, checkpoint execution, financial facts, and report access in the
  Cockpit;
- report sections that distinguish reviewed facts, grounded inference, unverified hypotheses, and
  evidence gaps;
- tests, multi-version CI, Windows bootstrap, and container setup.

It produces research priorities for human review. It does not produce autonomous investment
recommendations or execute trades.

## v0.5 development preview

The active v0.5 branch adds the first official-disclosure event-calendar vertical:

- immutable `CorporateEventVersion` records with canonical entity, event type, lifecycle state,
  official/public time, system-observed time, effective/expected dates, and source lineage;
- SEC EDGAR filing discovery mapped conservatively into financial-report or regulatory-filing
  events;
- idempotent discovery plus a new version when guarded capture links the filing to Evidence;
- current, full-history, date/type/state, and point-in-time event queries;
- migration 5, `events.json`, run-manifest summaries, CLI, and API paths; and
- repository-local `.env` loading across SEC, market, model, and ticker adapters, with
  credential-safe configuration errors.

This is a US-first foundation. It does not yet include CNINFO/SSE/SZSE/BSE, OpenDART/KIND, issuer
calendars, filing-content event extraction, or event-triggered automated re-evaluation. See
[the v0.5 execution plan](docs/V0_5_PLAN.md).

The [v0.5.1 live-event gateway plan](docs/V0_5_1_PLAN.html) defines Jin10 MCP polling and Open
Platform WebSocket as two equal-priority live information channels. M0-M7 are implemented:

- typed signal/retention/action/bridge contracts and additive migrations 6/7/8;
- independent channel checkpoints, deterministic versions, single alerts, and frozen no-key replay;
- strict MCP initialization, structuredContent parsing, latest-page polling, 30/120/300 cadence,
  and a 1200-call local target below the documented 1500 per-tool daily limit;
- Open Platform flash/calendar/quote WebSocket auth, heartbeat, reconnect, and normalization;
- cross-channel overlap/divergence and P50/P95 delay metrics plus entity/theme/injection rules;
- rules-only and explicitly selected typed model analysis with visible failure/call lineage; and
- a supervisor, CLI/API/SSE, and responsive Cockpit Live Desk;
- confirmed official-source tasks, guarded capture, reviewed Evidence links, immutable run context,
  parent-preserving linked re-evaluations, and an audit timeline; and
- an isolated no-key chaos soak, read-only diagnostics, release runbook, and Research Bridge UI.

Run `capexgraph live demo` and then `capexgraph live status` to inspect the synthetic no-key path.
The MCP adapter has a real-provider smoke test. WebSocket live smoke still requires its separate
Secret-Key; without it the UI reports `WAIT KEY` rather than pretending to be connected. Aggregator
messages remain secondary signals and must pass through official capture and human review before
creating a separate Evidence link. The credentialed WebSocket live soak remains an external
acceptance gate until its Secret-Key is available; it is not reported as a passing or fallback
path.

## v0.4 development preview

The active v0.4 branch now contains the first market-data foundation slice:

- provider-neutral daily-history contracts with explicit exchange, currency, timezone, raw close,
  adjusted close, provider version, retrieval time, and source hash;
- optional EODHD history for US, Shanghai, Shenzhen, KRX, and KOSDAQ, with Beijing Stock Exchange
  reported as unsupported rather than returning an empty success;
- the existing Yahoo adapter as an explicit no-key fallback;
- deterministic checks for ordering, duplicates, OHLC validity, negative volume, adjusted-close
  validity, future dates, and staleness;
- idempotent SQLite bar storage and quality reports through schema migration 4; and
- CLI, API, run-snapshot, and forward-tracking integration.

Point-in-time theme membership, theme metrics, mainline policy, scheduling, and Cockpit views are
still pending. See [the v0.4 execution plan](docs/V0_4_PLAN.md) and
[market-data guide](docs/MARKET_DATA.md).

## Quick start

```powershell
.\scripts\bootstrap.ps1

.\.venv\Scripts\python.exe -m capexgraph.cli info
.\.venv\Scripts\python.exe -m capexgraph.cli demo
.\.venv\Scripts\python.exe -m capexgraph.cli demo-anchor
.\.venv\Scripts\python.exe -m capexgraph.cli demo-alphabet-q2
.\.venv\Scripts\python.exe -m capexgraph.cli serve
```

API documentation is available at `http://127.0.0.1:8000/docs`.

The demo commands need no API key. They execute frozen, public-source evidence packs and are
reproducible product demos, not current investment reports. `demo-alphabet-q2` replays the dated
Alphabet Q2 2026 AI CapEx acceptance case; its live-capture baseline and known gaps are documented
under `cases/alphabet_q2_2026/`.

### Model execution channels

CapexGraph never treats a compatible HTTP protocol as proof that authentication or billing is the
same. Each run explicitly selects one channel and keeps it for the lifetime of that run:

| Provider | Setup | Usage boundary |
| --- | --- | --- |
| `fixture` | none | bundled, frozen golden cases |
| `codex_subscription` | official local Codex CLI plus ChatGPT login | ChatGPT/Codex subscription pool |
| `openai` | OpenAI Platform API key | separately billed OpenAI API |

Inspect configuration without exposing credentials:

```powershell
capexgraph model providers
capexgraph model providers --probe-codex
```

For personal Codex-subscription execution, install the official Codex CLI and sign in with
ChatGPT. In the Cockpit, open **Connections**, select **Codex Subscription**, and click
**使用 ChatGPT 登录** if the account is not already available. No OpenAI Platform API key is
required. The same login can be prepared from a terminal:

```powershell
codex login
codex login status
```

The Connection Center discovers the models available to that account. An optional selection is
stored locally as `CAPEXGRAPH_CODEX_MODEL`; otherwise the Codex default is used. Then run:

```powershell
capexgraph theme "AI数据中心电力" --provider codex_subscription --execute
```

CapexGraph invokes `codex exec` in an ephemeral, read-only temporary workspace and validates the
final JSON against the requested Pydantic schema. Account discovery and browser login use the
official local Codex app-server; OAuth tokens remain owned by Codex and are never returned through
the CapexGraph API. A login, quota, execution, or schema failure is persisted on the selected run
and never falls back to the OpenAI API or fixture.

An existing CLIProxyAPI deployment remains available only as an advanced compatibility transport:
set `CAPEXGRAPH_CODEX_TRANSPORT=proxy`, keep it bound to loopback, and configure its base URL,
model, and separate proxy key. Remote proxy URLs still require the explicit
`CAPEXGRAPH_ALLOW_REMOTE_CODEX_PROXY=1` opt-in.

```dotenv
CAPEXGRAPH_CODEX_TRANSPORT=proxy
CAPEXGRAPH_CODEX_BASE_URL=http://127.0.0.1:8317/v1
CAPEXGRAPH_CODEX_PROXY_KEY=your-local-proxy-key
CAPEXGRAPH_CODEX_MODEL=the-model-slug-exposed-by-your-proxy
```

For the separately billed official OpenAI API channel:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,openai]"
$env:OPENAI_API_KEY = "..."
$env:CAPEXGRAPH_OPENAI_MODEL = "your-structured-output-capable-model"
.\.venv\Scripts\python.exe -m capexgraph.cli theme "AI数据中心电力" --provider openai --execute
```

`CAPEXGRAPH_MODEL` remains a legacy OpenAI-only fallback. It is never reused by the Codex
subscription channel.

Model-proposed sources remain `low` confidence until the source is captured, hash-verified, and
explicitly reviewed. The model cannot promote an unreviewed claim by wording it confidently.
Use `--evidence-mode strict` to block execution until a reviewed, unchanged capture exists; the
default `partial` mode may continue but preserves unsupported relationships at low confidence.

### SEC disclosure access (no API key)

SEC EDGAR metadata and Company Facts do not require an API key, but SEC requires automated clients
to identify the application and provide a real contact address. Put that identity in the
repository-local `.env`:

```dotenv
CAPEXGRAPH_SEC_USER_AGENT=CapexGraph research Your Name your-real-email@example.com
```

CapexGraph loads this file automatically for event discovery and filing facts. If SEC returns 403,
the command stops with a configuration instruction; it does not bypass the regulator's access
controls. Frozen demos and tests remain available without network access or credentials.

### Optional EODHD market provider

Keep the token only in the repository-local `.env` file:

```dotenv
EODHD_API_TOKEN=your-token
CAPEXGRAPH_MARKET_PROVIDER=eodhd
```

Then inspect public provider status and synchronize daily history:

```powershell
capexgraph market providers
capexgraph market sync 688019.SH AAPL 000660.KO --days 730
capexgraph market snapshot <run-id> 688019.SH
```

The token is read only by the Python backend. It is not returned by the API, written to manifests,
or embedded in source URLs. To use the no-key path explicitly, pass `--provider yahoo`; selecting
EODHD without a token fails clearly instead of silently changing providers.

### Web Cockpit

```powershell
.\scripts\dev.ps1
```

Open `http://127.0.0.1:5173`. Creating a workspace, discovering/capturing/reviewing sources, and
extracting SEC facts do not require a model key. The Cockpit shows all three model channels and
their credential-safe readiness state. **Connections** in the top bar is the product setup entry
for Jin10 MCP, Jin10 WebSocket, and the Codex subscription. It verifies MCP before saving, stores
provider secrets only in the ignored local `.env`, detects the official Codex login and available
models, and never returns a secret to the browser. Codex subscription execution requires the
official local Codex CLI and ChatGPT login;
OpenAI execution requires its separately billed API key. The Cockpit can run one durable stage at
a time, run all remaining stages, retry a failed checkpoint, inspect coverage and provider
failures, render the real graph, open the portable report, and manage forward tracking.

### Live event gateway

The frozen dual-channel replay and rules-only impact path need no provider or model key:

```powershell
capexgraph live demo
capexgraph live status
capexgraph live providers
capexgraph live soak --mode fixture --cycles 6 --failure-every 3
capexgraph live doctor
```

For real MCP polling, open **Connections → 金十 MCP**, paste the Bearer token, and choose
**连接并验证**. The backend completes MCP initialization plus tool/resource discovery before it
persists the value. The equivalent manual local `.env` configuration is:

```dotenv
JIN10_MCP_BEARER_TOKEN=your-bearer-token
CAPEXGRAPH_JIN10_MCP_CALL_BUDGET=1200
```

Then poll once or run the independent channel supervisor:

```powershell
capexgraph live poll --stream flash
capexgraph live poll --stream calendar
capexgraph live monitor
```

WebSocket uses an independent credential and remains equal priority after it is enabled. Save it
through **Connections → 金十 WebSocket**, or configure the same backend-only value manually:

```dotenv
JIN10_WEBSOCKET_SECRET_KEY=your-open-platform-secret-key
CAPEXGRAPH_JIN10_WS_FLASH_CATEGORIES=1,4
CAPEXGRAPH_JIN10_WS_CALENDAR_CATEGORIES=cj
```

The React Cockpit exposes Live Desk as its first navigation item. It shows MCP/WebSocket health
separately, reconnects its SSE stream, provides event/category/source filters, explains
matched/divergent lineage and delivery delay, supports no-key rules analysis, and records explicit
Watch/Dismiss/Mute actions. Its Research Bridge creates confirmed official-source tasks, captures
and reviews official material, links only unchanged reviewed Evidence, attaches immutable context,
creates parent-preserving child re-evaluations, and exposes the complete audit timeline. Provider
credentials are submitted once over the loopback API, are never put in browser storage, and never
appear in status/settings responses. Browser
notifications require a direct user opt-in.
See [the live event operator guide](docs/LIVE_EVENTS.md) for API contracts, retention, cursor
semantics, and troubleshooting, and [the live operations runbook](docs/LIVE_OPERATIONS.md) for
release gates, restart, recovery, and incident handling.

## Research artifact contract

Every run is stored under `runs/<run-id>/`:

```text
manifest.json       input, versions, providers, timestamps
state.json          resumable workflow state
graph.json          nodes, grounded edges, confidence
evidence.json       source ledger
coverage.json       deterministic review and failure coverage
sources.json        persistent discovery/capture queue
financials.json     source-linked comparison for Anchor Scan
financials/facts.json versioned filing-derived facts and source locators
financials/summary.json latest available facts and explicit missing metrics
market/<ticker>.json normalized bars, quality result, and snapshot
events.json         current corporate events and immutable version history
candidates.json     verdicts, risks, invalidation, triggers
decision.json       final structured decision
report.html         self-contained portable research report
checkpoints/        one durable artifact per completed/failed step
```

SQLite at `runs/capexgraph.db` is the local system of record. JSON artifacts remain human-readable
and portable. Set `CAPEXGRAPH_STATE_DB` to move the database.

SQLite schemas are versioned. Safe additive migrations run when a store opens; operators can
inspect and control the same path explicitly:

```powershell
capexgraph db status
capexgraph db backup --output .\backup\capexgraph.db
capexgraph db upgrade
# Stop the API before replacing an active database.
capexgraph db restore .\backup\capexgraph.db --force
```

See [the upgrade guide](docs/UPGRADING.md) before restoring or moving a workspace.

## Common commands

```powershell
# Research
capexgraph model providers --probe-codex
capexgraph theme "AI数据中心电力" --market CN --provider openai
capexgraph theme "AI数据中心电力" --market CN --provider codex_subscription
capexgraph sources add <run-id> <url> --title "Issuer filing"
capexgraph sources capture <run-id> <suggestion-id>
capexgraph evidence review <run-id> <evidence-id>
capexgraph run <run-id> --provider openai --evidence-mode strict
capexgraph theme "A股半导体硅片" --provider fixture --execute
capexgraph anchor "603986" --provider fixture --execute
capexgraph demo-alphabet-q2
capexgraph run <run-id> --provider openai --until graph
capexgraph resume <run-id>

# Live evidence and market data
capexgraph ticker resolve 兆易创新
capexgraph sources discover <run-id> --identifier GOOGL
capexgraph sources add <run-id> <url> --title "Issuer filing"
capexgraph sources capture <run-id> <suggestion-id>
capexgraph evidence collect <run-id> <url> --id filing-1 --title "Filing"
capexgraph evidence review <run-id> filing-1
capexgraph financials extract <run-id> --identifier GOOGL
capexgraph financials list <run-id>
capexgraph market providers
capexgraph market sync 688019.SH AAPL 000660.KO --days 730
capexgraph market snapshot <run-id> 603986 --provider eodhd

# Official disclosure events
capexgraph events sync <run-id> --identifier GOOGL --form 10-Q --form 8-K
capexgraph events list <run-id>
capexgraph sources capture <run-id> <suggestion-id>
capexgraph events list <run-id> --history
capexgraph events list <run-id> --as-of 2026-07-23

# Synthetic live-signal foundation (no provider or model key)
capexgraph live demo
capexgraph live status
capexgraph live demo --until 2026-07-29T02:06:00Z --path .\data\live-demo.db
capexgraph live status --path .\data\live-demo.db

# Forward tracking and reports
capexgraph tracking add <run-id> <node-id> --market-provider eodhd
capexgraph tracking snapshot <tracked-id> --live --market-provider eodhd
capexgraph tracking list
capexgraph report render <run-id>

# Database safety
capexgraph db status
capexgraph db backup --output .\backup\capexgraph.db
```

CapexGraph records candidate and benchmark prices on a common market date, then reports since-call
return, benchmark return, and arithmetic alpha. It does not backfill an imaginary call price from
later data.

## API surface

```text
POST /api/v1/runs/theme
POST /api/v1/runs/anchor
GET  /api/v1/runs
GET  /api/v1/runs/{id}
POST /api/v1/runs/{id}/execute
POST /api/v1/runs/{id}/resume
GET  /api/v1/runs/{id}/checkpoints
GET  /api/v1/runs/{id}/coverage
GET  /api/v1/runs/{id}/artifacts/{filename}
POST /api/v1/runs/{id}/sources/discover
POST /api/v1/runs/{id}/sources/suggest
GET  /api/v1/runs/{id}/sources
POST /api/v1/runs/{id}/sources/{suggestion-id}/capture
POST /api/v1/runs/{id}/financials/extract
GET  /api/v1/runs/{id}/financials
POST /api/v1/runs/{id}/events/discover
POST /api/v1/runs/{id}/events/refresh
GET  /api/v1/runs/{id}/events
GET  /api/v1/model/providers
GET  /api/v1/market/providers
POST /api/v1/market/sync
POST /api/v1/runs/{id}/market
POST /api/v1/runs/{id}/tracking
GET  /api/v1/tracking
POST /api/v1/tracking/{id}/snapshots
GET  /api/v1/runs/{id}/report
```

Theme Scan stages are `intake → census → graph → audit → score → debate → decision`. Anchor Scan
stages are `intake → cause → graph → audit → compare → debate → decision`. Every stage is resumable
and writes a durable checkpoint.

## Container

```powershell
docker compose up --build
```

This starts the API on `http://127.0.0.1:8000` and persists the SQLite workspace in a named volume.
The local Codex bridge is a native-local default. A container can reach a deliberately exposed
host bridge only through an explicit `host.docker.internal` configuration and the remote-proxy
opt-in; CapexGraph never changes that network boundary silently.

## Design principles

- **Agents judge; code verifies.** Prices, tickers, dates, calculations, and schema checks stay deterministic.
- **No relationship without provenance.** Medium/high-confidence graph edges require evidence IDs.
- **Runs are inspectable assets.** Intermediate outputs are preserved, not hidden behind a final report.
- **Research, not execution.** Live brokerage integration is intentionally outside the MVP.
- **Progressive setup.** Golden cases need no key; live model and premium data providers remain optional.

New contributors and coding agents should start with [AGENTS.md](AGENTS.md),
[current status](docs/CURRENT_STATUS.md), and the [roadmap](ROADMAP.md).

See [project context](docs/PROJECT_CONTEXT.md), [accepted decisions](docs/DECISIONS.md),
[v0.4 execution plan](docs/V0_4_PLAN.md),
[Theme Scan](docs/THEME_SCAN.md), [Anchor Scan](docs/ANCHOR_SCAN.md),
[live research tools](docs/LIVE_RESEARCH.md), [forward tracking](docs/MONITORING.md),
[MVP plan](docs/MVP.md), and [architecture](docs/ARCHITECTURE.md).

## Disclaimer

CapexGraph is for research and education only. It is not financial, investment, legal, or tax advice.
