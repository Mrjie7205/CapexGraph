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

Resumable state machines coordinate research stages. The MVP begins with deterministic scaffolds; agent nodes and checkpoint persistence land incrementally.

### Tools and providers

Tools own ticker identity, adjusted prices, financial calculations, official filing retrieval, and report validation. Provider interfaces prevent the core from depending on one model or data vendor.

### Applications

- FastAPI exposes research runs and evidence.
- React/Vite provides the Research Cockpit.
- CLI supports local and batch workflows.

## Repository boundary

CapexGraph is independent from the existing Serenity skill and private research repository. Useful ideas or fixes may be copied deliberately, but there is no runtime dependency, submodule, or automatic data sync.
