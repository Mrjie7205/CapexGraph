# Alphabet Q2 2026 acceptance report

Run date: 2026-07-23  
Disclosure date: 2026-07-22  
Live run ID: `20260723-theme-89e5570f`  
Subject: `Alphabet Q2 2026 AI CapEx Transmission`

## Outcome

The case passed CapexGraph's evidence, provenance, financial-import, deterministic replay, and
market-snapshot paths. It did not pass as an autonomous live research run.

The completed replay contains:

- 2 reviewed first-party disclosures and 1 captured market-data source;
- 11 normalized, evidence-linked financial and operating metrics;
- 5 nodes, 3 audited edges, and 3 research-priority candidates;
- no named external supplier claim; and
- a `needs_review` decision rather than a buy/sell output.

The strongest evidence-backed result is that AI accelerator/server capacity and multi-site
data-center networking are research-priority bottleneck layers. The two captured disclosures do
not support attributing Alphabet's capital expenditure to named external beneficiaries.

## Evidence captured

| Evidence | Status | SHA-256 |
|---|---|---|
| Alphabet Q2 2026 earnings release | reviewed | `65f35a2e9c287112121f736321c7526d603ba8e0dae27acac56c7d7357602aa8` |
| Q2 2026 CEO earnings-call remarks | reviewed | `4c3e3618cac3905c365788f120645a77796421fafd0232b2905d3d4cc92a2562` |
| GOOGL Yahoo Chart snapshot | captured | `fe02d1ccca910fc47a029b49a5456c7aa22e136d121776961312a3792a4ec044` |

The live disclosure capture required a one-command local environment override because this Codex
desktop network resolves public hosts into the reserved `198.18.0.0/15` range. The default SSRF
guard correctly rejects that range. This is an environment-compatibility intervention, not a
reason to weaken the default protection.

## Financial integrity checks

The normalized import correctly preserved, among other facts:

- revenue: USD 119.796 billion;
- Google Cloud revenue: USD 24.768 billion, up 82% year over year;
- purchases of property and equipment: USD 44.924 billion;
- quarterly free cash flow: negative USD 5.855 billion;
- net equity-securities gain: USD 99.031 billion;
- disclosed EPS effect from that gain: USD 6.26;
- Cloud backlog: USD 514 billion; and
- model API throughput: approximately 22 billion tokens per minute.

This case is particularly useful because it requires the research layer to separate operating
momentum from the large non-operating equity gain.

## Baseline failures observed before adaptation

| Path | Baseline result | Meaning |
|---|---|---|
| Supplied official URLs | pass after local network override | Capture, extraction, hash, and review work |
| Normalized financial CSV | pass | 11 evidence-linked facts persisted |
| `GOOGL` identity | fail | Bundled registry was A-share-only |
| Arbitrary live Theme execution | blocked | No model/API configuration was present |
| Source discovery | unavailable | Current collector starts from supplied URLs |
| Theme consumption of imported facts | unavailable | Facts persist but are not injected into Theme prompts |
| Theme report financial display | fail | Report says no structured comparison for this mode |
| Catalyst Scan | unavailable | It remains a reserved scaffold |

Before the deterministic replay, the live run therefore contained two reviewed disclosures and
11 financial facts, but zero nodes, edges, and candidates. That is the honest current live-system
baseline.

## Minimal adaptations made

- Added registry-backed `GOOGL` and `GOOG` identities.
- Added a dated `demo-alphabet-q2` frozen replay.
- Allowed a captured evidence item to survive workflow replay when the fixture proposes the same
  stable evidence identity. The captured hash, local path, and review state remain authoritative.
- Added a frozen-response integration test covering capture, review, financial import, replay,
  evidence preservation, and supplier-attribution restraint.

The replay is deliberately human-curated. It validates typed outputs, provenance rules, audit
coverage, and the expected research boundary; it does not prove autonomous source discovery or
model judgment.

## Research decision

1. **AI accelerator and server capacity — high-priority watch.** Management explicitly describes
   demand as supply constrained while model usage is increasing.
2. **Multi-site data-center networking — medium-priority watch.** Management directly describes a
   network designed to connect accelerators across multiple sites, but no spending split or vendor
   exposure is disclosed.
3. **Alphabet — operating anchor, not a clean headline-EPS signal.** Cloud growth and operating
   income are strong, while free-cash-flow pressure and the equity gain must be analyzed separately.
4. **Power and cooling — unresolved hypothesis.** Economically plausible, but intentionally left
   without an edge because the captured sources do not provide sufficient evidence.

The captured Yahoo snapshot for GOOGL as of 2026-07-22 was USD 342.09, with a 3-month return of
3.01%, 16.28% below the six-month high, below its 50-day average, and classified as `range`.
Yahoo Chart is an unofficial best-effort adapter, so this is workflow context rather than a
licensed market-data record.

## Remaining product defects

### P0 — trustworthy live execution

1. Add official-source discovery and a visible review queue.
2. Allow a non-fixture Theme run to consume already reviewed evidence without requiring users to
   handcraft a provider path.
3. Record provider and coverage failures in the run and Cockpit instead of only returning a CLI
   error.

### P1 — filing-derived financial context

1. Extract normalized filing facts rather than requiring a manual CSV.
2. Inject evidence-linked facts into the appropriate Theme/Anchor stages.
3. Render the imported metrics and their source lineage in the report.
4. Add period-over-period calculations without allowing the model to invent units or periods.

### Deferred

- Implement Catalyst Scan only after the v0.3 live evidence path is trustworthy.
- Add scheduled re-evaluation for subsequent Alphabet quarters.
- Expand from infrastructure layers to named suppliers only through separate first-party evidence.

## Reproduction

Frozen replay:

```powershell
.\.venv\Scripts\python.exe -m capexgraph.cli demo-alphabet-q2
```

The live capture and import commands are documented in this directory's `README.md`. The generated
local HTML report is under:

```text
runs/20260723-theme-89e5570f/report.html
```
