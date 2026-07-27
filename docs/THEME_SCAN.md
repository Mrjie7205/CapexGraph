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

`--provider fixture` accepts the golden semiconductor-wafer subject and the dated
`Alphabet 2026年Q2 AI资本开支传导` acceptance subject. Their public sources and expected
outputs were manually curated, so audited edges may retain medium or high confidence. The Alphabet
case additionally verifies that a newly captured source can retain its hash and review state when
the deterministic replay proposes the same stable evidence identity.

```powershell
capexgraph demo-alphabet-q2
```

The Alphabet fixture deliberately stops at evidence-backed infrastructure layers. It does not
convert product mentions or aggregate capital expenditure into named supplier relationships.

### OpenAI

`--provider openai` uses `client.responses.parse` with each stage's Pydantic output model. Install the optional dependency and configure both variables:

```powershell
python -m pip install -e ".[openai]"
$env:OPENAI_API_KEY = "..."
$env:CAPEXGRAPH_MODEL = "your-model"
```

The OpenAI adapter does not search or fetch sources on its own. Model-proposed evidence remains a
research queue and resulting claims are forced to low confidence. A user can capture HTML/PDF
sources with the live evidence tools, verify their hashes, and explicitly review them. A claim may
preserve medium/high confidence only when all of its cited captured sources are reviewed and
unchanged; review still does not guarantee the interpretation is correct.

Before the first live stage, the workflow records model/provider version and evaluates evidence
coverage. Every stage receives bounded extracted text from captured/reviewed sources and bounded
versioned financial facts; the prompt does not receive only titles or URLs. `partial` mode can
continue with explicit low-confidence gaps. `strict` mode checkpoints a failure until at least one
reviewed, hash-valid source exists and blocks unsupported medium/high relationship proposals.

See `docs/LIVE_RESEARCH.md` for the capture and review contract.

## Deterministic integrity checks

The workflow fails and checkpoints the error when:

- an edge references an unknown node;
- an edge references a missing evidence item;
- medium/high-confidence curated edges omit evidence;
- the audit does not cover every edge;
- a candidate references an unknown node;
- the debate omits a candidate;
- the decision ranks an unknown or duplicate candidate.
- strict evidence preflight or confidence requirements are not met;
- a captured source hash no longer matches; or
- a provider/fact input fails deterministic validation.
