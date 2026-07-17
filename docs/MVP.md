# Completed MVP plan

This document records the milestones delivered in `v0.2.0`. It is historical, not the forward
backlog. See `ROADMAP.md` and `docs/CURRENT_STATUS.md` for the next work.

## Definition of done

A new user can create a Theme Scan and an Anchor Scan, inspect grounded relationships, review structured candidate verdicts, add candidates to tracking, and later measure alpha without opening raw implementation files.

## Milestones

1. **Foundation ✅** — package, API, web shell, domain schema, CI.
2. **Run engine ✅** — SQLite state, bounded retries, JSON checkpoints, resume.
3. **Theme Scan core ✅** — structured agents, evidence graph, audit, bottleneck scoring, debate, decision artifacts, golden demo.
4. **Live research tools ✅** — SSRF-safe web/PDF capture, content hashing, evidence review, ticker identity, no-key market snapshots, financial imports.
5. **Anchor Scan ✅** — 360° chain map, financial deep dive, neighbour ranking.
6. **Cockpit ✅** — run execution, progress, graph/evidence review, opportunity radar.
7. **Monitoring ✅** — snapshots, structured triggers, invalidation, scorecard.
8. **Release ✅** — golden cases, Windows setup, documentation, report renderer.

## Golden cases

- Theme: `A股半导体硅片`
- Anchor: `兆易创新 / 603986`

## Explicitly out of scope

- live brokerage execution;
- autonomous portfolio management;
- cloud multi-user authentication;
- social/news terminal;
- reinforcement learning;
- private tweet datasets or proprietary research artifacts.

## Historical M3 boundary

At M3, the Theme Scan golden case was curated and reproducible while model proposals were forced
to low confidence. M4 subsequently added URL-based evidence capture, hashing, explicit review,
ticker identity, market snapshots, and financial imports. Automatic source discovery is still not
implemented; see the current boundaries in `docs/CURRENT_STATUS.md`.
