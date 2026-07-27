# Current status

- Last verified: 2026-07-27
- Release: `v0.2.0` alpha
- Main release commit: `ca2fe8f`
- Next target: `v0.3 — Trustworthy live research`

This file is the short handoff for a new session. Verify it against code and tests when starting a
substantial change, and update it in the same pull request whenever shipped capability changes.

## Shipped

- durable SQLite research runs, bounded retries, JSON checkpoints, and resume;
- complete Theme Scan and Anchor Scan typed workflows;
- frozen no-key semiconductor-wafer and 兆易创新 golden cases;
- optional OpenAI structured-output provider;
- SSRF-safe HTML/PDF capture, content hashing, and explicit evidence review;
- deterministic A-share ticker identity, Yahoo chart snapshots, and normalized financial imports;
- FastAPI endpoints and a React/Vite Cockpit with background execution and polling;
- dynamic run graph, evidence ledger, candidate queue, and decision display;
- tracked call/benchmark baselines, subsequent snapshots, alpha, trigger events, and stage board;
- self-contained HTML reports, Windows bootstrap, Docker configuration, and wheel release.

## Unreleased v0.3 work

- merged the Alphabet acceptance baseline through PR #11 after all Python-version and Web CI passed;
- added a dated Alphabet Q2 2026 AI CapEx frozen replay and first-party live-capture case;
- added registry-backed `GOOGL` and `GOOG` identities;
- preserved captured hash/review metadata when deterministic replay reuses the same evidence
  identity; and
- added Chinese HTML report rendering for Chinese subjects, including evidence-linked financial
  metrics; and
- recorded the live baseline and remaining defects in
  `cases/alphabet_q2_2026/ACCEPTANCE_REPORT.md`.
- added a unified, versioned SQLite migration registry with checksums, transactional rollback,
  idempotent safe startup upgrades, and a frozen v0.2 legacy database fixture;
- added `db status`, `db upgrade`, consistent backup, and verified restore commands; and
- verified that a v0.2 database preserves its run, checkpoint, tracked candidate, snapshot, and
  trigger-event counts after upgrade.
- added a persistent source-suggestion queue with SEC/EDGAR discovery and a deterministic manual
  issuer/regulator URL path;
- added canonical-URL and content-hash deduplication, persisted discovery/capture failures, retry,
  dismissal, and guarded redirect handling; and
- exposed the source queue and extracted evidence text in CLI, API, and the Cockpit.

This does not complete the v0.3 live vertical slice. Automatic filing extraction,
financial-fact prompt/report integration, and autonomous non-fixture execution remain open.

The M1 migration slice has targeted regression coverage; the full release matrix is rerun at each
milestone and before release.

## Verified at v0.2.0

- 30 Python tests passed locally;
- Ruff passed;
- production Vite build passed;
- Python 3.11, 3.12, 3.13, and Web GitHub CI passed;
- the `0.2.0` wheel was built and its fixtures/tracking modules were inspected;
- API and Web dev servers returned healthy responses; and
- a CLI tracking smoke test recorded +12% candidate return, +4% benchmark return, and +8% alpha,
  then rendered an HTML report.
- after adding the repository handoff contract, the full suite contains 32 passing tests, including
  two checks that enforce required context files, version alignment, and Catalyst/M3 boundaries.

Docker was not available on the development machine, so the image configuration was added and
reviewed but not built locally.

## Honest capability boundaries

- Catalyst Scan is only a scaffold. It has no research schemas, handlers, audit, golden fixture, or
  live execution path.
- The OpenAI provider returns structured outputs but does not autonomously search or fetch official
  sources. URLs must be captured and reviewed through the evidence tools.
- Official-source discovery currently covers SEC/EDGAR and deterministic user-supplied URLs. It
  does not promise automatic A-share exchange search or broad web/news discovery.
- Yahoo Chart is an unofficial, best-effort no-key adapter, not a licensed production feed.
- Financial data is attached through normalized evidence-linked imports; automatic XBRL/filing
  extraction is not implemented.
- Monitoring is manually invoked. There is no scheduler or automatic re-evaluation job.
- The application is local-first and single-user. Cloud authentication and team permissions are not
  implemented.
- SQLite is versioned and safely migratable; source-queue and financial-fact migrations are still
  pending as part of M2 and M4.
- The Cockpit is functional but still concentrated in a large `App.tsx`; report/run comparison and
  a searchable library are future work.

## Start here next

Implement v0.3 in the execution order defined by
[`docs/V0_3_PLAN.md`](V0_3_PLAN.md), `ROADMAP.md`, and the `roadmap` GitHub Issues:

1. [#6 live non-fixture Theme/Anchor vertical slice](https://github.com/Mrjie7205/CapexGraph/issues/6);
2. [#7 filing-derived normalized financial facts](https://github.com/Mrjie7205/CapexGraph/issues/7);
3. explicit Cockpit coverage/failure states and v0.3.0 release hardening.

Do not begin Catalyst Scan merely because the enum exists; trustworthy live evidence remains the
higher priority.
