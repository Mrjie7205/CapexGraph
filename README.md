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
- three explicit model channels: no-key fixtures, a local Codex-subscription bridge, and the
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
Platform WebSocket as two equal-priority live information channels. Its M0/M1 development
foundation now includes typed signal/retention/action contracts, additive migration 6, independent
per-channel checkpoints, deterministic cross-channel versions, and a frozen no-key dual-channel
replay. Run `capexgraph live demo` and then `capexgraph live status` to inspect that synthetic path.

Real Jin10 MCP/WebSocket adapters, continuous polling, optional AI impact analysis, SSE, and the
Cockpit Live Desk remain planned work. The frozen fixture is not current market data. Future
aggregator messages remain secondary signals and must pass through official capture and human
review before becoming Evidence.

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
| `codex_subscription` | local CLIProxyAPI plus ChatGPT/Codex login | ChatGPT/Codex subscription pool |
| `openai` | OpenAI Platform API key | separately billed OpenAI API |

Inspect configuration without exposing credentials:

```powershell
capexgraph model providers
capexgraph model providers --probe-codex
```

For personal local Codex-subscription execution, keep CLIProxyAPI bound to loopback, give it a
separate local access key, and configure:

```dotenv
CAPEXGRAPH_CODEX_BASE_URL=http://127.0.0.1:8317/v1
CAPEXGRAPH_CODEX_PROXY_KEY=your-local-proxy-key
CAPEXGRAPH_CODEX_MODEL=the-model-slug-exposed-by-your-proxy
```

Then run:

```powershell
capexgraph theme "AI数据中心电力" --provider codex_subscription --execute
```

CapexGraph talks only to the proxy's Responses-compatible endpoint. It does not read or persist
ChatGPT OAuth files. Remote proxy URLs are rejected unless
`CAPEXGRAPH_ALLOW_REMOTE_CODEX_PROXY=1` is explicitly set. A proxy, authentication, quota, or
schema failure is persisted on the selected run and never falls back to the OpenAI API or fixture.

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
their credential-safe readiness state. Codex subscription execution requires the local bridge;
OpenAI execution requires its separately billed API key. The Cockpit can run one durable stage at
a time, run all remaining stages, retry a failed checkpoint, inspect coverage and provider
failures, render the real graph, open the portable report, and manage forward tracking.

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
