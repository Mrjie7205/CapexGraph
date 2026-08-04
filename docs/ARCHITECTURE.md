# CapexGraph architecture

CapexGraph separates probabilistic research from deterministic verification.

```text
Web / CLI / Python API
        ↓
Research workflow (Theme / Anchor; Catalyst reserved)
        ↓
Specialist agents sharing typed state
        ↓
Evidence, market, financial, and validation tools
        ↓
Run store → graph → candidates → tracking → scorecard
```

## Layers

### Domain

Stable Pydantic contracts for runs, companies, evidence, graph edges, candidates, triggers, and verdicts. Agent prose never becomes the system of record without passing these contracts.

### Workflow

Resumable state machines coordinate research stages. SQLite is the system of record for runs and checkpoints; each step also writes a portable JSON artifact. An interrupted or failed run skips completed checkpoints when resumed.

Theme Scan plugs Theme, Universe, Chain, Evidence, Bottleneck, Debate, and Research Manager
agents into the persistence contract. Anchor Scan substitutes identity, repricing-cause, neighbour,
and financial-comparison specialists. Every agent returns a Pydantic model; deterministic code
validates references and materializes domain objects and artifacts.

Theme and Anchor are the implemented research workflows. Catalyst exists only as a reserved enum
and pipeline scaffold so its future artifact shape can remain compatible; it must not fall through
to runtime-only scaffold handlers and be presented as completed research.

### Tools and providers

Provider interfaces prevent the workflow from depending on one model vendor or confusing a shared
wire protocol with a shared authentication and billing boundary. Theme and Anchor expose three
explicit model channels:

```text
fixture             → bundled outputs                    → no credential or usage
codex_subscription  → official Codex CLI / codex exec   → ChatGPT OAuth and subscription pool
openai              → official Responses API            → Platform API key and API billing
```

The two live adapters share typed structured-output contracts, but their configuration, provider
identity, error state, and usage boundary are separate. A selected channel never falls back to
another. The default subscription path discovers the official local Codex CLI, reads account/model
readiness through the official app-server, and runs schema-bound reasoning with ephemeral
`codex exec`. Codex owns ChatGPT OAuth storage; CapexGraph receives neither OAuth tokens nor API
keys. CLIProxyAPI remains an explicit compatibility transport, loopback-only unless the operator
opts into a secured remote endpoint.

A run records provider, adapter version, model, transport, authentication mode, billing mode,
endpoint scope, and model-call count before or during its first checkpoint. The provider and model
are then locked for that run. Resume may reuse completed checkpoints and retry the same channel,
but must not execute later stages under a different identity while retaining an older manifest.
Provider errors are typed as configuration, authentication, unavailable, rate-limit, protocol, or
output-validation failures. Only retryable failures consume the workflow retry budget; SDK-level
automatic retries are disabled.

Tools own ticker identity, market prices, financial facts/imports, SSRF-safe public source
retrieval, content hashing, and report rendering. The market-data boundary has two current
adapters: optional licensed EODHD for normalized US/CN/KR daily history and Yahoo as an explicit
no-key fallback. Both return one `MarketBarSet`; raw OHLC remains separate from adjusted close.
Provider capability declarations expose coverage and license boundaries without exposing
credentials.

`MarketDataService` writes the raw response to the ignored local runtime, runs deterministic
quality checks, blocks structurally invalid data, and idempotently upserts accepted bars and
quality reports into SQLite. Run snapshots consume this same path instead of bypassing the gate.
Forward tracking also uses it before pairing candidate and benchmark dates. See
[`MARKET_DATA.md`](MARKET_DATA.md) for ticker mappings, adjustment semantics, and remaining M1
limits.

Source discovery has its own trust boundary. `SourceSuggestion` records a provider result, official
domain classification, reason, and queue state. It is not Evidence. Only a successful guarded
capture creates `Evidence(status=captured)`; explicit human approval is still required for
`reviewed`. The Theme graph bootstrap may instead create distinct `agent_reviewed` Evidence only
after ticker-matched regulator/issuer discovery, guarded capture, independent model review, and
literal verification of quotations bound to separate raw-source and extracted-text hashes. SEC
discovery uses official EDGAR JSON and document
URLs. User-supplied URLs enter the same queue and are labeled issuer/regulator only when their
domains match deterministic policy. Canonical URLs and content hashes are deduplicated
independently.

### Live signal gateway

The v0.5.1 gateway is deliberately separate from both official events and
Evidence. Each provider delivery becomes a `SignalObservation` with its own channel, external ID,
published/observed timestamps, content hash, and retention class. `LiveSignalService` preserves
those observations and appends a `LiveSignalVersion` when a second channel, revision, or content
variant changes the canonical view. A match therefore emits one current signal without erasing
channel-only, delay, or divergent-content history.

`LiveEventSource` is the common boundary for frozen, MCP, and WebSocket sources. Checkpoints are
keyed by provider, channel, and stream; health, cursor, freshness, and call budget remain
independent. A failed source can degrade only its own checkpoint. Raw validation failures enter a
metadata-only dead-letter record containing a hash and safe schema errors, not the unlicensed or
potentially sensitive payload.

M0-M7 now provide three executable paths. The frozen, controllable-clock feed preserves a no-key
replay. `Jin10McpClient` performs strict Streamable HTTP negotiation and consumes only
`structuredContent`; flash uses repeated latest-page reads with local idempotency because the
provider cursor pages backward through history. A Beijing-day call target and adaptive cadence
protect quota. `Jin10WebSocketWorker` independently authenticates/subscribes to flash, calendar,
and optional quote streams, uses protocol heartbeat plus jittered reconnect, and never changes MCP
health or cadence.

Every new signal version receives an immutable rules assessment. The L0 gate maps configured
entities/themes, scores relevance/urgency/importance/novelty, flags prompt-injection patterns, and
creates at most one alert per signal key. Coverage is calculated from preserved observations,
including channel-only counts, matched/divergent state, and P50/P95 delivery delay. Optional model
analysis is a separately selected L1 path; typed outputs, model/provider, prompt hash, call count,
and failures are persisted. A model failure leaves a visible failed analysis and a rules baseline,
not a falsely model-authored proposal.

`LiveGatewayRuntime` supervises independent MCP and WebSocket loops. The API exposes state,
poll/start/stop, events, coverage, settings, analysis, actions, and reconnectable SSE. Live Desk
consumes that surface. Connection Center is the local onboarding boundary: it submits a secret
once to the loopback backend, verifies MCP before persistence, atomically updates only an
allowlisted ignored `.env` setting, rebuilds the affected runtime, and returns status without the
secret. Browser storage and GET responses never contain provider credentials. A `signal_only`
record still cannot become Evidence or an official corporate event without guarded capture and
human review.

The durable SSE cursor belongs to alert delivery, not to every canonical signal. Signals below the
alert threshold still persist and appear through the paged `/api/v1/live/events/page` ledger.
Live Desk synchronizes that ledger on SSE readiness, local/cross-tab operations, visibility
changes, and a bounded 30-second visible-tab interval. Page filtering and totals are server-side;
full records are assembled only for the requested page through batched store reads.

Open Cockpit tabs coordinate connection and monitor changes through a browser message containing
only a topic, random message ID, tab ID, and timestamp. BroadcastChannel is paired with a
localStorage notification fallback, but no credential, provider payload, or research artifact is
stored there. Formal versus frozen provenance is derived from observation retention class, not
from the MCP/WebSocket channel name, because the frozen dual-channel replay intentionally exercises
both formal channel contracts.

`LiveResearchBridge` implements that explicit M7 boundary. A confirmed verification task moves the
signal to `official_source_pending` through a new signal version. Regulator or explicitly identified
issuer URLs enter the existing source queue; guarded capture remains `captured` until a human
reviews the unchanged hash. Approval creates a separate `LiveEvidenceLink` and a new
`evidence_linked` signal version. Rejection creates no link.

Run integration uses `LiveRunContextLink`: a bounded immutable snapshot, trust class, content hash,
and optional reviewed Evidence links. Context loading recomputes the hash and excludes a tampered
snapshot. A linked re-evaluation creates a new child `ResearchRun` with `parent_run_id`; it does not
mutate the parent's payload or artifacts. Dedicated audit rows plus synthesized observation,
signal, analysis, and action entries form the event timeline. `LiveSoakRunner` exercises duplicate
replay, one-channel failure isolation, and recovery in an isolated temporary database, then
persists only its bounded report.

### Point-in-time themes and mainline monitoring

`ThemeDefinition`, `ThemeSource`, and `ThemeMembership` form a bitemporal registry. Valid dates
describe when membership applies; known dates describe when CapexGraph could have used it.
`ThemeUniverseSnapshot` freezes the selected membership and its input hashes for one market date.
Recognition sources and Evidence-backed industrial exposure are separate typed fields.

`MainlineService` calculates deterministic market metrics from that snapshot and persists the
inputs before applying a versioned `MainlinePolicy`. Assessments and state transitions are
append-only. `run_batch` isolates failures and is safe to invoke from an external scheduler;
duplicate theme/market/date/policy jobs are idempotent. State changes and official events may create
human-gated `ThemeResearchProposal` rows, but they do not run a model or mutate research by default.

### Corporate event calendar

`CorporateEventVersion` is the durable v0.5 event contract. It separates the source-public
`known_at` timestamp from CapexGraph's `observed_at` timestamp and preserves announced, expected,
effective, occurred, and cancelled dates independently. All datetimes are timezone-aware UTC.

Event versions are append-only in SQLite migration 5. A semantic hash makes identical discovery
idempotent; a source revision, lifecycle change, or new Evidence link appends a version under the
same stable `event_key`. Current views select the latest version available by the requested system
observation cutoff. A document backfilled today therefore cannot appear in what an earlier run
actually knew.

Official source adapters cover SEC, CNINFO, SSE, SZSE, BSE, OpenDART, and KIND. Periodic-report
forms/titles are labeled `financial_report`; generic filings stay `regulatory_filing` until
captured content supports a more specific event. Discovery remains separate from Evidence. When
guarded capture succeeds, the event calendar appends an evidence-linked version rather than
upgrading the discovery row in place. `events.json` is the portable current/history projection;
the database remains authoritative.

Before live research, a deterministic context builder measures evidence coverage, verifies captured
hashes, loads bounded extracted source text, and loads bounded financial facts. The same context is
added to every Theme and Anchor prompt. Partial mode allows explicit gaps and downgrades unsupported
relationships. For a live Theme run, strict mode defers its first evidence gate until the automatic
graph bootstrap; other paths still fail early without reviewed Evidence. Both paths reject
unsupported medium/high relationship proposals, and Agent-only support remains capped at medium.

### Filing facts

`FilingFactsProvider` separates official filing-data retrieval from normalization. SEC Company
Facts and a conservative OpenDART account subset capture official responses as Evidence and emit
immutable `FinancialFact` objects.
Fact identities include period, accession, and value lineage. Restatements are appended, missing
metrics are explicit nulls, and derived free cash flow stores a formula and input fact IDs. SQLite
supports queryability; `financials/facts.json` preserves portability and exact JSON locators.

For unstructured regulator/issuer disclosures, deterministic extraction creates
`DisclosureFactCandidate` rows only from hash-verified reviewed Evidence and parseable report
periods. Human acceptance creates the immutable fact; rejection remains durable audit state.

### Evidence trust boundary

```text
curated fixture       → schema validation → medium/high confidence allowed
model proposal        → schema validation → forced low confidence
captured source       → hash verification → explicit human review
human reviewed claim  → medium/high confidence may be preserved
Agent reviewed claim  → model/prompt/hash/exact-quote lineage → at most medium confidence
```

An evidence ID proves provenance inside a run. `captured` means raw bytes and extracted review text
were separately hashed; `reviewed` means a human approved that unchanged material. `agent_reviewed`
records an independent
Evidence Review Agent, provider/model/transport, source and prompt hashes, timestamp, rationale,
exact quotations, and warnings. It never impersonates human review. None of these states makes
every possible interpretation of the source true. Curated fixtures and claims backed entirely by
human-reviewed captures may preserve high confidence; Agent-reviewed support stops at medium.

### Forward tracking

Tracking tables share the SQLite workspace while remaining separate from immutable run artifacts.
A tracked candidate stores the original call date, candidate price, benchmark price, thesis,
invalidation text, and structured triggers. Later paired snapshots calculate return and alpha.
Trigger events are append-only and acknowledgement never deletes event history.

### Database lifecycle

One ordered migration registry owns both research-run and tracking schemas. Every applied migration
records its version, name, checksum, and timestamp in `schema_migrations`. Fresh databases and
unversioned v0.2 databases reach the same schema through transactional, idempotent migrations.
Only migrations marked safe for startup may run automatically; explicit upgrade, consistent backup,
and verified restore are available through the CLI. A failed migration rolls back only its own
transaction and never stamps a version that did not complete.

Schema version 4 adds normalized cross-market daily bars and hashed,
idempotent quality reports. It does not rewrite v0.3 run, checkpoint, tracking, source, or financial-fact
records.

Schema version 5 adds append-only corporate event versions. It is additive and does not rewrite
market bars, financial facts, source suggestions, tracking history, or run payloads.

Schema version 6 adds live observations, append-only canonical signal versions and their links,
independent provider/channel checkpoints, redacted dead letters, and human-gated action proposals.
It is additive and does not modify prior research, market, official-event, or tracking history.

Schema version 7 adds immutable rules assessments and analysis lineage, one canonical alert-delivery
record per signal key, persisted Live Desk settings, and append-only user actions. It is additive
and does not reinterpret prior observations, signals, Evidence, events, runs, or tracking history.

Schema version 8 adds official-source verification tasks, reviewed live-to-Evidence links,
immutable run-context links, bridge audit entries, and soak reports. It is additive and does not
rewrite prior observations, signals, Evidence, events, runs, financial/market facts, or tracking
history.

Schema version 9 adds point-in-time theme definitions, sources, memberships, and universe
snapshots. Version 10 adds daily theme metrics, policies, assessments, state events, monitor jobs,
and human-gated proposals. Version 11 adds cross-provider market comparison results. Version 12
adds reviewed disclosure-fact candidates. All remain additive and preserve earlier records.

### Applications

- FastAPI exposes runs, evidence review, official events/fact candidates, themes, mainline jobs,
  market sync/comparison, tracking, HTML reports, live gateway/SSE, Research Bridge, audit,
  diagnostics, and soak-report surfaces.
- React/Vite provides the Chinese-first Research Cockpit, Mainline Desk, official source/event
  queue, responsive Live Desk/Research Bridge, and stage board.
- CLI supports research, theme imports, mainline batch monitoring, official events/facts, market
  comparison, tracking, portable reports, synthetic replay, real MCP polling, and the equal-
  priority live supervisor plus deterministic soak and local diagnostics.

## Runtime lifecycle

```text
created → running → needs_review
              ↘ failed → resume → running
```

Each execution receives a bounded automatic retry budget. Manual resume grants a fresh retry budget
but preserves the lifetime attempt count and all completed checkpoints. The Cockpit may execute
through only the next step, which provides a user-visible pause at a durable checkpoint rather than
attempting to interrupt a provider call mid-stage.

## Repository boundary

CapexGraph is independent from the existing Serenity skill and private research repository. Useful ideas or fixes may be copied deliberately, but there is no runtime dependency, submodule, or automatic data sync.
