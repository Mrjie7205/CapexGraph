# Accepted decisions

This is an ADR-lite log for product and architecture decisions that future sessions must not reopen
accidentally. Add a new entry when a change alters a trust boundary, first-class object, provider
contract, repository boundary, or user workflow.

## D001 — Separate the skill and research system

- **Status:** accepted
- **Date:** 2026-07-16

`serenity-bottleneck-hunter` remains a self-contained, low-friction skill. CapexGraph is a separate
professional research workspace. Shared fact-correctness fixes may be applied to both, but there is
no runtime dependency, submodule, private path, or required dual installation.

## D002 — Workflow-driven, not agent-for-agent's-sake

- **Status:** accepted
- **Date:** 2026-07-16

Agents handle bounded judgment and analysis. Deterministic code handles identities, dates, prices,
calculations, persistence, schema validation, and cross-reference integrity. TradingAgents is a
product-shape reference, not an implementation target.

## D003 — Evidence status and claim confidence are separate

- **Status:** accepted
- **Date:** 2026-07-16

`proposed`, `captured`, `reviewed`, and `rejected` describe evidence lifecycle. They do not directly
state that a claim is true. Medium/high-confidence edges require evidence; unverified model claims
are forced low. A human-reviewed, unchanged capture may preserve a stronger claim, subject to edge
audit.

## D004 — Research runs are first-class, durable assets

- **Status:** accepted
- **Date:** 2026-07-16

Every workflow operates on a dated `ResearchRun` with manifest, provider identity, checkpoints,
typed state, and portable artifacts. Intermediate work remains inspectable. Resume skips completed
steps rather than regenerating them invisibly.

## D005 — Progressive setup is a product requirement

- **Status:** accepted
- **Date:** 2026-07-16

Golden cases and inspection paths must work without an API key. Model and premium data adapters are
optional. Professional capability may require configuration, but it must not remove the no-key path
or misrepresent fixtures as live analysis.

## D006 — Track paired baselines, never reconstructed calls

- **Status:** accepted
- **Date:** 2026-07-17

A tracking record stores the candidate and benchmark price on a common date. Later returns and
alpha are calculated from those baselines. CapexGraph does not infer a historical call price from
later market data. Trigger events are durable; acknowledgement does not erase history.

## D007 — SQLite for execution, JSON/HTML for portability

- **Status:** accepted
- **Date:** 2026-07-17

SQLite is the local system of record for queryable run and tracking state. JSON checkpoints and run
artifacts remain human-readable and portable. HTML reports are derived outputs, not a replacement
for typed state.

## D008 — Research infrastructure, not brokerage execution

- **Status:** accepted
- **Date:** 2026-07-17

CapexGraph may form research priorities, triggers, and invalidation states. It does not place orders,
manage a portfolio autonomously, or present model output as personalized financial advice.

## D009 — One versioned migration registry owns SQLite

- **Status:** accepted
- **Date:** 2026-07-27

Run and tracking stores no longer create their schemas independently. One ordered, checksummed
migration registry owns the whole SQLite workspace. Migrations are transactional and idempotent;
safe additive migrations may run on startup, while any migration marked non-automatic requires an
explicit operator upgrade. Backup and restore use SQLite's consistent backup API and restore never
overwrites an existing database without an explicit force flag.

## D010 — Discovery suggestions are not Evidence

- **Status:** accepted
- **Date:** 2026-07-27

Search and provider results are stored as `SourceSuggestion` objects with their own lifecycle:
`suggested → selected → capture_pending → captured`, with durable dismissal, failure, and duplicate
outcomes. A suggestion never becomes captured or reviewed merely because it came from SEC, an
issuer domain, a user, or a model. Successful guarded download creates a separate Evidence object;
human review remains a second explicit action. URL identity and downloaded-content identity are
deduplicated separately and neither operation silently overwrites an existing capture.

## D011 — Live prompts consume bounded run evidence

- **Status:** accepted
- **Date:** 2026-07-27

Every Theme and Anchor stage receives a deterministic, bounded context containing coverage,
captured/reviewed source text, and persisted financial facts. A model is not expected to infer
source contents from URLs. Partial mode may continue with gaps but unsupported relationships become
low confidence. Strict mode requires reviewed, hash-valid evidence and checkpoints unsupported
medium/high claims so the same run can resume after review.

## D012 — Filing facts are immutable evidence-linked versions

- **Status:** accepted
- **Date:** 2026-07-27

Official filing adapters capture their raw response as Evidence before normalized facts enter the
system of record. Every `FinancialFact` preserves period, unit, concept, filing identity, evidence
ID, and source locator. Restatements append a new value instead of overwriting history; missing is
null rather than zero; derived values declare formula and input fact IDs. Deterministic code, not an
agent, owns these validations.

## D013 — Market providers are complementary and quality-gated

- **Status:** accepted
- **Date:** 2026-07-29

EODHD is the optional cross-market daily provider for US, Shanghai/Shenzhen, KRX, and
KOSDAQ. It does not automatically replace a China-specialist provider: Tushare or another licensed
A-share adapter may remain primary or act as the semantic/quality reference for adjusted prices,
suspensions, limits, and local fields. Yahoo remains an explicit no-key fallback and demo path,
not a silent production default. Provider selection is configuration-driven; a missing EODHD token
is an explicit error rather than permission to change sources.

Raw OHLC, adjusted return price, volume adjustment, corporate actions, exchange, currency, source
version, and retrieval time must remain distinguishable. Every market default is gated by a frozen
independent comparison suite. Provider keys stay local, and licensed raw data is never committed
or redistributed through the public repository.

## D014 — Theme recognition and industrial exposure are separate axes

- **Status:** accepted
- **Date:** 2026-07-29

An index constituent, ETF holding, ETF creation basket, or vendor concept member is evidence of
market classification/recognition. It is not by itself evidence that the company has material
industrial exposure, nor that a supplier/customer relationship exists. Evidence-reviewed filings
and supply-chain relationships populate industrial exposure separately.

Theme membership is point-in-time and preserves both when a membership was effective and when the
system could have known it. CapexGraph must be able to surface high-exposure/low-recognition
companies; absence from an ETF cannot exclude a bottleneck lead.

## D015 — Data foundations precede broader automation

- **Status:** accepted
- **Date:** 2026-07-29

The approved release order is:

1. v0.4 cross-market daily history, point-in-time theme universes, deterministic theme metrics,
   versioned mainline policy, scheduling, and linked re-evaluation;
2. v0.5 official CN/US/KR disclosures, filing facts, and event calendars;
3. v0.6 point-in-time consensus revisions and expectation-aware regime analysis;
4. v0.7 Catalyst Scan and cross-run graph memory; and
5. v0.8 Cockpit productization.

Scheduling an unvalidated Yahoo-only, present-day-universe workflow is not treated as progress.
Mainline taxonomy and thresholds require a separate explicit product decision before they become
the default policy.

## D016 — v0.5 starts as an isolated official-event foundation

- **Status:** accepted
- **Date:** 2026-07-29

The user explicitly advanced development to v0.5 while v0.4 point-in-time theme membership,
mainline policy, scheduling, and Cockpit work remain incomplete. v0.5 may therefore implement
official-disclosure and event-calendar contracts, persistence, and standalone user paths in
parallel, but it cannot claim the missing v0.4 monitoring loop or silently couple events to an
unapproved mainline policy.

Corporate event history is append-only. `known_at` records when the official source made information
public; `observed_at` records when CapexGraph actually ingested it. Historical system queries use
`observed_at`, so a document backfilled today cannot appear in what an earlier run knew. Discovery
metadata remains a `SourceSuggestion`; only guarded capture creates Evidence, and linking that
Evidence appends a new event version instead of rewriting the discovery version.

## D017 — Live aggregators provide signals, not Evidence

- **Status:** accepted for the signal/Evidence boundary; channel-priority clause superseded by D019
- **Date:** 2026-07-29

The v0.5.1 live-event gateway uses three progressive provider paths: a frozen no-key feed for
deterministic demos and CI, Jin10 MCP as a quota-aware polling fallback, and Jin10 Open Platform
WebSocket as the preferred low-latency channel when a separate Secret-Key is configured. Provider
adapters normalize into one append-only `LiveSignalVersion` boundary, so switching or recovering
channels cannot change downstream analysis semantics or create duplicate alerts.

The original MCP-fallback/WebSocket-preferred ordering above is retained as decision history only
and must not guide implementation. D019 replaces that ordering with equal-priority channels while
leaving every signal-versus-Evidence rule in this decision intact.

A live aggregator message is a secondary market signal. It can be mapped to themes, entities,
existing graph nodes, and research runs; it can also trigger an official-source search or a linked
re-evaluation proposal. It is not `Evidence`, cannot become a `CorporateEventVersion` merely by
arrival, and cannot raise a supply-chain relationship to medium/high confidence. The existing
guarded capture, hash, and human-review path remains the only upgrade route.

AI event analysis is optional and cost-gated. Its typed output must show direction, horizon,
transmission path, price confirmation, evidence gaps, triggers, invalidations, model lineage, and
failure state. It may propose ignore, watch, verify, attach, or linked re-evaluation actions. A
human must explicitly accept any action that creates a run or changes research state; CapexGraph
does not place orders or manage positions.

## D018 — Model protocol, authentication, and billing are separate boundaries

- **Status:** accepted
- **Date:** 2026-07-29

CapexGraph keeps `fixture`, `codex_subscription`, and `openai` as three explicit research-model
providers. The Codex subscription provider may use an OpenAI-compatible Responses surface through
a loopback CLIProxyAPI bridge, but protocol compatibility does not make it the OpenAI Platform API:
it uses a separate local proxy credential, delegates ChatGPT OAuth to the proxy, and consumes the
operator's ChatGPT/Codex subscription boundary. The `openai` provider uses a Platform API key and
separate API billing. The fixture provider uses neither.

No provider silently falls back to another. Provider and model are locked after a run starts so
resumed stages cannot diverge from the durable manifest. Failures are categorized, retryability is
explicit, and only credential-safe details enter checkpoints, manifests, reports, API responses,
or the Cockpit. CapexGraph never reads or persists ChatGPT OAuth files. Remote subscription proxies
are rejected by default; an explicit opt-in does not weaken the operator's responsibility to secure
that endpoint.

## D019 — MCP and WebSocket are equal-priority live information channels

- **Status:** accepted; supersedes only the channel-priority clause in D017
- **Date:** 2026-07-29

Jin10 MCP polling and Jin10 Open Platform WebSocket are two formal, equal-priority information
channels. Delivery order is not trust order: MCP is the first channel connected to real data
because its Bearer access is already available, while the WebSocket adapter is developed in
parallel from the same provider-neutral contract. A missing Secret-Key blocks only WebSocket live
smoke. Once available, WebSocket joins MCP in continuous operation; neither channel is a fallback,
replacement, or automatic failover target for the other.

Each channel owns its credential, checkpoint, freshness, retry/backoff, quota or connection health,
and raw `SignalObservation`. The gateway matches overlapping observations into one canonical
`LiveSignalVersion` and one alert while preserving channel identity, published/observed timestamps,
field differences, revisions, and channel-only events. The Cockpit reports both channel states plus
overlap, P50/P95 delay, missing events, and revision differences. It must not claim content parity
until measured.

Channel failure changes only that channel's status. MCP quota pressure may reduce MCP cadence but
cannot disable or demote WebSocket; WebSocket disconnects may trigger its own reconnect and gap
state but cannot change MCP cadence or role. Cross-channel data can corroborate delivery and improve
coverage, but two aggregator observations still remain secondary signals. They do not satisfy the
official-source capture and human-review gate established by D017.

## D020 — Live polling is head-refresh, analysis is rules-first, and M6 stops before research mutation

- **Status:** accepted
- **Date:** 2026-07-29

Jin10 `list_flash` cursors page toward older history; they are not forward incremental cursors.
Continuous MCP operation therefore calls the un-cursored latest page on each cycle, relies on
stable external identities plus content hashes for local idempotency/revisions, and records the
returned `next_cursor` only for explicit historical backfill. Calendar observations separate the
scheduled publication time from when CapexGraph observed the current calendar row.

Every new signal version runs through a deterministic rules layer before an optional model. The
ruleset owns relevance, urgency, importance, novelty, entity/theme mapping, exclusions, injection
flags, and the single-alert decision. Model execution is explicit, threshold/cost gated, typed, and
audited; model failure is visible and cannot be labeled as model-generated output. Licensed
provider bodies default to metadata-only retention, HTML is sanitized, and picture URLs are not
hotlinked or persisted.

M6 may record reversible read/watch/verify/dismiss/mute/ignore actions and expose browser
notifications after explicit permission. It may not attach a signal as Evidence or create a linked
research run. Those state-changing bridges remain M7 and must pass through official-source capture,
human review, and explicit confirmation.

## D021 — M7 research mutation is explicit, append-only, and parent-preserving

- **Status:** accepted
- **Date:** 2026-07-30

M7 implements the state-changing bridge through dedicated verification-task, Evidence-link, and
run-context endpoints. Every write requires an explicit confirmation flag and appends an audit
entry. Generic live actions cannot attach Evidence or create linked re-evaluations, so callers
cannot bypass source authority, guarded capture, hash verification, or human review.

An official-source task may use a recognized regulator domain or an explicitly identified issuer
domain. A successful capture remains `captured` and cannot verify the signal. Only unchanged
`reviewed` Evidence can create a `LiveEvidenceLink`; rejection creates no link. Verification-state
changes append a `LiveSignalVersion` rather than rewriting the signal that originally arrived from
the aggregator.

Live context is stored as an immutable snapshot plus `context_hash`. Research context loading
recomputes the hash and omits a tampered snapshot. Attaching context to an existing run does not
change its prior artifacts. A linked re-evaluation creates a new child run with `parent_run_id` and
leaves the parent payload byte-for-byte unchanged. The live snapshot retains the trust class
`secondary_live_signal`; separately listed reviewed Evidence links are the only factual source
upgrade.

The deterministic fixture chaos/soak gate runs observations in an isolated temporary database and
persists only its bounded report. This prevents release testing from contaminating the operator's
current signal ledger. A credentialed provider soak requires both equal-priority channel
credentials; missing WebSocket access remains an explicit external live-smoke gate, not a passing
or fallback result.

## D022 — Local onboarding uses a one-way secret boundary and the official Codex transport

- **Status:** accepted; supersedes D018 only for the default Codex transport
- **Date:** 2026-07-30

CapexGraph exposes one product entry, Connection Center, for local single-user integrations. A
Jin10 secret may travel once from a password field to the loopback backend. It is never placed in
browser storage, returned by a GET/status response, embedded in a run, or written to logs. The
backend may atomically update only an allowlisted repository-local `.env` key. MCP credentials are
persisted only after a successful standard handshake plus tool/resource discovery; WebSocket
credentials remain visibly `live_probe_pending` until an authenticated monitor run proves the
stream. Disconnect remains an explicit destructive action.

The default `codex_subscription` transport is the official local Codex CLI, not a third-party
proxy. Account and available-model discovery plus browser login use the official Codex app-server.
Research execution uses ephemeral, read-only `codex exec` with a requested JSON schema and validates
the final result again with Pydantic. Codex owns ChatGPT OAuth storage; CapexGraph receives no OAuth
token and requires no OpenAI Platform API key for this channel. CLIProxyAPI remains an explicit
compatibility transport for existing users, bound to loopback by default.

No onboarding convenience changes the trust model: provider secrets unlock data/model transport,
not Evidence authority, and no model channel silently falls back to another.

## D023 — Alert delivery and the canonical event ledger have separate refresh semantics

- **Status:** accepted
- **Date:** 2026-07-31

The reconnectable SSE cursor represents durable alert delivery. It must not be broadened into an
implicit alert for every persisted signal: rules are allowed to retain a low-score signal without
creating `LiveAlertDelivery`. Live Desk therefore combines SSE readiness/alert notifications with
a server-paged canonical ledger refresh on relevant local or cross-tab operations, tab visibility,
and a bounded 30-second visible-tab interval.

Event totals and filtering are computed by the backend. Full detail records are assembled only for
the requested page with batched reads, so increasing history does not turn a list request into one
detail query per signal. `source_scope=live|fixture|mixed` is derived from observation retention
class. Channel names cannot identify a frozen replay because the synthetic fixture deliberately
uses MCP and WebSocket observations.

Cross-tab messages are coordination signals only. They contain a topic, random message ID, tab ID,
and timestamp; no provider credential, market payload, or research artifact may enter
BroadcastChannel or the localStorage notification fallback.

## D024 — v0.4 and v0.5 consolidate into the v0.5.1 pre-v0.6 baseline

- **Status:** accepted
- **Date:** 2026-08-03

The previously parallel market/theme/mainline, official-event, and live-gateway branches are one
local-first release boundary. Schema migrations remain additive and ordered through version 12;
there is no parallel database, identity registry, or second Cockpit. v0.6 builds on these contracts
instead of reopening them.

Release completion does not erase external operational gates. A provider implementation can ship
with truthful `not_configured`, `partial`, or `WAIT KEY` state when a real credential or entitlement
is unavailable. Frozen tests prove behavior, not live-provider availability.

## D025 — Mainline automation is deterministic, externally scheduled, and experimental by default

- **Status:** accepted
- **Date:** 2026-08-03

`mainline run-all` is the stable local scheduling boundary. It calculates and persists inputs,
metrics, quality, policy version, assessment, state transition, and job status without model cost.
CapexGraph does not install or own an operating-system scheduler; Windows Task Scheduler, cron, or
another operator-owned runner invokes the command after each market close.

The first conservative policy is intentionally marked `experimental`. Technical completion means
the classification is reproducible and auditable, not that its thresholds have been approved as a
production investment rule. Promotion requires an explicit product decision and a new effective
policy version; old assessments are never reinterpreted.

## D026 — Official metadata, reviewed Evidence, and financial facts remain separate layers

- **Status:** accepted
- **Date:** 2026-08-03

SEC, CNINFO, SSE, SZSE, BSE, OpenDART, and KIND discovery may create conservative event metadata.
It cannot by itself create a verified operating fact. A fact parsed from regulator or issuer text
must originate from a hash-verified, human-reviewed Evidence item, enter a durable candidate state,
and receive an explicit accept decision before becoming immutable `FinancialFact`.

Official structured APIs such as SEC Company Facts and OpenDART accounts retain their own response
hash, provider version, period, unit, and locator lineage. Unstructured extraction remains bounded
to deterministic allowlisted patterns and parseable report periods; a model cannot fill missing
numbers or approve candidates.

## D027 — v0.6 consensus history requires historical entitlement, not current-value backfill

- **Status:** accepted
- **Date:** 2026-08-03

Consensus revisions are point-in-time data. A provider that exposes only today's consensus may
support a current dashboard but cannot satisfy the v0.6 historical-revision contract. Every
adapter must declare historical depth, entitlement, permitted persistence, redistribution limits,
market/metric coverage, and timestamps before implementation.

The public repository may include only synthetic licensed-shaped fixtures. Theme aggregates must
show contributors, coverage, weighting, stale values, and normalization failures. Official actuals
remain Evidence-linked facts, and models cannot synthesize missing analyst estimates.

## D028 — Autonomous evidence review is a distinct, capped trust state

- **Status:** accepted
- **Date:** 2026-08-04

Starting the non-fixture Theme `graph` checkpoint authorizes a bounded automatic evidence pass. An
Agent may propose seed companies, select official sources, and independently review captures, but
deterministic code must verify market/ticker identity, regulator or issuer authority, guarded
downloads, raw-source and extracted-text hashes, limits, and literal supporting quotations. Every
capture receives an
outcome, and zero accepted sources stop graph execution visibly.

Automatic approval is stored as `agent_reviewed` with reviewer/provider/model/transport,
raw-source/text and prompt integrity, timestamp, rationale, quotations, and warnings. It never
produces or impersonates
human `reviewed`. Fully Agent-reviewed support may ground a relationship only up to medium
confidence; curated or unchanged human-reviewed support may retain high. Fixture runs remain the
no-key deterministic path and skip the bootstrap.

Official company identity remains authoritative after bootstrap. If the graph model returns a
different node ID or a bare six-digit ticker for the same company, deterministic canonicalization
must reuse the verified node and remap relationship endpoints rather than creating a duplicate.
