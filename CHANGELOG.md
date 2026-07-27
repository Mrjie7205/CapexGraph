# Changelog

All notable changes to CapexGraph are documented here.

## Unreleased

## 0.3.0 — 2026-07-27

- added a repository-owned cross-session handoff contract: agent guide, forward roadmap, project
  context, current status, accepted decisions, documentation drift checks, and PR checklist;
- clarified that Catalyst Scan is reserved/scaffolded rather than shipped;
- updated Theme Scan documentation for the M4 evidence capture and review boundary.
- added an Alphabet Q2 2026 AI CapEx acceptance case with first-party evidence manifests,
  normalized financial facts, a deterministic no-key replay, and an observed-defects report;
- added registry-backed Alphabet Class A and Class C ticker identities;
- preserved captured evidence hashes, local artifacts, and review status when a workflow reuses
  the same stable evidence identity;
- added frozen-response integration coverage that prevents aggregate CapEx or product mentions
  from becoming unsupported named-supplier claims.
- added Chinese report localization for Chinese subjects, including workflow labels, evidence
  states, confidence, financial metrics, units, risks, limitations, and disclaimers.
- added an execution-grade v0.3 plan covering dependency order, PR boundaries, acceptance tests,
  release gates, risks, and explicit exclusions.
- added versioned, checksummed SQLite migrations with automatic safe startup upgrades;
- added a frozen v0.2 legacy database fixture and regression coverage for runs, checkpoints,
  tracking snapshots, and trigger events;
- added consistent SQLite backup/restore plus `capexgraph db status|upgrade|backup|restore`.
- added a durable `SourceSuggestion` queue that keeps discovery results separate from Evidence;
- added SEC/EDGAR filing discovery and deterministic issuer/regulator URL suggestions;
- added canonical-URL and content-hash deduplication, persisted capture failures, safe redirect
  handling, and HTML/PDF content-type enforcement;
- added source discovery, capture, retry, dismissal, and extracted-text paths across CLI, API, and
  the Cockpit.
- added `partial` and `strict` evidence modes, deterministic coverage preflight, bounded captured
  source text in every Theme/Anchor prompt, and checkpointed strict-mode recovery;
- recorded model, source-discovery, market/evidence, and filing provider versions plus as-of date,
  coverage, pending review, and durable failure metadata in run manifests;
- prevented unreviewed/model-only relationship proposals from retaining medium/high confidence;
- added a frozen non-fixture Alphabet vertical proving reviewed source text and financial context
  reach the model without hand-editing run artifacts;
- added immutable, versioned SEC Company Facts across income, cash flow, and balance-sheet metrics,
  including restatements, explicit missing values, deterministic unit/period conflicts, and derived
  free cash flow with formula lineage;
- added financial-fact schema migration 3, raw SEC response evidence/hash capture, JSON source
  locators, CLI/API extraction, and Theme/Anchor context injection;
- added Cockpit create-first/no-key preparation, evidence-mode selection, one-stage pause,
  retry/resume, coverage and provider failures, filing-fact extraction/table, and report access;
- updated reports to expose providers, evidence coverage, fact provenance, reviewed facts,
  grounded inferences, unverified hypotheses, and coverage gaps; and
- aligned Python and Web versions to `0.3.0`.

## 0.2.0 — 2026-07-17

- added SSRF-safe HTML/PDF evidence capture, hashing, and explicit review;
- added deterministic A-share ticker identity and no-key market snapshots;
- added evidence-linked financial fact imports;
- added the seven-stage Anchor Scan with a frozen 兆易创新 golden case;
- turned the Cockpit into a live run, graph, evidence, and decision workbench;
- added candidate tracking, benchmark-relative scorecards, structured trigger events, and stage boards;
- added self-contained HTML research reports, Windows bootstrap, and container setup;
- expanded CI across supported Python versions and package builds.

## 0.1.0 — 2026-07-16

- initial domain model, SQLite run engine, resumable checkpoints, Theme Scan, API, CLI, and web shell.
