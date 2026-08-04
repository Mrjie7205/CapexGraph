# Current status

- Last updated: 2026-08-04
- Consolidated release: `v0.5.1`
- Schema version: `12`
- Next product milestone: `v0.6` — point-in-time consensus revisions and expectation-aware regime analysis
- Active branch: `codex/research-run-controls-stage-details`

This is the short handoff for a new session. Verify it against code and tests before a substantial
change. `ROADMAP.md` defines future scope; `docs/DECISIONS.md` preserves accepted boundaries.

## What works now

### Research workspace

- Theme Scan and Anchor Scan use typed, checkpointed stages and immutable run artifacts.
- Frozen no-key golden cases remain available for repeatable demos.
- Model execution is explicit and non-fallback: fixture, official local Codex subscription, or
  separately billed OpenAI API.
- Evidence capture is SSRF guarded and hashed. Non-fixture Theme Scan now automatically proposes
  up to four seed companies, resolves ticker-matched regulator/issuer disclosures, captures them,
  and independently reviews every capture with exact quotations before the graph stage. The new
  `agent_reviewed` state records model/prompt/hash provenance and is capped at medium confidence;
  `reviewed` remains explicitly human. Zero accepted sources fail the graph checkpoint visibly.
  CNINFO discovery resolves the platform's official `orgId` before querying announcements, and the
  graph merge reuses verified company nodes when a model returns the same ticker without a suffix.
- Financial facts, reports, tracking snapshots, scorecards, triggers, and research stages remain
  available from the earlier releases.
- The Cockpit now opens completed/failed stages as readable structured sections with Agent,
  provider/model lineage, attempts, timestamps, messages, and errors; operators no longer need to
  inspect raw checkpoint or manifest JSON to understand a stage result.
- The Cockpit previews the automatic evidence work before Theme graph execution, then shows its
  five phases, accepted/rejected counts, verified companies, failure reason, and distinct Agent
  review badges in the Evidence ledger.
- Accidental untouched runs can be removed through a two-step confirmation. Eligibility is
  re-checked under a database write lock, any checkpoint/domain output/source/fact/tracking/live or
  mainline reference blocks deletion, and the local workspace is moved recoverably under
  `runs/.trash/<timestamp>/<run-id>` before its run row is removed.

### v0.4 market, themes, and mainline monitoring

- EODHD supports normalized US/CN/KR daily history; Tushare is the A-share specialist/validation
  adapter; Yahoo is an explicit no-key network path; `fixture-market` is the deterministic no-key
  test/demo path.
- Quality gates cover ordering, duplicates, OHLC/volume validity, staleness, expected trading
  sessions, suspensions, adjusted-return semantics, corporate-action discontinuities, and stored
  cross-provider comparison reports.
- Theme definitions, sources, membership and snapshots preserve both `valid_*` and `known_*` time.
  A historical query cannot see a membership learned later.
- Recognition sources such as ETFs/indices/vendor lists are distinct from evidence-backed
  industrial exposure. The Cockpit shows both fields instead of treating inclusion as proof.
- Deterministic mainline metrics include 20/60-day return, benchmark-relative strength, breadth,
  participation, dispersion, volatility, persistence, and coverage.
- Versioned assessments and append-only state events support `insufficient`, `watch`, `emerging`,
  `confirmed`, `fragile`, and `exited` states.
- `mainline run-all` is the idempotent external scheduling entry point. One theme failure does not
  erase successful jobs, and the default path does not invoke a model.
- Official events can create a human-gated re-evaluation proposal without mutating an old run or
  spending model tokens automatically.
- The Chinese-first **主线雷达 / Mainline Desk** exposes data source, coverage, quality, metrics,
  state reasoning, theme lineage, jobs, and proposal decisions.

The bundled `mainline-conservative-2026-08-03` policy is intentionally `experimental`. Its code,
inputs, hashes, thresholds, and state changes are auditable, but turning it into the default
production investment policy requires an explicit later product decision.

### v0.5 official disclosures, events, and facts

- Official discovery adapters exist for SEC/EDGAR, CNINFO, Shanghai, Shenzhen and Beijing
  exchanges, OpenDART, and KIND/KRX, with credential-safe capability reporting.
- SEC discovery includes bounded historical submission shards. OpenDART filing facts normalize a
  conservative official-account subset while preserving source response lineage.
- Corporate events are append-only and point-in-time queryable. `known_at` and `observed_at` remain
  separate, and conservative title/form mapping avoids inventing operating conclusions.
- Official or issuer Evidence can produce review candidates for a bounded set of disclosed facts.
  A candidate becomes an immutable `FinancialFact` only after explicit human acceptance.
- Source Queue lets the user choose a market-appropriate official provider, discover filings,
  inspect the event timeline, capture Evidence, review it, and accept/reject fact candidates.
- Frozen CN/US/KR provider cases cover discovery, event mapping, Evidence linking, financial facts,
  and event-triggered research proposals without redistributing licensed data.

### v0.5.1 live-event gateway

- Jin10 MCP and Open Platform WebSocket are equal-priority channels with independent credentials,
  checkpoints, cadence/health, observations, and recovery.
- MCP uses standard initialize/initialized/tools/resources/call semantics and machine-parses only
  `structuredContent`. WebSocket implements auth, subscription, heartbeat, and reconnect.
- Canonical signals retain every observation, report matched/divergent/channel-only states, and
  deliver a single alert through reconnectable SSE.
- Live Desk includes paging, filters, provenance, coverage/delay metrics, cross-tab refresh,
  rules-only or explicit cost-gated model analysis, Connection Center, and Research Bridge.
- A live-news item remains a secondary signal. Only guarded official capture plus unchanged human-
  reviewed Evidence can link it into a research run.
- The frozen chaos/soak gate is implemented. A real Jin10 WebSocket live soak remains `WAIT KEY`
  until `JIN10_WEBSOCKET_SECRET_KEY` is supplied; this is not reported as a passing connection.

## No-key acceptance path

```powershell
capexgraph themes demo
capexgraph mainline run-all --market CN --as-of 2026-08-03 --provider fixture-market
capexgraph live demo
capexgraph live status
capexgraph live soak --mode fixture --cycles 6 --failure-every 3
```

The Cockpit provides equivalent product paths through **主线雷达**, **实时工作台**, **连接中心**,
**来源与证据**, and **研究桥接**.

## Honest capability boundaries

- CapexGraph produces research priorities and conditional plans, not orders or autonomous
  portfolio actions.
- The experimental mainline policy is not a buy/sell rule and has not been promoted to production.
- Real EODHD, Tushare, OpenDART, Jin10, and model calls require their own credentials and never
  silently fall back to another provider.
- A ChatGPT/Codex subscription is not an OpenAI Platform API key. The official local Codex channel
  uses the signed-in Codex CLI; OpenAI API usage is separately configured and billed.
- Missing provider coverage is shown as missing/partial/unsupported. Models cannot fill it in as if
  it were sourced fact.
- Historical theme membership depends on imported, licensed, or public point-in-time sources. The
  bundled dataset proves system behavior; it is not a complete reconstruction of every market
  theme.
- Consensus history and revision breadth do not exist yet; those are the v0.6 scope.

## Verification record

Local working-tree gate on 2026-08-04 for autonomous Theme evidence bootstrap and Cockpit run
controls:

- Ruff: passed;
- Python: 172 tests passed;
- React/Vite production build: passed at Web version 0.5.1;
- browser: the retained Codex Theme run showed the pending automatic-evidence action; temporary
  browser-only responses verified running/completed/failed bootstrap states without mutating the
  run; desktop and 375px layouts had no horizontal overflow, and the fresh console had zero errors;
  and
- isolated live Codex/CNINFO spot check: 40 official suggestions discovered, four selected and
  captured, three marked `agent_reviewed`, one rejected, and Theme `graph` completed. This is a
  dated integration check, not a guarantee that future themes will always find acceptable evidence.

Previous consolidated release record:

Local release gate on 2026-08-03:

- Ruff: passed;
- Python: 140 tests passed, including fresh/legacy migrations through schema 12;
- React/Vite production build: passed at Web version 0.5.1;
- wheel: `capexgraph-0.5.1-py3-none-any.whl` built and contains themes, monitoring, CN/KR source
  adapters, OpenDART facts, and the frozen multi-market fixture; and
- browser: no-key Mainline Desk produced a 94.4 deterministic `confirmed` assessment, displayed
  experimental-policy and partial-history warnings, created a human-gated proposal, and had no
  horizontal overflow at 1265px or 375px. No new console error appeared after the final reload.

The pull request and remote CI result remain the authoritative cloud record.

## Start here next

1. Read `ROADMAP.md` and `docs/V0_6_PLAN.md` before adding consensus data.
2. Keep estimates point-in-time; never reconstruct history from today's consensus.
3. Reuse the theme universe and official-event contracts instead of creating parallel identities.
4. Preserve the no-key fixture path and explicit provider/auth/billing boundaries.
5. Do not promote the experimental mainline thresholds without a recorded product decision.
