# CapexGraph roadmap

This is the authoritative forward plan. `docs/MVP.md` is the completed v0.2.0 milestone history;
this file defines what comes next. Priorities may change only through an explicit product decision,
which must also update `docs/DECISIONS.md` and `docs/CURRENT_STATUS.md`.

## Current release

`v0.3.0` completes the trustworthy live-research vertical slice:

- versioned database upgrades and recovery;
- official SEC source discovery and review queues;
- evidence coverage, strict/partial execution, and source text in agent context;
- immutable SEC filing facts with source locators and formula lineage;
- provider/failure visibility and the complete create → source → review → facts → research → report
  Cockpit path; and
- preserved no-key fixtures, resumable runs, tracking, scorecards, and reports.

The user has explicitly advanced active development to the isolated v0.5 official-event foundation
after the first v0.4 market-data slice. Point-in-time theme universes and mainline monitoring remain
incomplete dependencies; starting event contracts does not waive them or make automatic
re-evaluation production-ready. The user has also approved a scoped `v0.5.1` live-event gateway:
Jin10 MCP polling and Open Platform WebSocket are equal-priority information channels with
independent checkpoints and health. MCP is the first real-data runtime slice while the WebSocket
adapter is developed in parallel; once credentials are available, both continue running and feed
cross-channel observation matching. Frozen events preserve the no-key path. This extension may
create research and re-evaluation proposals, but it does not complete the missing v0.4 mainline
policy. The product sequence remains:

1. market history and historical theme membership;
2. official disclosures, filing facts, and event calendars;
3. point-in-time consensus revisions; and
4. richer Catalyst and cross-run graph workflows.

## v0.3 — Trustworthy live research ✅

详细实施顺序、交付物、测试矩阵和Definition of Done见
[`docs/V0_3_PLAN.md`](docs/V0_3_PLAN.md)。`ROADMAP.md`仍是里程碑范围和优先级的最终
依据，执行计划不得扩大到v0.4或v0.5能力。

### Goals

1. Add database schema versioning and migrations before evolving persisted runs and tracking data.
2. Add official-source discovery adapters and a review queue without weakening SSRF controls.
3. Complete a live, non-fixture Theme/Anchor path that captures sources before stronger claims.
4. Normalize filing-derived financial facts with traceable period, unit, and evidence lineage.
5. Expose provider failures, incomplete coverage, and review requirements clearly in the Cockpit.

### Acceptance criteria

- A new user can run one non-fixture Theme or Anchor subject without editing JSON artifacts.
- Every downloaded source has a URL, retrieval time, content hash, local artifact, and status.
- No model-only claim can become medium/high confidence.
- Run manifests record model, data providers, versions, as-of date, and evidence policy.
- SQLite upgrades preserve existing v0.2.0 runs and scorecards through tested migrations.
- At least one official-filing live case has a reproducible integration test with network calls
  replaced by frozen responses.

Completed in `v0.3.0`; the execution record and test matrix remain in
[`docs/V0_3_PLAN.md`](docs/V0_3_PLAN.md).

## Cross-cutting model-channel isolation

The active development branch now keeps three model execution channels explicit:

1. `fixture` for frozen no-key demos and regression tests;
2. `codex_subscription` for a personal loopback CLIProxyAPI bridge using the operator's
   ChatGPT/Codex subscription boundary; and
3. `openai` for the separately billed official OpenAI Platform API.

The channels share typed research schemas but never share credentials, model settings, billing
identity, fallback, or durable provider records. A run locks its provider and model when execution
starts. CLI, API, Cockpit, manifests, failures, and reports expose the actual channel without
returning secrets. The local relay is an optional adapter, not a dependency for fixtures, evidence,
market data, official events, or the OpenAI API path.

## v0.4 — Cross-market data foundation and mainline monitoring

Detailed execution order, provider boundaries, data contracts, tests, and Definition of Done are in
[`docs/V0_4_PLAN.md`](docs/V0_4_PLAN.md).

### Goals

1. Replace the Yahoo-only live path with a provider-neutral daily market-data layer:
   - optional EODHD for one normalized US/CN/KR path;
   - optional China-specialist adapters for A-share semantics and validation; and
   - the existing no-key provider and frozen fixtures as explicit fallback/demo paths.
2. Add point-in-time `ThemeDefinition`, `ThemeMembership`, and `ThemeUniverseSnapshot` contracts.
3. Keep two different concepts separate:
   - market recognition from indices, ETF holdings/baskets, and vendor concept lists; and
   - evidence-backed industrial exposure from filings and the supply-chain graph.
4. Backfill or import auditable historical membership sources for CN, US, and KR without pretending
   that one ETF or vendor taxonomy is the universal definition of a theme.
5. Calculate deterministic theme momentum, relative strength, breadth, persistence, dispersion,
   and data-quality metrics from the membership known at each observation date.
6. Add scheduled or externally triggerable daily jobs, durable mainline-state changes, and linked
   re-evaluation proposals.
7. Preserve provider, license, adjustment, freshness, and missing-data visibility in CLI, API,
   artifacts, and the Cockpit.

### Acceptance criteria

- With an EODHD token configured locally, one command can normalize and persist daily history for
  representative US, Shanghai/Shenzhen, KRX, and KOSDAQ securities.
- Removing every premium key still leaves frozen data-quality tests, golden runs, and inspection
  paths working; no secret or licensed raw dataset is committed.
- Raw close, adjusted close/return price, corporate-action semantics, exchange, currency, provider
  version, retrieval time, and source hash remain distinguishable.
- A provider cannot become the default for a market until its frozen comparison suite documents
  duplicate dates, missing sessions, stale observations, corporate actions, and close-price
  differences against an independent reference.
- A theme can be reconstructed `as_of` a historical date without using a membership or source that
  became known later.
- ETF/index/vendor membership contributes to `recognition`; it does not by itself prove industrial
  exposure or a supplier/customer relationship.
- The system can surface a high-exposure/low-recognition company as a bottleneck lead even when it
  is absent from the selected ETF.
- A versioned mainline policy produces inspectable inputs and state changes; its taxonomy and
  thresholds must be explicitly approved before becoming a default product policy.
- Monitoring runs unattended through a documented entry point; duplicate bars, universe snapshots,
  daily metrics, and trigger events remain idempotent.
- A state change can propose or launch a linked re-evaluation run without mutating the original.
- The Cockpit explains provider coverage, theme sources, calculation windows, benchmarks, missing
  observations, and why a theme changed state.

## v0.5 — Cross-market disclosures, filing facts, and event calendar

Detailed implementation order and the current SEC-first boundary are in
[`docs/V0_5_PLAN.md`](docs/V0_5_PLAN.md).

### Goals

1. Add official discovery/capture adapters for:
   - CNINFO and the Shanghai, Shenzhen, and Beijing exchanges;
   - SEC/EDGAR and issuer IR sources; and
   - OpenDART plus KRX/KIND.
2. Extend filing facts beyond the current bounded SEC Company Facts path with market-specific
   taxonomy and period normalization.
3. Add a typed, durable event calendar for earnings, guidance, dividends, splits, index changes,
   lock-up expiry, investor days, capex/production milestones, and other evidence-linked events.
4. Preserve scheduled, announced, revised, occurred, cancelled, and source-known dates separately.
5. Feed new official evidence and facts into monitoring triggers and linked re-evaluation proposals.

### Acceptance criteria

- At least one frozen official-source vertical works for each of CN, US, and KR.
- Every event has a source, observed-at timestamp, effective/expected date, lifecycle state, and
  canonical entity.
- Filing/event updates append versions and never rewrite what an earlier run knew.
- Missing official coverage remains visible and cannot be silently filled with model prose.
- Licensed aggregators remain optional accelerators; official captures remain the evidence anchor.

### v0.5.1 planned extension — live event gateway

The complete product, architecture, frontend, operation, delivery, and test plan is the standalone
HTML artifact [`docs/V0_5_1_PLAN.html`](docs/V0_5_1_PLAN.html).

Goals:

1. Add a provider-neutral live-event gateway with three executable paths:
   - a frozen no-key event stream for deterministic demos and tests;
   - Jin10 MCP adaptive polling, delivered first with cursor and daily-call-budget protection; and
   - Jin10 Open Platform WebSocket, co-developed from the same contract for `flash`, `calendar`,
     and permitted quote subscriptions.
   MCP and WebSocket are equal-priority production channels, not primary and fallback. Enabling or
   recovering one never disables, demotes, or changes the schedule of the other.
2. Normalize live aggregator messages into append-only `LiveSignalVersion` records that remain
   separate from official `CorporateEventVersion` and Evidence. Preserve each channel arrival as a
   `SignalObservation`, then match overlapping observations without erasing source, delay, revision,
   or field differences.
3. Apply deterministic deduplication, revisions, relevance, entity/theme mapping, novelty, cooldown,
   retention policy, and prompt-injection controls before optional model analysis.
4. Generate typed, conditional `ResearchActionProposal` outputs with direction, horizon, impact
   path, confidence, price confirmation, evidence gaps, triggers, and invalidations.
5. Add a Cockpit Live Desk with connection health, event stream, filters, event detail, AI analysis,
   official-source tasks, and explicit user actions to ignore, watch, attach, or launch linked
   re-evaluation.

Acceptance criteria:

- WebSocket reconnect and MCP polling/recovery have independent frozen deterministic tests. A
  disconnected, stale, or quota-constrained channel is shown as degraded without changing the
  other channel's priority, cadence, or health.
- Cross-channel matching emits one canonical alert while preserving all observations. The product
  reports overlap, channel-only events, revision/field differences, and P50/P95 delivery delay
  instead of claiming that MCP and WebSocket content are identical.
- Provider credentials stay backend-only and licensed raw data is never committed or exported.
- No-key fixtures and rules-only analysis remain useful without Jin10 or model credentials.
- A Jin10 signal cannot become Evidence or raise a relationship to medium/high confidence without
  the existing guarded official-source capture and human-review path.
- Model analysis is optional and cost-gated; failures, provider/model versions, prompt hashes, and
  retries remain visible.
- The Live Desk works on desktop and narrow layouts, shows MCP and WebSocket state independently,
  exposes channel coverage, delivers matched updates through SSE, and requires an explicit human
  action before creating a linked run or research action.
- The extension creates research priorities and conditional plans only. It does not place orders,
  manage positions, or claim the unfinished v0.4 mainline policy is production-ready.

## v0.6 — Consensus revisions and expectation-aware regime analysis

### Goals

1. Add provider-neutral point-in-time analyst estimate and revision contracts.
2. Track current consensus plus 1/4/12-week changes, upward/downward revision breadth, analyst count,
   actual-versus-consensus surprise, and post-event price reaction.
3. Aggregate revisions by point-in-time theme universe without letting large constituents or
   changing coverage silently dominate the result.
4. Distinguish a fundamentally improving theme from one whose positive result was already expected.
5. Add estimate freshness, provider coverage, currency/period normalization, and revision lineage.

### Acceptance criteria

- A historical query returns only estimates that were available at that historical timestamp.
- Current consensus is never presented as a historical series when prior snapshots are unavailable.
- Every aggregate exposes contributor count, coverage ratio, weighting rule, and stale observations.
- A frozen licensed-shaped fixture proves revision, surprise, and breadth calculations without
  redistributing vendor data.
- Mainline reports distinguish price confirmation, fundamental evidence, and expectation change.

## v0.7 — Catalyst Scan and cross-run graph memory

### Goals

1. Implement Catalyst Scan beyond the current pipeline scaffold.
2. Model event timeline, transmission path, exposed nodes, scenarios, and invalidation.
3. Introduce canonical entity/evidence identities across runs without rewriting immutable artifacts.
4. Reuse reviewed evidence through versioned references and revalidate it when source hashes change.
5. Add cross-run graph and candidate comparison in web, CLI, and Python interfaces.

### Acceptance criteria

- Catalyst Scan has typed outputs, audit coverage, deterministic validation, golden fixture, and
  live-provider path.
- The API and README advertise Catalyst only after those tests pass.
- Cross-run reuse preserves which run saw which evidence version and when.

## v0.8 — Cockpit productization

### Goals

- split the current single-page UI into maintainable run, evidence, graph, tracking, and report
  modules;
- add searchable run/report libraries and side-by-side comparison;
- improve accessibility, responsive behavior, empty/error states, and long-running job feedback;
- provide a supported local deployment and an optional authenticated deployment profile; and
- document backup, restore, migration, and data-provider configuration.

### Acceptance criteria

- A non-developer can complete the core loop entirely in the Cockpit.
- API authentication, if enabled, is explicit and does not break local single-user setup.
- Backup and restore are covered by an automated test.

## v1.0 — Stable research contract

- stable versioned run, evidence, graph, tracking, and provider interfaces;
- documented migration and compatibility policy;
- benchmark evaluation for evidence precision, relationship audit coverage, and reproducibility;
- supported extension contract for model, source, filing, and market-data providers;
- threat model, deployment guide, observability, and release checklist; and
- multiple independently reproduced public golden cases.

## Explicit non-goals

- brokerage order execution;
- autonomous portfolio management;
- hidden or unverifiable scoring;
- copying private Serenity research data into this repository;
- becoming a generic social/news terminal; and
- adding agent roles that do not improve evidence quality or user decisions.

## Execution order

GitHub Issues carrying the `roadmap` label are the executable queue. Within a release, complete
`priority:P0` items before `priority:P1` unless the user explicitly changes the order. Each issue
must link back to the relevant goal and repeat its measurable acceptance criteria. Until the v0.4
milestone issues are created, the ordered milestones in `docs/V0_4_PLAN.md` are the approved local
execution queue.

### Active executable queue

1. Completed in v0.3 — [#4 versioned SQLite migrations and backup/restore](https://github.com/Mrjie7205/CapexGraph/issues/4)
2. Completed in v0.3 — [#5 official-source discovery and evidence review queue](https://github.com/Mrjie7205/CapexGraph/issues/5)
3. Completed in v0.3 — [#6 live non-fixture Theme/Anchor vertical slice](https://github.com/Mrjie7205/CapexGraph/issues/6)
4. Completed in v0.3 — [#7 filing-derived financial facts with evidence lineage](https://github.com/Mrjie7205/CapexGraph/issues/7)
5. Completed slice — v0.4 M0/M1: the first EODHD/quality/persistence vertical slice is implemented;
   frozen comparisons, exchange/corporate-action checks, and an A-share validation adapter remain.
6. Completed first slice — v0.5 M0 and the initial M1 SEC vertical: append-only event contracts,
   official filing discovery, Evidence-linked versions, point-in-time queries, CLI/API, and
   artifacts pass the local release gate; SEC history backfill and a contact-identified live smoke
   remain.
7. Paused dependency P0 — v0.4 M2: point-in-time theme registry and historical membership.
8. Paused dependency P1 — v0.4 M3/M4/M5, including [#8 scheduled snapshots, trigger jobs, and re-evaluation links](https://github.com/Mrjie7205/CapexGraph/issues/8).
9. Next v0.5 P0 — CNINFO/SSE/SZSE/BSE, then OpenDART/KIND official disclosure adapters.
10. Deferred to v0.7 — [#9 Catalyst Scan beyond the reserved scaffold](https://github.com/Mrjie7205/CapexGraph/issues/9).
