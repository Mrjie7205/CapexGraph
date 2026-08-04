# Theme Scan

Theme Scan is CapexGraph's first complete research workflow:

```text
intake → census → graph → audit → score → debate → decision
```

Each stage receives typed state, returns one Pydantic model, and is checkpointed before the next stage begins. A failed run can resume without repeating completed model calls.

## Cockpit stage inspection and empty-run cleanup

In **研究任务 / 工作流**, select a run and use **查看详情** beside any completed, blocked, or
failed stage. The Cockpit opens the latest finished stage automatically and renders its typed output
as named sections and lists together with Agent, attempts, timestamps, provider/model lineage,
message, and error state. This is a view of the persisted checkpoint/`manifest.agent_outputs`; it
does not re-run or reinterpret the stage.

An untouched duplicate run shows **删除空任务**. The first click opens an inline explanation and
the second moves the workspace to the local `runs/.trash` recovery area. The backend performs the
authoritative check again and refuses deletion when the run has started or has checkpoints,
nodes/edges, Evidence, candidates, sources/facts, tracking, live context, or a mainline proposal.
Research assets must be preserved rather than cleaned up through this convenience action.

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

## Automatic company evidence before graph mapping

For non-fixture Theme runs, pressing **运行下一阶段** when `graph` is pending authorizes one bounded
automatic evidence pass. The Agent proposes up to four listed-company seeds from the completed
boundary and census, discovers ticker-matched official disclosures through CNINFO (CN), SEC (US),
or KIND (KR), selects and captures up to four sources, then independently reviews every captured
text with exact quotations. The operator is not asked to know which companies or reports to pick.

Accepted material is recorded as `agent_reviewed` with provider, model, transport, prompt hash,
source hash, rationale, quotes, warnings, and review time. It is visibly distinct from human
`reviewed` material and caps a fully Agent-grounded edge at medium confidence. The five phases and
counts appear in the Cockpit, while `evidence-bootstrap.json` preserves restart/failure detail.
Zero accepted sources stop `graph`; fixtures bypass the automatic pass.

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

### Codex subscription

`--provider codex_subscription` uses the same strict Pydantic contract through the official local
Codex CLI. It requires an installed Codex CLI and a ChatGPT login, but no OpenAI Platform API key.
Connection Center can start the official browser login and select a model available to the
account. CapexGraph runs an ephemeral, read-only, schema-bound `codex exec`, never receives OAuth
tokens, and never falls back to the official API channel when subscription execution fails.

```powershell
capexgraph model providers --probe-codex
capexgraph theme "AI数据中心电力" --provider codex_subscription --execute
```

CLIProxyAPI remains an explicit `CAPEXGRAPH_CODEX_TRANSPORT=proxy` compatibility path for existing
local installations; it is no longer the default.

### OpenAI API

`--provider openai` uses `client.responses.parse` with each stage's Pydantic output model. Install the optional dependency and configure both variables:

```powershell
python -m pip install -e ".[openai]"
$env:OPENAI_API_KEY = "..."
$env:CAPEXGRAPH_OPENAI_MODEL = "your-model"
```

The OpenAI adapter itself does not fetch sources. For Theme Scan, the workflow now surrounds it
with the deterministic automatic evidence service above: model judgment proposes/selects/reviews,
while official-provider identity, guarded downloads, hashes, exact quotations, limits, and
confidence caps are enforced by code. Human Source Queue review remains available; human-reviewed
unchanged sources may preserve high confidence, while Agent-reviewed sources stop at medium.

Before the first live stage, the workflow records model/provider version and evaluates evidence
coverage. Every stage receives bounded extracted text from captured/reviewed sources and bounded
versioned financial facts; the prompt does not receive only titles or URLs. `partial` mode can
continue with explicit low-confidence gaps. For live Theme runs, `strict` defers its initial
evidence gate until the automatic graph bootstrap, then requires at least one unchanged human- or
Agent-reviewed source and still caps Agent-only support at medium confidence.

The selected provider and model are locked when execution starts. Resume may retry the same
channel, but switching a partially executed run to another authentication or billing channel is
rejected; create a new run instead. Provider failures record a safe category and retryability, and
run manifests retain model-call counts without storing credentials.

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
