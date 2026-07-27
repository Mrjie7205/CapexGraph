# Changelog

All notable changes to CapexGraph are documented here.

## Unreleased

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
