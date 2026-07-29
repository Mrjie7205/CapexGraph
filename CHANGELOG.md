# Changelog

All notable changes to CapexGraph are documented here.

## Unreleased

- added three explicit, non-fallback model channels: frozen fixtures, a local CLIProxyAPI-backed
  Codex subscription adapter, and the separately billed official OpenAI API;
- isolated model names and credentials per channel, enforced loopback-by-default proxy URLs,
  retained strict Responses/Pydantic parsing, disabled nested SDK retries, and categorized
  credential-safe provider failures;
- locked provider and model identity after execution starts, persisted transport/billing provenance
  plus model-call counts, and exposed redacted model readiness through CLI, API, Cockpit, and
  portable reports;
- approved and documented the v0.5.1 live-event gateway plan, including a frozen no-key event feed,
  equal-priority Jin10 MCP and Open Platform WebSocket channels, MCP-first real-data delivery with
  WebSocket co-development, cross-channel observation matching, deterministic filtering, optional
  AI impact analysis, Cockpit Live Desk flows, and explicit signal-versus-Evidence boundaries;
- implemented the v0.5.1 M0/M1 foundation with typed live observations, append-only signal
  versions, retention and verification states, per-channel checkpoints, redacted dead letters,
  human-gated action proposals, and additive schema migration 6;
- added a common live-source protocol, deterministic service/store, frozen synthetic MCP/WebSocket
  feeds with independent cursors and health, matched/divergent examples, and no-key `live demo` /
  `live status` CLI paths without claiming a real Jin10 connection;
- completed v0.5.1 M2 with a strict Streamable HTTP MCP client, standard negotiation, tool/resource
  discovery, structuredContent-only parsing, latest-page flash polling, calendar normalization,
  Beijing-day call budgets, 30/120/300 adaptive cadence, and credential-safe status;
- completed M3 with official Jin10 flash/calendar/quote WebSocket envelopes, Secret-Key auth,
  subscription, heartbeat, jittered reconnect, HTML sanitization, licensed-picture omission, and
  health/checkpoints independent from MCP; live smoke remains explicitly gated by the missing
  Secret-Key;
- completed M4 with deterministic relevance/urgency/importance/novelty and injection rules,
  editable entity/theme mappings, single canonical alerts, and overlap/channel-only/divergence plus
  P50/P95 delivery metrics;
- completed M5 with a no-key rules baseline and an explicit selective typed-model path that
  persists provider/model/prompt/call/failure lineage without silently presenting a failed model
  call as model output;
- added schema migration 7 for rule assessments, analysis records, alert delivery states,
  backend-owned Live Desk settings, and auditable user actions;
- completed M6 with the live supervisor, `live providers|poll|monitor`, the `/api/v1/live`
  status/events/coverage/settings/actions/SSE surface, and a responsive Live Desk with independent
  channel chips, no-key replay, filters, lineage, impact analysis, coverage audit, explicit browser
  notifications, and Watch/Verify/Dismiss/Mute actions;
- started the v0.5 official-event foundation with typed event taxonomy, lifecycle state,
  source-public/system-observed timestamps, effective/expected dates, and canonical entities;
- added append-only migration 5, semantic idempotency, immutable event versions, current/history
  views, and point-in-time queries;
- upgraded SEC submission discovery with acceptance timestamps, item metadata, and XBRL flags;
- mapped SEC periodic reports conservatively into financial-report events and other forms into
  regulatory-filing events without inferring document contents;
- linked successful guarded source capture by appending a new evidence-backed event version, and
  exposed the calendar through CLI, API, run manifests, and portable `events.json`;
- kept successful evidence capture authoritative if the downstream event projection fails, while
  recording a durable event-calendar error for explicit refresh;
- centralized repository `.env` loading across SEC, market, model, and ticker adapters, and made
  SEC 403 failures explain the required real-contact User-Agent configuration;
- started the v0.4 market-data foundation with provider-neutral bar, capability, quality, and sync
  contracts;
- added a credential-safe EODHD daily-history adapter for US, Shanghai, Shenzhen, KRX, and KOSDAQ,
  while preserving Yahoo as an explicit no-key fallback and reporting Beijing Stock Exchange as
  unsupported;
- preserved raw OHLC separately from adjusted close, added deterministic structural/staleness
  checks, and blocked failed data before normalized persistence;
- added schema migration 4, idempotent daily bars, hashed quality reports, ignored local raw
  responses, and overlapping incremental sync;
- connected provider selection and quality-checked history to CLI, API, run market snapshots, and
  forward tracking without exposing tokens; and
- approved and documented the v0.4 execution plan for EODHD-backed US/CN/KR daily history,
  market-specific quality gates, point-in-time theme membership, deterministic theme metrics,
  versioned mainline policy, scheduled monitoring, and linked re-evaluation;
- separated ETF/index/vendor recognition from evidence-backed industrial exposure and required
  effective/known time boundaries for historical theme universes; and
- reordered future milestones so cross-market official disclosures/events precede point-in-time
  consensus revisions, with Catalyst and Cockpit productization following afterward.

## 0.3.0 — 2026-07-27

- added a repository-owned cross-session handoff contract: agent guide, forward roadmap, project
  context, current status, accepted decisions, documentation drift checks, and PR checklist;
- clarified that Catalyst Scan is reserved/scaffolded rather than shipped;
- updated Theme Scan documentation for the M4 evidence capture and review boundary.
- added an Alphabet Q2 2026 AI CapEx acceptance case with first-party evidence manifests,
  normalized financial facts, a deterministic no-key replay, and an observed-defects report;
- added registry-backed Alphabet Class A and Class C ticker identities;
- preserved captured evidence hashes, local artifacts, and review status when a workflow reuses
  the same stable evidence identity;
- added frozen-response integration coverage that prevents aggregate CapEx or product mentions
  from becoming unsupported named-supplier claims.
- added Chinese report localization for Chinese subjects, including workflow labels, evidence
  states, confidence, financial metrics, units, risks, limitations, and disclaimers.
- added an execution-grade v0.3 plan covering dependency order, PR boundaries, acceptance tests,
  release gates, risks, and explicit exclusions.
- added versioned, checksummed SQLite migrations with automatic safe startup upgrades;
- added a frozen v0.2 legacy database fixture and regression coverage for runs, checkpoints,
  tracking snapshots, and trigger events;
- added consistent SQLite backup/restore plus `capexgraph db status|upgrade|backup|restore`.
- added a durable `SourceSuggestion` queue that keeps discovery results separate from Evidence;
- added SEC/EDGAR filing discovery and deterministic issuer/regulator URL suggestions;
- added canonical-URL and content-hash deduplication, persisted capture failures, safe redirect
  handling, and HTML/PDF content-type enforcement;
- added source discovery, capture, retry, dismissal, and extracted-text paths across CLI, API, and
  the Cockpit.
- added `partial` and `strict` evidence modes, deterministic coverage preflight, bounded captured
  source text in every Theme/Anchor prompt, and checkpointed strict-mode recovery;
- recorded model, source-discovery, market/evidence, and filing provider versions plus as-of date,
  coverage, pending review, and durable failure metadata in run manifests;
- prevented unreviewed/model-only relationship proposals from retaining medium/high confidence;
- added a frozen non-fixture Alphabet vertical proving reviewed source text and financial context
  reach the model without hand-editing run artifacts;
- added immutable, versioned SEC Company Facts across income, cash flow, and balance-sheet metrics,
  including restatements, explicit missing values, deterministic unit/period conflicts, and derived
  free cash flow with formula lineage;
- added financial-fact schema migration 3, raw SEC response evidence/hash capture, JSON source
  locators, CLI/API extraction, and Theme/Anchor context injection;
- added Cockpit create-first/no-key preparation, evidence-mode selection, one-stage pause,
  retry/resume, coverage and provider failures, filing-fact extraction/table, and report access;
- updated reports to expose providers, evidence coverage, fact provenance, reviewed facts,
  grounded inferences, unverified hypotheses, and coverage gaps; and
- aligned Python and Web versions to `0.3.0`.

## 0.2.0 — 2026-07-17

- added SSRF-safe HTML/PDF evidence capture, hashing, and explicit review;
- added deterministic A-share ticker identity and no-key market snapshots;
- added evidence-linked financial fact imports;
- added the seven-stage Anchor Scan with a frozen 兆易创新 golden case;
- turned the Cockpit into a live run, graph, evidence, and decision workbench;
- added candidate tracking, benchmark-relative scorecards, structured trigger events, and stage boards;
- added self-contained HTML research reports, Windows bootstrap, and container setup;
- expanded CI across supported Python versions and package builds.

## 0.1.0 — 2026-07-16

- initial domain model, SQLite run engine, resumable checkpoints, Theme Scan, API, CLI, and web shell.
