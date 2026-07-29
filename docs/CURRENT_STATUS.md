# Current status

- Last verified: 2026-07-29
- Release: `v0.3.0` — Trustworthy live research
- Active target: `v0.5` — official disclosure events, by explicit user priority
- Approved planned extension: `v0.5.1` — provider-neutral live-event gateway with equal-priority
  Jin10 MCP and Open Platform WebSocket channels, a frozen no-key feed, optional AI analysis, and
  a Cockpit Live Desk; MCP is first-live while WebSocket is co-developed; plan only, not implemented
- Incomplete dependency: `v0.4` — cross-market data foundation and mainline monitoring; the market
  slice exists, while theme/mainline automation remains open
- Active development branch: `codex/v0-5-official-events`

This is the short handoff for a new session. Verify it against code and tests when starting a
substantial change, and update it in the same pull request whenever shipped capability changes.

## Implemented on the v0.5 development branch

- three isolated model-execution channels: no-key fixtures, a loopback CLIProxyAPI
  `codex_subscription` adapter using the ChatGPT/Codex subscription boundary, and the separately
  billed official OpenAI API adapter;
- per-channel model configuration, strict Responses/Pydantic output, provider/model locking after
  execution starts, typed retry policy, credential-safe provider status in CLI/API/Cockpit, and
  manifest/report transport plus billing provenance without silent fallback;
- typed `CorporateEventVersion`, event taxonomy, lifecycle state, canonical entity, official source,
  effective/expected dates, `known_at`, and `observed_at`;
- append-only migration 5 and an idempotent event store with current, full-history, filter, and
  system point-in-time queries;
- SEC Submissions metadata upgraded with acceptance timestamp, item, and XBRL fields;
- conservative SEC mapping: periodic reports become `financial_report`; other forms remain
  `regulatory_filing` without guessing their business meaning;
- durable SourceSuggestion-to-event mapping, followed by a new evidence-linked event version when
  guarded source capture succeeds; a projection failure cannot erase a successful capture and is
  recorded for `events refresh` recovery;
- `events.json`, run-manifest coverage, and CLI/API discover, refresh, current, history, and
  `as_of` paths; and
- one shared project `.env` loader for market, SEC, model, and ticker configuration, with an
  actionable SEC 403 error that asks for a real contact address rather than bypassing access rules.

This is the first US official-source vertical, not a v0.5 release. CNINFO/SSE/SZSE/BSE, OpenDART,
KIND/KRX, issuer calendars, cross-market fact taxonomy, event-triggered re-evaluation, and the
Cockpit event view remain open. The detailed boundary is in `docs/V0_5_PLAN.md`.

The approved v0.5.1 live-event design is documented in `docs/V0_5_1_PLAN.html`. MCP polling and
WebSocket are equal-priority information channels: MCP is the first real-data runtime slice, the
WebSocket adapter is developed in parallel, and both remain active after the Secret-Key is
available. No live gateway, Jin10 adapter, signal schema, automatic AI event analysis, SSE stream,
or Live Desk has been implemented yet. A Jin10 signal remains a secondary discovery input and
cannot become Evidence without the existing guarded official-source capture and human-review path.

## Verified for the current v0.5 slice

- 78 Python tests pass and Ruff passes;
- the React/Vite production build passes;
- a clean isolated wheel build succeeds and contains `capexgraph.events` plus the shared
  configuration loader;
- fresh and legacy migration tests reach schema version 5 without rewriting prior run, checkpoint,
  source, financial-fact, market, or tracking records;
- frozen SEC tests cover acceptance timestamps, conservative form classification, idempotent
  discovery, capture-to-Evidence versioning, point-in-time history, CLI, API, and artifacts; and
- the official SEC schema was probed successfully with an identifying test User-Agent. A real
  project event sync is intentionally left blocked until the operator supplies
  `CAPEXGRAPH_SEC_USER_AGENT` with a real contact address; the repository does not invent one.

## Implemented on the v0.4 development branch

- provider-neutral `MarketBarSet`, capability, quality-result, and sync-result contracts;
- separate raw OHLC and adjusted close semantics, with raw prices used for displayed price/SMA/range
  and adjusted close used for returns;
- explicit EODHD mappings for US, Shanghai, Shenzhen, KRX, and KOSDAQ plus a clear unsupported
  Beijing Stock Exchange result;
- credential-safe EODHD retries/errors/source URLs and an explicit Yahoo no-key fallback;
- deterministic ordering, duplicate-date, OHLC, volume, adjusted-close, future-date, and staleness
  checks that block structurally failed data;
- migration 4 with idempotent normalized bars and hashed quality reports;
- ignored local raw-response retention, overlapping incremental updates, CLI/API sync, run snapshot,
  and forward-tracking integration; and
- public provider status that reveals only credential presence, never the token.

This is an M0/M1 vertical slice, not a v0.4 release. Frozen cross-provider comparison fixtures,
exchange-calendar/corporate-action checks, an A-share specialist validation adapter, M2 historical
theme membership, M3 mainline policy, M4 scheduling, and M5 Cockpit work remain open.

## Verified for the v0.4 foundation commit

- 69 Python tests pass and Ruff passes;
- the React/Vite production build passes;
- the local wheel builds and contains the complete `capexgraph.market` package;
- fresh and legacy databases reach schema version 4 without changing the legacy run, checkpoint,
  candidate, snapshot, or trigger-event counts;
- synthetic tests cover EODHD parsing, credential-safe failures, US/CN/KR/KOSDAQ mapping, explicit
  BSE rejection, quality blocking, idempotent storage, `.env` redaction, API status, and run
  snapshot integration; and
- an optional live EODHD smoke synchronized representative US, Shanghai, and KRX securities through
  the real service with `pass` quality through 2026-07-28 and credential-free source URLs.

## Shipped in v0.3.0

- one ordered, checksummed SQLite migration registry, including tested v0.2 legacy upgrades,
  consistent backup, verified restore, and three current schema versions;
- a persistent `SourceSuggestion` review queue, official SEC/EDGAR discovery, deterministic manual
  issuer/regulator URLs, canonical-URL and content-hash deduplication, durable failures, retry, and
  dismissal;
- SSRF-safe HTML/PDF capture, extracted text, SHA-256 provenance, and explicit human review;
- `partial` and `strict` evidence modes with a deterministic preflight and checkpointed recovery;
- bounded injection of captured/reviewed source text and filing facts into every Theme/Anchor stage;
- model, source, and data provider names and versions, as-of date, evidence policy, coverage, review
  backlog, and failures in each run manifest;
- code-enforced confidence gates: an unreviewed or model-only relationship cannot remain medium or
  high confidence;
- a frozen non-fixture Alphabet integration path that proves source text and facts reach model
  prompts, and that a strict failure resumes after review without editing JSON;
- a versioned `FinancialFact` contract and SEC Company Facts provider covering income statement,
  cash flow, and balance-sheet metrics;
- immutable restatement history, explicit missing values, unit/period conflict failures, and derived
  free cash flow with formula and input fact IDs;
- source locator, provider version, raw SEC response hash, financial-fact context, and report/UI
  presentation;
- a Cockpit create-first path that needs no model key for workspace creation, source discovery,
  capture, review, or SEC fact extraction;
- Cockpit coverage/failure states, checkpoint-at-a-time execution, retry/resume, financial-fact
  table, and portable report access;
- reports that separate reviewed facts, grounded inferences, unverified hypotheses, and coverage
  gaps; and
- preserved no-key semiconductor-wafer, 兆易创新, and Alphabet frozen replays, Chinese reporting,
  tracking, scorecards, and stage boards.

## Verified for v0.3.0

- 58 Python tests pass locally;
- Ruff passes;
- the React/Vite production build passes;
- the v0.2 legacy fixture upgrades to schema version 3 without changing run, checkpoint, candidate,
  snapshot, or trigger-event counts;
- the frozen Alphabet live vertical, restatement/missing/derived fact cases, and A-share golden
  regressions pass; and
- the package version is aligned across Python and Web;
- the `0.3.0` wheel contains filing providers, financial persistence, and fixtures;
- a clean Python environment installed the wheel, completed the no-key Theme golden run, and
  initialized schema version 3; and
- browser QA created an OpenAI/strict workspace with no key and confirmed `created` plus zero
  completed stages; it also verified coverage/readiness, financial-fact entry, portable-report
  sections, and visible persistence of a real SEC 403 provider failure.

GitHub CI passed for release PR #12 on Python 3.11, 3.12, 3.13, and the Web production build.
Future code or documentation changes must pass the same remote release gate again.

## Honest capability boundaries

- Catalyst Scan is only a scaffold. It has no research schemas, handlers, audit, golden fixture, or
  live execution path.
- Creating a workspace, collecting/reviewing sources, replaying fixtures, and extracting SEC facts
  need no model key. Live execution explicitly selects either a local
  `codex_subscription` bridge with its own proxy key/model or the separately billed OpenAI API with
  `OPENAI_API_KEY` and `CAPEXGRAPH_OPENAI_MODEL`; neither channel falls back to the other.
- The CLIProxyAPI adapter is source-contract and mock-transport verified. A real subscription call
  still requires the operator to install, authenticate, and run the third-party local proxy; this
  checkout does not bundle it or claim an official OpenAI support contract for that relay.
- CapexGraph does not autonomously browse the broad Web. Official discovery currently covers
  SEC/EDGAR plus user-supplied official URLs.
- Automatic filing facts currently cover a bounded US-GAAP metric set through SEC Company Facts.
  A-share exchange filings and taxonomy adapters are not implemented.
- `captured` verifies bytes and hash; `reviewed` records human approval of that capture. Neither
  status proves every interpretation in a report.
- Partial mode may produce a low-confidence `needs_review` report with explicit gaps. Strict mode
  requires at least one reviewed, hash-valid source and blocks unsupported medium/high claims.
- Yahoo Chart remains an unofficial, best-effort no-key market adapter, not a licensed production
  feed.
- EODHD daily history is implemented on the v0.4 development branch, but its independent frozen
  comparison suite and A-share semantic validation are not complete. Tushare, JQData, SEC N-PORT
  theme holdings, and KRX constituent adapters are still roadmap targets.
- CapexGraph has no point-in-time theme registry today. It cannot yet reconstruct which companies
  belonged to a theme using only information available on a historical date.
- ETF/index/vendor membership is planned as market-recognition evidence, not proof of industrial
  exposure or supplier/customer relationships.
- Monitoring remains manually invoked. Scheduling and automatic re-evaluation belong to v0.4.
- SEC filing metadata can now populate an event calendar, but content-level event extraction,
  issuer calendars, and CN/KR official sources are not implemented.
- The application is local-first and single-user. Cloud authentication and team permissions are not
  implemented.
- A running model call is not cancelled mid-stage. The Cockpit can execute one stage and pause at
  the next durable checkpoint.

## Start here next

Continue v0.5 from [the execution plan](V0_5_PLAN.md):

1. start v0.5.1 M0/M1 dual-channel contracts and frozen feed, then ship the MCP first-live M2
   while developing the WebSocket M3 adapter in parallel; the Secret-Key gates only live smoke,
   and the complete HTML plan is [here](V0_5_1_PLAN.html);
2. configure a real SEC contact User-Agent for optional live smoke, then add historical submission
   files and backfill;
3. add CNINFO plus Shanghai/Shenzhen/Beijing official announcement discovery;
4. add OpenDART and KIND/KRX official disclosure paths;
5. normalize cross-market filing facts and evidence-linked event extraction; and
6. connect events to monitoring proposals and the Cockpit without fabricating the unfinished v0.4
   mainline policy.

The remaining v0.4 work stays recorded in [its execution plan](V0_4_PLAN.md) and must be resumed
before CapexGraph can claim automated daily mainline monitoring.

Cross-market official disclosures/events are the explicit active v0.5 target. Consensus revisions
remain v0.6 and Catalyst Scan remains v0.7; do not start those later milestones merely because an
enum, data vendor, or endpoint exists.
