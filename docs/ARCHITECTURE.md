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

Theme Scan plugs Theme, Universe, Chain, Evidence, Bottleneck, Debate, and Research Manager
agents into the persistence contract. Anchor Scan substitutes identity, repricing-cause, neighbour,
and financial-comparison specialists. Every agent returns a Pydantic model; deterministic code
validates references and materializes domain objects and artifacts.

### Tools and providers

Provider interfaces prevent the workflow from depending on one model vendor. The built-in fixture provider loads a curated evidence pack and needs no key. The optional OpenAI provider uses structured Responses API output and is loaded only when selected.

Tools own ticker identity, adjusted prices, financial imports, SSRF-safe public source retrieval,
content hashing, and report rendering. The built-in market adapter is no-key and best-effort;
production deployments can replace it behind the same interface.

### Evidence trust boundary

```text
curated fixture       → schema validation → medium/high confidence allowed
model proposal        → schema validation → forced low confidence
captured source       → hash verification → explicit human review
reviewed model claim  → medium/high confidence may be preserved
```

An evidence ID proves provenance inside a run. `captured` means bytes were downloaded and hashed;
`reviewed` means a human approved that unchanged capture. It still does not make every possible
interpretation of the source true. Curated fixtures and claims backed entirely by reviewed captures
may preserve medium/high confidence.

### Forward tracking

Tracking tables share the SQLite workspace while remaining separate from immutable run artifacts.
A tracked candidate stores the original call date, candidate price, benchmark price, thesis,
invalidation text, and structured triggers. Later paired snapshots calculate return and alpha.
Trigger events are append-only and acknowledgement never deletes event history.

### Applications

- FastAPI exposes runs, evidence review, artifacts, tracking, and HTML reports.
- React/Vite provides the live Research Cockpit and stage board.
- CLI supports local, batch, tracking, and portable-report workflows.

## Runtime lifecycle

```text
created → running → needs_review
              ↘ failed → resume → running
```

Each execution receives a bounded automatic retry budget. Manual resume grants a fresh retry budget but preserves the lifetime attempt count and all completed checkpoints.

## Repository boundary

CapexGraph is independent from the existing Serenity skill and private research repository. Useful ideas or fixes may be copied deliberately, but there is no runtime dependency, submodule, or automatic data sync.
