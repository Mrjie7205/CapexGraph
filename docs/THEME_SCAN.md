# Theme Scan

Theme Scan is CapexGraph's first complete research workflow:

```text
intake → census → graph → audit → score → debate → decision
```

Each stage receives typed state, returns one Pydantic model, and is checkpointed before the next stage begins. A failed run can resume without repeating completed model calls.

## No-key golden run

```powershell
capexgraph demo
```

This runs the frozen `A股半导体硅片` evidence pack as of `2025-04-29`. It demonstrates the execution and artifact contracts without network access or an API key. It is deliberately labeled as a demo rather than a current sector report.

The run produces:

- `graph.json` — resolved nodes, evidence-linked edges, audit verdicts;
- `evidence.json` — source ledger and evidence policy;
- `candidates.json` — research priorities, risks, invalidation, triggers;
- `decision.json` — ranking, limitations, next actions, disclaimer;
- `checkpoints/*.json` — one durable output per agent stage.

## Provider behavior

### Fixture

`--provider fixture` accepts only the golden semiconductor-wafer subject. Its public sources were manually curated, so audited edges may retain medium or high confidence.

### OpenAI

`--provider openai` uses `client.responses.parse` with each stage's Pydantic output model. Install the optional dependency and configure both variables:

```powershell
python -m pip install -e ".[openai]"
$env:OPENAI_API_KEY = "..."
$env:CAPEXGRAPH_MODEL = "your-model"
```

M3 does not give the model a trusted filing or web retrieval tool. Its proposed evidence remains useful as a research queue, but CapexGraph forces all resulting edges and candidates to low confidence until a later retrieval stage independently validates them.

## Deterministic integrity checks

The workflow fails and checkpoints the error when:

- an edge references an unknown node;
- an edge references a missing evidence item;
- medium/high-confidence curated edges omit evidence;
- the audit does not cover every edge;
- a candidate references an unknown node;
- the debate omits a candidate;
- the decision ranks an unknown or duplicate candidate.
