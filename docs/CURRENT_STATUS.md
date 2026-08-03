# Current status

- Last verified: 2026-07-31
- Release: `v0.3.0` — Trustworthy live research
- Active target: `v0.5` — official disclosure events, by explicit user priority
- Active extension: `v0.5.1` — provider-neutral live-event gateway with equal-priority Jin10 MCP
  and Open Platform WebSocket channels; M0 through M7 are implemented in code, including real MCP
  polling, the WebSocket protocol/worker, reconciliation/rules, optional AI analysis, API/SSE,
  Cockpit Live Desk/Research Bridge, official-source/Evidence/run integration, audit, diagnostics,
  release gates, and a productized Connection Center for Jin10/Codex onboarding. The credentialed
  WebSocket live soak remains an external acceptance gate until a Secret-Key is available
- Incomplete dependency: `v0.4` — cross-market data foundation and mainline monitoring; the market
  slice exists, while theme/mainline automation remains open
- Active development branch: `codex/v0-5-1-live-event-gateway`

This is the short handoff for a new session. Verify it against code and tests when starting a
substantial change, and update it in the same pull request whenever shipped capability changes.

## Implemented on the v0.5.1 development branch (M0-M7)

- typed `SignalObservation`, append-only `LiveSignalVersion`, channel/match/retention/verification
  states, independent `LiveProviderCheckpoint`, redacted dead letters, and human-gated
  `ResearchActionProposal` contracts;
- additive migration 6 for observations, canonical signal versions and their links, per-channel
  checkpoints, dead letters, and research-action proposals;
- a provider-neutral `LiveEventSource` protocol and deterministic `LiveSignalService` that preserves
  every channel observation, emits `single_channel`, `matched`, or `divergent` signal versions, and
  does not let one channel failure change the other channel's checkpoint or health;
- a frozen synthetic Jin10-shaped MCP/WebSocket fixture with a controllable clock, independent
  cursors, identical and divergent cross-channel examples, and deterministic replay; and
- no-key `capexgraph live demo` and `capexgraph live status` commands for replaying and inspecting
  the persisted foundation without presenting fixture events as current market information;
- a strict Jin10 Streamable HTTP MCP client using `initialize` → initialized notification →
  tools/resources discovery → tool calls, with `structuredContent` as the only machine-data
  source, latest-page polling, cursor metadata, Beijing-day budget reset, and 30/120/300-second
  adaptive cadence;
- a Jin10 Open Platform WebSocket adapter for flash, calendar, and optional quotes, including the
  official connected/auth/subscribe envelopes, ping/pong heartbeat, jittered reconnect, independent
  health/checkpoint state, and a visible no-key `NOT_CONFIGURED` state;
- additive migration 7 for deterministic rule assessments, typed analysis lineage, single-alert
  delivery state, Live Desk settings, and auditable user actions;
- deterministic relevance, urgency, importance, novelty, injection, entity/theme, cooldown, and
  single-alert rules, plus overlap, channel-only, divergent, P50, and P95 coverage metrics;
- a rules-only no-key impact-analysis baseline and an explicitly selected/cost-gated model path
  with typed output, prompt hash, provider/model/call lineage, and visible failure state without
  silent model fallback;
- `live providers|poll|monitor` CLI paths and `/api/v1/live` status, polling, monitor, event,
  coverage, settings, action, analysis, and reconnectable SSE endpoints; and
- a responsive Live Desk with independent channel chips, filters, lineage/detail, coverage audit,
  settings, explicit browser notifications, rules/model analysis selection, and human
  Watch/Dismiss/Mute actions;
- a productized Connection Center reachable from the top bar and Live Desk, with verify-before-save
  Jin10 MCP setup, independent WebSocket setup, redacted status, explicit disconnect, runtime
  refresh, and no secret in browser storage or GET responses;
- official Codex CLI account/model discovery and ChatGPT browser login through the official
  app-server, plus ephemeral read-only schema-bound `codex exec` for subscription analysis without
  an OpenAI Platform API key; strict schema normalization and disabled plugin/catalog loading keep
  that subprocess bounded and deterministic;
- immediate `live.ready` SSE delivery, truthful `WAIT KEY` channel cards when formal credentials
  are absent, and bounded CN/US/KR Market selection in the research composer;
- additive migration 8 plus typed verification tasks, reviewed Evidence links, immutable run
  context links, durable bridge audit entries, and bounded soak reports;
- `LiveResearchBridge` with explicit confirmation on every mutation, regulator/issuer source
  authority checks, guarded capture/retry, captured-versus-reviewed separation, source-hash
  integrity, approve/reject behavior, and append-only verification-state signal versions;
- existing-run context attachment and new linked Theme/Anchor runs, including child re-evaluation
  with `parent_run_id` while preserving the parent run payload;
- dedicated API endpoints and a synthesized audit timeline across observations, signal versions,
  analyses, actions, Evidence links, and run links; generic attach/linked actions remain blocked so
  callers cannot skip the bridge;
- `live soak` with duplicate replay, alternating one-channel failure, checkpoint-isolation and
  recovery checks in an isolated temporary database, plus `live doctor`, persisted reports, and
  the operations/recovery runbook; and
- a responsive Research Bridge with four-stage status, official-source capture and human review,
  immutable run operations, explicit confirmations, and audit history.
- a Chinese-first Cockpit language system across the research composer, workflow, graph, source
  queue, readiness, Live Desk, Connection Center, settings, and Research Bridge: operating labels
  and machine states are Chinese, while compact English sublabels preserve product and audit
  vocabulary; native selectors use Chinese-first option text, and the bridge Market control is
  bounded to CN/US/KR instead of accepting free text.
- a paged canonical event ledger with filtered totals, load-more, formal/fixture/mixed provenance,
  score/theme/entity/alert filtering, batched sub-second page assembly at the current local scale,
  and automatic visibility/interval synchronization for non-alert signals; and
- credential-free cross-tab synchronization for connection and monitor state so multiple open
  Cockpit tabs converge without reload.

This completes M0 through M7 in code and makes the branch release-ready; it does not merge, tag, or
publish a release. The current checkout has no Jin10 WebSocket
Secret-Key, so the WebSocket transport is protocol/mock verified and visibly reports `WAIT KEY`;
it is not claimed as live-connected. The fixture chaos/soak gate passes; the credentialed
MCP/WebSocket soak is implemented but correctly refuses to pass until both equal-priority channel
credentials exist.

## Implemented on the v0.5 development branch

- three isolated model-execution channels: no-key fixtures, the official local Codex CLI
  `codex_subscription` adapter using the ChatGPT/Codex subscription boundary, and the separately
  billed official OpenAI API adapter; CLIProxyAPI remains an explicit compatibility transport;
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

The approved v0.5.1 design is documented in `docs/V0_5_1_PLAN.html`. MCP polling and WebSocket are
equal-priority information channels with separate loops, checkpoints, health, and credentials.
MCP is live-verified; WebSocket becomes live-active when its independent Secret-Key is configured.
A Jin10 signal remains a secondary discovery input and cannot become Evidence without the existing
guarded official-source capture and human-review path.

## Verified for the current development slice

- the official Codex subscription path completed a real `gpt-5.6-sol` call through an authenticated
  ChatGPT subscription on 2026-07-30 and passed the requested Pydantic output contract;
- the v0.5.1 closeout on 2026-07-31 repeated the real integrated path: Connection Center reported
  MCP and Codex ready, a bounded MCP monitor run grew the canonical ledger from 407 to 427, both
  open Cockpit tabs updated automatically, and one formal storage-related signal completed a
  one-call Codex subscription analysis whose structured proposal appeared in Research Bridge
  audit history;
- the productized connection flow was browser-verified at desktop and 390px width: Codex account
  and models load, missing Jin10 credentials remain `WAIT KEY`, SSE becomes `CONNECTED`
  immediately, and the Market selector exposes exactly CN/US/KR without horizontal overflow;
- the Chinese-first interface was browser-verified at desktop and 390px width across the landing
  composer, Live Desk, connection onboarding, gateway settings, Research Bridge, dynamic run and
  evidence states, with English retained only as compact secondary vocabulary;
- 123 Python tests pass locally and Ruff passes;
- the React/Vite production build passes;
- a fresh wheel build includes `capexgraph.events`, the complete
  `capexgraph.live` package, both adapters, the synthetic dual-channel fixture, and shared
  configuration loaders;
- fresh and legacy migration tests reach schema version 8 without rewriting prior run, checkpoint,
  source, financial-fact, market, official-event, or tracking records;
- frozen live-gateway tests cover timezone enforcement, retention, independent checkpoints and
  failure health, idempotency, matched/divergent/single-channel versions, redacted dead letters,
  human-gated actions, and the no-key CLI path;
- Jin10 frozen transport tests cover standard MCP negotiation, structuredContent precedence,
  historical cursor semantics, daily budget exhaustion, all official WebSocket envelopes,
  authentication/subscription, calendar/quote normalization, reconnect health, HTML sanitization,
  and licensed-picture omission;
- rule/analysis/API tests cover single alerts, cross-channel coverage and delay, rules-only and
  typed model paths, visible model failure, settings, SSE resume IDs, user actions, verification
  confirmation, official-source approval/rejection, immutable linked runs, context integrity,
  audit, fixture chaos/soak, and no-key diagnostics;
- a real MCP smoke on 2026-07-29 negotiated all eight documented tools and `quote://codes`, then
  normalized 20 latest flash observations and 269 calendar observations with both streams active;
- desktop and 390-pixel browser QA verified the no-key replay, SSE connection, matched/divergent
  display, rules analysis, backend-only credential boundary, responsive settings/Research Bridge,
  four-stage workflow, audit timeline, and no horizontal overflow or console errors;
- desktop and 390-pixel closeout QA verified formal/fixture source badges, filtered totals,
  50-to-100 load-more pagination, theme filtering, automatic all-signal refresh, and cross-tab
  start/stop convergence without horizontal overflow;
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
  need no model key. Live execution explicitly selects either the official local Codex CLI with a
  ChatGPT login or the separately billed OpenAI API with `OPENAI_API_KEY` and
  `CAPEXGRAPH_OPENAI_MODEL`; neither channel falls back to the other.
- Codex subscription execution still requires a locally installed official Codex CLI and an
  eligible authenticated ChatGPT account. The Connection Center can start the official browser
  login but never receives OAuth tokens. CLIProxyAPI is compatibility-only and retains its
  loopback/explicit-opt-in security boundary.
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
- Mainline/theme monitoring remains manually invoked. Its scheduling and automatic re-evaluation
  belong to v0.4 and are not made complete by the separate live-event supervisor.
- The v0.5.1 gateway can continuously poll Jin10 MCP and run an independent WebSocket worker,
  persist/reconcile events, serve SSE, and expose the Live Desk. MCP needs its Bearer token;
  WebSocket needs a separate Secret-Key. Rules-only analysis and frozen replay need neither.
- The current checkout has no WebSocket Secret-Key, so only its frozen protocol and reconnect
  tests are verified. Browser notifications require explicit user opt-in, and licensed raw
  provider bodies/pictures are not archived or exported.
- SEC filing metadata can now populate an event calendar, but content-level event extraction,
  issuer calendars, and CN/KR official sources are not implemented.
- The application is local-first and single-user. Cloud authentication and team permissions are not
  implemented.
- A running model call is not cancelled mid-stage. The Cockpit can execute one stage and pause at
  the next durable checkpoint.

## Start here next

Continue v0.5/v0.5.1 from [the execution plan](V0_5_PLAN.md):

1. when a WebSocket trial Secret-Key is available, run the implemented credentialed MCP/WebSocket
   soak and record the result; until then keep `WAIT KEY` and do not call WebSocket live-connected;
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
