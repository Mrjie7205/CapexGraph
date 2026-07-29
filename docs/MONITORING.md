# Forward tracking

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
