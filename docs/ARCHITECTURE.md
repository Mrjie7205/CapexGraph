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

Provider interfaces prevent the workflow from depending on one model vendor. The built-in fixture provider loads a curated evidence pack and needs no key. The optional OpenAI provider uses structured Responses API output and is loaded only when selected.

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
`reviewed`. SEC discovery uses official EDGAR JSON and document URLs. User-supplied URLs enter the
same queue and are labeled issuer/regulator only when their domains match deterministic policy.
Canonical URLs and content hashes are deduplicated independently.

### Corporate event calendar

`CorporateEventVersion` is the durable v0.5 event contract. It separates the source-public
`known_at` timestamp from CapexGraph's `observed_at` timestamp and preserves announced, expected,
effective, occurred, and cancelled dates independently. All datetimes are timezone-aware UTC.

Event versions are append-only in SQLite migration 5. A semantic hash makes identical discovery
idempotent; a source revision, lifecycle change, or new Evidence link appends a version under the
same stable `event_key`. Current views select the latest version available by the requested system
observation cutoff. A document backfilled today therefore cannot appear in what an earlier run
actually knew.

The first mapper consumes SEC source suggestions. Periodic-report forms are labeled
`financial_report`; other forms stay `regulatory_filing` until captured content supports a more
specific event. Discovery remains separate from Evidence. When guarded capture succeeds, the event
calendar appends an evidence-linked version rather than upgrading the discovery row in place.
`events.json` is the portable current/history projection; the database remains authoritative.

Before live research, a deterministic context builder measures evidence coverage, verifies captured
hashes, loads bounded extracted source text, and loads bounded financial facts. The same context is
added to every Theme and Anchor prompt. Partial mode allows explicit gaps and downgrades unsupported
relationships. Strict mode fails at a durable checkpoint until reviewed evidence exists and rejects
unsupported medium/high relationship proposals.

### Filing facts

`FilingFactsProvider` separates official filing-data retrieval from normalization. The first
adapter captures SEC Company Facts JSON as Evidence and emits immutable `FinancialFact` objects.
Fact identities include period, accession, and value lineage. Restatements are appended, missing
metrics are explicit nulls, and derived free cash flow stores a formula and input fact IDs. SQLite
supports queryability; `financials/facts.json` preserves portability and exact JSON locators.

### Evidence trust boundary

```text
curated fixture       → schema validation → medium/high confidence allowed
model proposal        → schema validation → forced low confidence
captured source       → hash verification → explicit human review
reviewed model claim  → medium/high confidence may be preserved
```

An evidence ID proves provenance inside a run. `captured` means bytes were downloaded and hashed;
`reviewed` means a human approved that unchanged capture. It still does not make every possible
interpretation of the source true. Curated fixtures and claims backed entirely by reviewed captures
may preserve medium/high confidence.

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

The in-development schema version 4 adds normalized cross-market daily bars and hashed,
idempotent quality reports. It does not rewrite v0.3 run, checkpoint, tracking, source, or financial-fact
records.

Schema version 5 adds append-only corporate event versions. It is additive and does not rewrite
market bars, financial facts, source suggestions, tracking history, or run payloads.

### Applications

- FastAPI exposes runs, evidence review, official events, artifacts, market sync/status, tracking,
  and HTML reports.
- React/Vite provides the live Research Cockpit and stage board.
- CLI supports local, batch, tracking, and portable-report workflows.

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
