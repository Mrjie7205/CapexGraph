# CapexGraph

**Evidence-first supply-chain investment research.**

CapexGraph turns an investment theme, a market anchor, or a catalyst into an auditable research run: a grounded supply-chain graph, candidate verdicts, invalidation conditions, and forward tracking.

> 证据优先的供应链投资研究系统：从主题或热门个股出发，构建可审计的产业链图谱，寻找尚未充分定价的瓶颈环节，并持续验证判断。

## Why CapexGraph

Most financial agent projects start with a ticker and end with a buy/sell opinion. CapexGraph starts one level earlier:

1. Where is capital expenditure flowing?
2. Which supply-chain relationships are actually evidenced?
3. Which nodes are hard to substitute?
4. What has the market already priced in?
5. What would prove the thesis wrong?

The project is independent from `serenity-bottleneck-hunter`. That skill remains a self-contained, low-friction project; CapexGraph is a separate professional research system.

## MVP research modes

- **Theme Scan** — theme → player census → supply-chain graph → bottleneck candidates.
- **Anchor Scan** — hot stock → 360° upstream/downstream map → overlooked neighbours.
- **Research Cockpit** — evidence review, run history, triggers, stage changes, and alpha scorecards.

## Repository status

CapexGraph is **pre-alpha**. The current vertical slice provides:

- typed research-domain models;
- evidence requirements for supply-chain edges;
- a seven-stage Theme Scan agent workflow;
- typed, schema-validated agent outputs;
- code-enforced node, edge, evidence, candidate, and ranking integrity;
- a curated no-key A-share semiconductor-wafer golden demo;
- an optional OpenAI Responses API provider;
- Theme and Anchor run creation plus resumable execution;
- SQLite run state plus per-step JSON checkpoints;
- automatic retry and checkpoint resume;
- FastAPI endpoints;
- a React/Vite research cockpit shell;
- tests and CI.

It produces research priorities for human review. It does not produce autonomous investment recommendations or execute trades.

## Quick start

### Python and API

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

capexgraph info
capexgraph demo
capexgraph theme "A股半导体硅片" --market CN
capexgraph anchor "603986" --market CN --execute
capexgraph run <theme-run-id> --provider openai --until graph
capexgraph resume <run-id>
capexgraph runs
capexgraph serve
```

API documentation is available at `http://127.0.0.1:8000/docs`.

`capexgraph demo` needs no API key. It executes a frozen public-source evidence pack dated `2025-04-29`; it is a reproducible product demo, not a current sector report.

### Optional OpenAI provider

```powershell
python -m pip install -e ".[dev,openai]"
$env:OPENAI_API_KEY = "..."
$env:CAPEXGRAPH_MODEL = "your-structured-output-capable-model"
capexgraph theme "AI数据中心电力" --provider openai --execute
```

CapexGraph uses the Responses API with native Pydantic parsing. Model-proposed sources have not yet been independently fetched and verified, so their edges and candidates are forcibly stored as `low` confidence. The live retrieval and filing-validation layer is the next milestone.

### Web cockpit

```powershell
cd apps\web
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Research artifact contract

Every run is stored under `runs/<run-id>/`:

```text
manifest.json       input, versions, providers, timestamps
state.json          resumable workflow state
graph.json          nodes, grounded edges, confidence
evidence.json       source ledger
candidates.json     verdicts, risks, invalidation, triggers
decision.json       final structured decision
checkpoints/        one durable artifact per completed/failed step
```

SQLite at `runs/capexgraph.db` is the local system of record. JSON artifacts remain human-readable and portable. Set `CAPEXGRAPH_STATE_DB` to move the database.

## Runtime API

```text
POST /api/v1/runs/theme
POST /api/v1/runs/anchor
GET  /api/v1/runs
GET  /api/v1/runs/{id}
POST /api/v1/runs/{id}/execute
POST /api/v1/runs/{id}/resume
GET  /api/v1/runs/{id}/checkpoints
```

Create and execute the no-key golden run in one request:

```json
{
  "subject": "A股半导体硅片",
  "market": "CN",
  "as_of_date": "2025-04-29",
  "provider": "fixture",
  "execute": true
}
```

Theme Scan stages are `intake → census → graph → audit → score → debate → decision`. Every stage is resumable and writes a durable checkpoint.

## Design principles

- **Agents judge; code verifies.** Prices, tickers, dates, calculations, and schema checks stay deterministic.
- **No relationship without provenance.** Medium/high-confidence graph edges require evidence IDs.
- **Runs are inspectable assets.** Intermediate outputs are preserved, not hidden behind a final report.
- **Research, not execution.** Live brokerage integration is intentionally outside the MVP.
- **Progressive setup.** The golden demo needs no key; live model providers and premium data remain optional.

See [Theme Scan](docs/THEME_SCAN.md), [MVP plan](docs/MVP.md), and [architecture](docs/ARCHITECTURE.md).

## Disclaimer

CapexGraph is for research and education only. It is not financial, investment, legal, or tax advice.
