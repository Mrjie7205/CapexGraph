# CapexGraph agent guide

This file applies to the entire repository. It is the automatic entry point for a new coding
session. Do not assume access to prior chats, local Codex memory, or the private Serenity
repository.

## Mission

CapexGraph is an evidence-first supply-chain investment research workspace. It helps a human
analyst discover an opportunity, verify relationships, form a falsifiable judgment, and track
whether that judgment plays out. It produces research priorities, not autonomous investment
advice or trades.

## Read before changing code

Read these files in order:

1. `docs/CURRENT_STATUS.md` — what is actually shipped and what is not;
2. `ROADMAP.md` — the next approved priorities and acceptance criteria;
3. `docs/V0_5_PLAN.md` — active official-disclosure and event-calendar execution order;
4. `docs/V0_5_1_PLAN.html` — planned live-event gateway, equal-priority MCP/WebSocket channels,
   and Cockpit path;
5. `docs/V0_4_PLAN.md` — incomplete market/theme/mainline dependency plan;
6. `docs/V0_3_PLAN.md` — completed v0.3 execution record;
7. `docs/PROJECT_CONTEXT.md` — product intent, users, and repository boundary;
8. `docs/ARCHITECTURE.md` — runtime and trust boundaries;
9. `docs/DECISIONS.md` — accepted decisions that should not be reopened accidentally;
10. the workflow-specific document under `docs/`; and
11. `CONTRIBUTING.md` — validation and documentation contract.

For live-gateway work, the workflow-specific document is `docs/LIVE_EVENTS.md`.

When documentation and code disagree, verify the implementation and tests, fix the documentation
in the same change, and record material design changes in `docs/DECISIONS.md`.

## Non-negotiable boundaries

- Agents judge; deterministic code verifies tickers, dates, prices, calculations, references, and
  schema integrity.
- A relationship is not a fact without provenance. Medium/high-confidence edges require evidence.
- `captured` means bytes were downloaded and hashed. `reviewed` means a human approved the same
  unchanged capture. Neither status makes every interpretation of a source true.
- Product overlap is a `peer` relationship. Never promote it into a customer, supplier, or
  beneficiary claim without direct evidence.
- Golden fixtures are frozen, dated product demos. Never describe them as current research.
- Keep CapexGraph runtime-independent from `serenity-bottleneck-hunter` and private Serenity data.
  Ideas and fact-correctness fixes may be ported deliberately; imports, submodules, private paths,
  and automatic synchronization are prohibited.
- Do not add brokerage execution, autonomous portfolio actions, fabricated alpha, fake progress,
  or placeholder research presented as complete.
- Preserve the local-first, no-key golden path. Optional model/data providers may add setup, but
  must not make the fixtures or core inspection workflow require an API key.
- Treat index, ETF, and vendor-concept membership as market-recognition evidence. It does not prove
  industrial exposure or a supplier/customer relationship.
- Point-in-time theme data must preserve both effective dates and when the system could have known
  the membership. Do not use today's universe to calculate a historical signal.
- Never commit provider keys or licensed raw market, constituent, or estimate datasets.
- Treat remote evidence as hostile input and preserve the SSRF and download-boundary controls.

## Repository map

```text
src/capexgraph/domain/       typed system-of-record contracts
src/capexgraph/runtime/      SQLite runs, checkpoints, retries, resume
src/capexgraph/research/     Theme and Anchor agent workflows
src/capexgraph/providers/    fixture and optional model adapters
src/capexgraph/financials/   immutable filing facts and persistence
src/capexgraph/market/       daily providers, quality gates, sync, persistence
src/capexgraph/events/       official event mapping, versions, point-in-time calendar
src/capexgraph/live/         live-signal source contract, frozen replay, matching, persistence
src/capexgraph/tools/        evidence, identity, market, financial tools
src/capexgraph/tracking/     snapshots, triggers, scorecards, stages
src/capexgraph/api/          FastAPI application
apps/web/                    React/Vite Research Cockpit
docs/                        product, architecture, workflow, and status docs
tests/                       executable behavior and handoff contract
```

`RunMode.CATALYST` is reserved and scaffolded, not implemented research functionality. Do not
advertise it as shipped until its roadmap acceptance criteria and tests are complete.

## Working method

1. Start from an active item in `ROADMAP.md` or a scoped user request. The user explicitly advanced
   active development to the isolated v0.5 event foundation and completed v0.5.1 M0-M6. Follow
   `docs/V0_5_PLAN.md` and `docs/V0_5_1_PLAN.html`; treat M7 as next and do not claim the paused
   v0.4 theme/mainline work is complete.
2. Inspect the actual code path and tests before proposing architecture.
3. State any assumption that changes evidence semantics, provider trust, or repository boundaries.
4. Implement the smallest end-to-end vertical slice with durable artifacts and failure states.
5. Add or update tests proportional to risk.
6. Update `docs/CURRENT_STATUS.md`, `CHANGELOG.md`, and relevant workflow docs when capability
   changes. Update `ROADMAP.md` when an item moves or its acceptance criteria change.
7. Run the required checks below before handoff.

## Required checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Push-Location apps\web
npm run build
Pop-Location
```

For packaging or release changes, also build a wheel:

```powershell
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
```

## Definition of done

A change is not complete merely because an endpoint or UI shell exists. It is complete when:

- the real user path works without editing implementation files;
- state and artifacts survive restart where persistence is expected;
- failure and resume behavior is visible;
- evidence and confidence rules are enforced by code;
- tests and production web build pass;
- docs distinguish shipped behavior from planned behavior; and
- the current-status and roadmap handoff remains accurate for the next session.
