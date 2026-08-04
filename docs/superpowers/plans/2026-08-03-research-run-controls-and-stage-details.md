# Research Run Controls and Stage Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a local user safely remove accidental untouched research tasks and understand every completed or failed workflow stage from the Cockpit.

**Architecture:** Add a guarded, recoverable deletion operation to `RunStore` and expose it through a confirmation-only FastAPI endpoint. The backend remains authoritative for eligibility and protects all runs with checkpoints, domain output, source/fact records, tracking, or live/mainline links. Add a focused React stage-detail component that renders the already-persisted pipeline metadata and `manifest.agent_outputs` into readable sections without mutating research state.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite, React 18, TypeScript, Vite, CSS, pytest, Playwright CLI.

---

## Task 1: Lock down guarded deletion behavior

**Files:**
- Modify: `src/capexgraph/runtime/store.py`
- Modify: `src/capexgraph/api/app.py`
- Test: `tests/test_api.py`

- [x] Write API tests proving confirmation is required, an untouched run is moved to `runs/.trash` and removed from SQLite, and completed/checkpointed or externally linked runs are rejected.
- [x] Run the focused tests and confirm they fail for the missing endpoint.
- [x] Add typed deletion eligibility/result contracts and one transactional `RunStore.delete_empty_run` operation.
- [x] Re-check eligibility inside the write transaction, archive the local run directory recoverably, and restore it if the database delete fails.
- [x] Expose `DELETE /api/v1/runs/{run_id}` with explicit confirmation and stale-run protection via the expected `updated_at` value.
- [x] Run the focused API tests and confirm they pass.

## Task 2: Add the human-readable stage detail view

**Files:**
- Create: `apps/web/src/StageDetailPanel.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/styles.css`
- Test: `tests/test_web_run_controls.py`

- [x] Write a source-contract regression test for the stage-detail control, selected-stage state, guarded deletion confirmation, and readable renderer; run it and confirm it fails.
- [x] Extend the TypeScript run/step contracts with timestamps, attempts, and typed `agent_outputs` access.
- [x] Build a focused stage-detail panel that shows status, agent, attempts, timestamps, provider/model lineage, errors, and structured output as sections/lists/cards.
- [x] Redact sensitive-looking keys defensively and provide honest empty states for stages without output.
- [x] Add `查看详情` controls to completed/failed stages and auto-select the latest completed or failed stage after a run refresh.
- [x] Add a two-step delete confirmation in the selected-run header and refresh selection after a successful deletion.
- [x] Style desktop and narrow-screen states in the existing editorial paper/wine visual language with readable type sizes.
- [x] Run the focused UI contract tests and the Web production build.

## Task 3: Update product handoff and verify end to end

**Files:**
- Modify: `docs/CURRENT_STATUS.md`
- Modify: `docs/THEME_SCAN.md`
- Modify: `CHANGELOG.md`

- [x] Replace the two known UX gaps with shipped behavior and document the conservative deletion boundary.
- [x] Add Cockpit usage instructions for viewing stage output and removing accidental empty runs.
- [x] Record both user-visible changes in the changelog.
- [x] Run Ruff, the complete pytest suite, and the Web production build.
- [x] Start or reuse the local services and use a real browser to verify stage details, confirmation cancellation, safe deletion of a temporary empty task, protected deletion of the retained checkpointed task, and responsive layout.
- [x] Remove only test artifacts created during this implementation and leave prior user changes intact.
