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
