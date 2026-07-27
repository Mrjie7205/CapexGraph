# CapexGraph roadmap

This is the authoritative forward plan. `docs/MVP.md` is the completed v0.2.0 milestone history;
this file defines what comes next. Priorities may change only through an explicit product decision,
which must also update `docs/DECISIONS.md` and `docs/CURRENT_STATUS.md`.

## Current release

`v0.2.0` completes the first local, evidence-first vertical slice:

- Theme Scan and Anchor Scan;
- captured/reviewed evidence and deterministic research tools;
- resumable runs and a live Cockpit;
- candidate tracking, paired benchmark scorecards, and reports.

The immediate priority is not adding more agent personas. It is making non-fixture research as
trustworthy and repeatable as the golden cases.

## v0.3 — Trustworthy live research

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

## v0.4 — Continuous monitoring and re-evaluation

### Goals

1. Add scheduled or externally triggerable batch market snapshots.
2. Evaluate financial and operating triggers when new evidence-linked metrics arrive.
3. Build a durable event timeline: source update → trigger → acknowledgement → re-evaluation run.
4. Compare scorecards across runs, themes, benchmarks, and call cohorts.
5. Make invalidation and thesis changes explicit, dated analyst actions.

### Acceptance criteria

- Monitoring can run unattended through a documented command or job entry point.
- Duplicate snapshots and trigger events remain idempotent.
- A trigger can launch or propose a linked re-evaluation run without mutating the original run.
- The Cockpit explains the calculation window, baseline, benchmark, and missing observations.

## v0.5 — Catalyst Scan and cross-run graph memory

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

## v0.6 — Cockpit productization

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
must link back to the relevant goal and repeat its measurable acceptance criteria.

### Active executable queue

1. P0 — [#4 Add versioned SQLite migrations and backup/restore](https://github.com/Mrjie7205/CapexGraph/issues/4)
2. P0 — [#5 Build official-source discovery and evidence review queue](https://github.com/Mrjie7205/CapexGraph/issues/5)
3. P0 — [#6 Complete a live non-fixture Theme/Anchor vertical slice](https://github.com/Mrjie7205/CapexGraph/issues/6)
4. P1 — [#7 Normalize filing-derived financial facts with evidence lineage](https://github.com/Mrjie7205/CapexGraph/issues/7)
5. P1 — [#8 Add scheduled snapshots, trigger jobs, and re-evaluation links](https://github.com/Mrjie7205/CapexGraph/issues/8)
6. P1 — [#9 Implement Catalyst Scan beyond the reserved scaffold](https://github.com/Mrjie7205/CapexGraph/issues/9)
