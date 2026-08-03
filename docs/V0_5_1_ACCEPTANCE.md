# v0.5.1 acceptance closeout

- Date: 2026-07-31
- Branch: `codex/v0-5-1-live-event-gateway`
- Scope: local Definition of Done for M0-M7 and the productized Cockpit path
- External gate: Jin10 WebSocket credentialed live smoke/soak remains `WAIT KEY`

## Outcome

The local v0.5.1 acceptance gate is closed. Jin10 MCP, the live supervisor, canonical event
storage, deterministic scoring, the official Codex subscription path, Live Desk, and Research
Bridge work as one user-visible path. Missing WebSocket credentials remain an explicit external
gate and are not represented as a passing live connection.

## Closeout fixes

- Connection and monitor changes propagate across open Cockpit tabs through a credential-free
  browser sync message. Opening or returning to Connection Center performs a real redacted
  readiness refresh.
- Live Desk refreshes the canonical event ledger on SSE readiness, cross-tab changes, tab
  visibility, and a bounded 30-second interval. SSE remains the durable alert stream; low-score
  signals that do not create alerts still become visible through ledger synchronization.
- `GET /api/v1/live/events/page` returns `items`, filtered `total`, `offset`, `limit`, and
  `has_more`. The existing array endpoint remains backward compatible.
- Server-side filters cover category, channel, formal/fixture/mixed source scope, minimum score,
  theme, entity, alert-only state, and title search.
- Every event record carries `source_scope=live|fixture|mixed`; the Cockpit labels these as
  **正式信号**, **演示样例**, or **混合谱系**.
- Page assembly uses batched store reads. A 407-signal local ledger returned the first 50 records
  in under one second during acceptance, instead of the pre-fix request timing out after 60
  seconds.
- Automated tests use an isolated empty project environment so a developer's ignored `.env`
  credentials cannot leak into or change no-key test behavior.

## Real local path verified

| Step | Observed result |
| --- | --- |
| Connection Center | Jin10 MCP `ready`; official Codex subscription `ready`; WebSocket `not_configured` |
| SSE | `CONNECTED` immediately after `live.ready` |
| Supervisor | Start/stop changed both open Cockpit tabs without reload |
| MCP intake | One bounded monitor run increased canonical signals from 407 to 427; both tabs refreshed to `50 / 427` |
| Source labeling | Formal filter returned only `live` records; fixture filter returned the three frozen demo records |
| Pagination | Load-more changed the formal ledger from 50 to 100 loaded records while preserving its total |
| Theme filter | `存储` narrowed the current ledger and retained matched-theme labels |
| Codex analysis | One authenticated `codex_subscription` call completed with typed direction, horizon, confidence, transmission path, evidence gaps, and `verify` next action |
| Research Bridge | The selected formal signal opened with four-stage evidence firewall and an immutable audit entry for the completed analysis |
| Responsive QA | Desktop and 390px layouts had no horizontal overflow |

The real Codex result correctly remained a conditional research proposal. It did not upgrade the
Jin10 message into Evidence or create a trade.

## Automated gate

Acceptance result on 2026-07-31:

- Ruff: passed
- Pytest: 123 passed
- React/Vite production build: passed
- Python wheel build: passed

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Push-Location apps\web
npm run build
Pop-Location
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
```

The page/filter test covers totals, offsets, `has_more`, source separation, score, theme, entity,
and alert-only filtering. Existing M7 tests continue to cover confirmed verification tasks,
official-source capture/review, Evidence links, immutable run context, linked re-evaluation, audit,
fixture soak, and diagnostics.

## Gate still open

The credentialed provider soak deliberately requires both equal-priority channels:

```powershell
capexgraph live soak --mode providers --cycles 30 --interval 10
```

Until `JIN10_WEBSOCKET_SECRET_KEY` is available and that soak passes, WebSocket stays
contract-tested but not live-accepted. This does not demote MCP to a fallback and does not reopen
the completed local v0.5.1 gate.
