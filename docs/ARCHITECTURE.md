# CapexGraph architecture

CapexGraph separates probabilistic research from deterministic verification.

```text
Web / CLI / Python API
        ↓
Research workflow (Theme / Anchor / Catalyst)
        ↓
Specialist agents sharing typed state
        ↓
Evidence, market, financial, and validation tools
        ↓
Run store → graph → candidates → tracking → scorecard
```

## Layers

### Domain

Stable Pydantic contracts for runs, companies, evidence, graph edges, candidates, triggers, and verdicts. Agent prose never becomes the system of record without passing these contracts.

### Workflow

Resumable state machines coordinate research stages. SQLite is the system of record for runs and checkpoints; each step also writes a portable JSON artifact. An interrupted or failed run skips completed checkpoints when resumed.

M2 uses deterministic runtime handlers to verify execution semantics. Theme, Chain, Evidence, Financial, and Research Manager agents replace those handlers in M3 without changing the persistence contract.

### Tools and providers

Tools own ticker identity, adjusted prices, financial calculations, official filing retrieval, and report validation. Provider interfaces prevent the core from depending on one model or data vendor.

### Applications

- FastAPI exposes research runs and evidence.
- React/Vite provides the Research Cockpit.
- CLI supports local and batch workflows.

## Runtime lifecycle

```text
created → running → needs_review
              ↘ failed → resume → running
```

Each execution receives a bounded automatic retry budget. Manual resume grants a fresh retry budget but preserves the lifetime attempt count and all completed checkpoints.

## Repository boundary

CapexGraph is independent from the existing Serenity skill and private research repository. Useful ideas or fixes may be copied deliberately, but there is no runtime dependency, submodule, or automatic data sync.
