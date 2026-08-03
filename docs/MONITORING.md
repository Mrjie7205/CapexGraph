# Monitoring

## Mainline monitor

The v0.4 monitor evaluates themes from the membership that was both valid and known at the requested
date. It computes returns, benchmark-relative strength, breadth, participation, dispersion,
volatility, persistence, and coverage before applying one versioned deterministic policy.

Load and run the frozen three-market acceptance path without credentials:

```powershell
capexgraph themes demo
capexgraph mainline policy
capexgraph mainline run-all --market CN --as-of 2026-08-03 --provider fixture-market
capexgraph mainline status
capexgraph mainline proposals
```

For a single theme/market:

```powershell
capexgraph mainline run memory-semiconductors --market CN --as-of 2026-08-03 --provider eodhd
```

Use `--provider tushare` for an A-share specialist path after configuring `TUSHARE_API_TOKEN`.
Provider selection is explicit and never silently falls back.

`run-all` is the stable scheduler entry point. It is idempotent for the same theme, market,
as-of date, and policy. Failures are isolated per theme/market and remain visible as durable jobs.
The default monitor never calls a model. A state change or official event can create a proposal,
but a user must accept it before any linked research action.

Example Windows Task Scheduler action after each market close:

```text
Program: C:\path\to\CapexGraph\.venv\Scripts\capexgraph.exe
Arguments: mainline run-all --market CN --as-of TODAY --provider eodhd
Start in: C:\path\to\CapexGraph
```

Use a wrapper to replace `TODAY` with the local ISO date and run separate tasks after CN, KR, and
US closes. On cron-capable systems the same CLI command can be scheduled normally. CapexGraph does
not install a system scheduler or keep a cloud worker alive; scheduling ownership remains explicit
and local-first.

The bundled policy `mainline-conservative-2026-08-03` is `experimental`. The state is a research
classification, not an order or recommendation. Policy thresholds must be promoted through a
recorded product decision before becoming production defaults.

The Cockpit's **主线雷达 / Mainline Desk** exposes the same workflow: load the demo or choose a
theme, select CN/US/KR and a provider, synchronize history, run the assessment, inspect quality and
coverage, then accept or reject any proposal.

## Forward tracking

Tracking turns a research candidate into a dated, falsifiable call record. CapexGraph stores the
candidate price and benchmark price on the same market date, then calculates subsequent return,
benchmark return, and alpha from paired snapshots.

```powershell
# Establish a live baseline with the configured market provider
capexgraph tracking add <run-id> <node-id> --market-provider eodhd

# Or use explicit, auditable manual prices
capexgraph tracking add <run-id> <node-id> --price 100 --benchmark-price 100 --as-of 2026-07-17 --no-live

# Capture a later market snapshot
capexgraph tracking snapshot <tracked-id> --live --market-provider eodhd

# Inspect scorecards and move research stages
capexgraph tracking list
capexgraph tracking stage <tracked-id> validated
```

The default benchmark is `000300.SH`. Each adapter performs its own canonical provider mapping:
EODHD receives `000300.SHG`, while the no-key Yahoo fallback receives the Yahoo symbol. A snapshot
is accepted only when the candidate and benchmark share a market date. Both histories pass the
same quality gate and enter the idempotent daily-bar store before pairing.

`CAPEXGRAPH_MARKET_PROVIDER` selects the default. `--market-provider` overrides it for one command.
Selecting EODHD without a local `EODHD_API_TOKEN` fails explicitly; it never falls back silently.
See [`MARKET_DATA.md`](MARKET_DATA.md).

Structured candidate triggers are evaluated only when their metric is deterministic and present in
the snapshot: `price`, `return_pct`, `benchmark_return_pct`, or `alpha_pct`. Financial triggers stay
unevaluated until a new evidence-linked financial metric is attached; text is never guessed into a
number. Fired events are durable and can be acknowledged without deleting their history.

Stages are `research`, `watch`, `validated`, `triggered`, `invalidated`, and `archived`. They are
explicit analyst state, not automated ratings.

Render a portable report:

```powershell
capexgraph report render <run-id>
```

The command writes `report.html` into the run directory. The file is self-contained, escapes all
research text, and includes relationships, candidates, sources, limitations, and next actions.
