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

M3 plugs Theme, Universe, Chain, Evidence, Bottleneck, Debate, and Research Manager agents into the M2 persistence contract. Every agent returns a Pydantic model; deterministic code then validates references and materializes domain objects and artifacts.

### Tools and providers

Provider interfaces prevent the workflow from depending on one model vendor. The built-in fixture provider loads a curated evidence pack and needs no key. The optional OpenAI provider uses structured Responses API output and is loaded only when selected.

Tools will own ticker identity, adjusted prices, financial calculations, official filing retrieval, content hashing, and report validation. Those live retrieval tools are not part of M3.

### Evidence trust boundary

```text
curated fixture → schema validation → medium/high confidence allowed
model proposal  → schema validation → forced low confidence → retrieval review required
```

An evidence ID proves provenance inside a run; it does not prove the underlying URL was fetched. Only providers marked `curated` may currently preserve medium/high-confidence claims. This prevents a model-generated citation from being mistaken for verified evidence.

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
