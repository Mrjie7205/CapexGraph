# Project context

## Why CapexGraph exists

The original Serenity bottleneck-hunter skill proved that a supply-chain bottleneck method can be
useful through a low-friction chat interface. CapexGraph is a separate product for the next need:
a professional research workspace with persistent runs, inspectable intermediate work, explicit
evidence, repeatable validation, and forward measurement.

The skill and this repository serve different users and should remain independently usable. A fix
may be applied to both projects deliberately, but neither project is a runtime dependency of the
other.

## Product thesis

The core loop is:

```text
discover opportunity → verify relationships → form judgment → track whether it plays out
```

CapexGraph starts before a ticker rating. It asks where spending or repricing is occurring, which
relationships are evidenced, which adjacent nodes may matter, what would invalidate the thesis,
and whether the resulting research priority later outperformed its stated benchmark.

## Product shape

CapexGraph is workflow-driven, not “agent-driven” for its own sake and not a literal clone of
TradingAgents. Specialist agents handle bounded research judgment. Deterministic tools and code
remain authoritative for identities, dates, prices, calculations, evidence references, confidence
gates, and persistence. The runtime controls order, retries, checkpoints, and resume.

The same durable run is available through:

- Web Cockpit for normal research work;
- CLI for reproducible and batch workflows; and
- Python/FastAPI interfaces for integration and extension.

## Primary users

- a thematic investor mapping capital expenditure into upstream bottlenecks;
- an analyst reverse-mapping a repriced anchor company into evidence-backed peers and neighbours;
- a researcher maintaining a dated candidate queue and measuring later outcomes; and
- a developer adding a trusted model, filing, source, or market-data provider.

## First-class objects

- **ResearchRun** — subject, market, as-of date, mode, provider versions, workflow state.
- **Evidence** — source identity, retrieval/hash state, excerpt, local artifact, review state.
- **SupplyChainNode / Edge** — canonical entities and evidence-linked relationships.
- **Candidate** — thesis, risks, invalidation, triggers, verdict, confidence.
- **Tracking record** — original call and benchmark baseline, later snapshots, alpha, events, stage.

Runs are inspectable assets, not disposable prompt transcripts. JSON artifacts provide portability;
SQLite provides durable local querying and execution state.

## Shipped research modes

- **Theme Scan** — theme boundary → census → graph → audit → bottleneck score → debate → decision.
- **Anchor Scan** — anchor identity → repricing cause → neighbour graph → audit → financial compare
  → debate → decision.

`Catalyst Scan` is a reserved `RunMode` and pipeline scaffold only. Its intended product direction
is documented in `ROADMAP.md`; it is not a shipped research workflow.

## Trust model

1. A curated fixture is a frozen, human-prepared demo and may preserve stronger confidence.
2. A model proposal is an unverified research lead and is forced to low confidence.
3. A captured source has verified bytes and hash, not verified interpretation.
4. A reviewed capture may support a stronger claim if every cited item remains unchanged.
5. The edge audit can accept, downgrade, or reject; it cannot invent missing provenance.

## Success criteria

CapexGraph succeeds when it makes a human analyst's reasoning easier to inspect, challenge,
continue, and measure. More prose, more agents, or a more confident verdict are not success unless
they improve provenance, falsifiability, usability, or reproducibility.
