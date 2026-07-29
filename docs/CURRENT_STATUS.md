# Current status

- Last verified: 2026-07-29
- Release: `v0.3.0` — Trustworthy live research
- Next target: `v0.4` — cross-market data foundation and mainline monitoring
- Active development branch: `codex/v0-4-data-foundation`

This is the short handoff for a new session. Verify it against code and tests when starting a
substantial change, and update it in the same pull request whenever shipped capability changes.

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

## Verified for the current v0.4 slice

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
  need no model key. A real OpenAI agent execution still requires `OPENAI_API_KEY` and
  `CAPEXGRAPH_MODEL`.
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
- The application is local-first and single-user. Cloud authentication and team permissions are not
  implemented.
- A running model call is not cancelled mid-stage. The Cockpit can execute one stage and pause at
  the next durable checkpoint.

## Start here next

Continue v0.4 from [the execution plan](V0_4_PLAN.md), in this order:

1. finish M1 frozen US/CN/KR/KOSDAQ comparisons, calendar/corporate-action checks, and one A-share
   enhancement/validation path;
2. add point-in-time theme definitions, memberships, and CN/US/KR historical imports;
3. implement deterministic theme metrics and an explicitly approved, versioned mainline policy;
4. add scheduled jobs, durable state changes, and linked re-evaluation; and
5. expose the completed path in the Cockpit and perform v0.4 release validation.

Cross-market official disclosures/events are v0.5, consensus revisions are v0.6, and Catalyst Scan
is now v0.7. Do not begin them merely because an enum, data vendor, or endpoint exists.
