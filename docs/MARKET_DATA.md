# Market data foundation

This document describes the v0.4 daily-history slice currently implemented in CapexGraph. It is a
data and research-observability layer, not a trading feed.

## Provider selection

Provider selection is explicit:

```dotenv
# Licensed cross-market path
EODHD_API_TOKEN=your-token
CAPEXGRAPH_MARKET_PROVIDER=eodhd

# Or the no-key fallback
CAPEXGRAPH_MARKET_PROVIDER=yahoo
```

The repository-local `.env` is ignored by Git. Process environment variables take precedence over
the file. `capexgraph market providers` and `GET /api/v1/market/providers` reveal only whether a
token is configured; they never return its value.

Selecting EODHD without `EODHD_API_TOKEN` is an error. CapexGraph does not silently fall back to
Yahoo, because a hidden provider change would make quality and licensing claims misleading.

## Canonical ticker mapping

| CapexGraph identity | EODHD symbol | Market |
|---|---|---|
| `AAPL` or `AAPL.US` | `AAPL.US` | United States |
| `688019.SH` | `688019.SHG` | Shanghai |
| `000001.SZ` | `000001.SHE` | Shenzhen |
| `000660.KO` | `000660.KO` | KRX main board |
| `247540.KQ` | `247540.KQ` | KOSDAQ |

Beijing Stock Exchange (`.BJ`) is explicitly unsupported by the EODHD adapter. A missing mapping
raises a structured provider error; an empty array is never treated as successful coverage.

## Price semantics

EODHD daily records are preserved without inventing an adjusted OHLC series:

- `open`, `high`, `low`, and `close` are stored as raw prices;
- `adjusted_close` is stored separately and is used for return calculations;
- `volume` is stored as the provider returns it;
- snapshot display price, six-month range, and SMA use raw prices;
- 1-month and 3-month returns use adjusted close, falling back to raw close only when adjustment is
  missing and recording a warning.

These semantics follow the
[EODHD End-of-Day Historical Data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes):
raw OHLC, split-and-dividend-adjusted close, and split-adjusted volume.

Each normalized `MarketBarSet` also records market, exchange, currency, timezone, provider,
provider version, retrieval time, credential-free source URL, and SHA-256 raw-response hash.

## Persistence and licensed data boundary

Schema migration 4 adds:

- `market_bars`, keyed by ticker, provider, and trade date; and
- `market_quality_reports`, keyed by ticker, provider, and raw-response hash.

Upserts make overlapping incremental fetches idempotent. When the requested history already exists,
CapexGraph refetches a seven-day overlap; when the requested window extends farther back, it
backfills from the earlier target date.

Raw provider responses are retained locally under:

```text
runs/_market_data/raw/<provider>/<ticker>/<sha256>.json
```

The entire runtime directory is Git-ignored. Licensed raw responses, tokens, and local databases
must not be committed or copied into public fixtures. Public tests use synthetic `httpx` responses.

## Quality gate

Before normalized bars are accepted, deterministic checks cover:

- empty history;
- non-ascending and duplicate dates;
- non-positive or internally inconsistent OHLC;
- negative volume;
- missing or non-positive adjusted close;
- dates after the requested end date; and
- stale latest observations.

Structural errors produce `fail`, persist a diagnostic quality report and raw response, and block
bar persistence. Missing adjusted close and staleness currently produce `warn`, so the issue remains
visible without confusing a market holiday or suspension with corrupt OHLC.

This first gate does not yet validate exchange calendars, split/dividend events, suspensions, price
limits, delistings, or cross-provider price differences. Those frozen comparison fixtures and an
A-share specialist validation adapter remain M1 work.

## CLI

```powershell
# Credential presence and provider capabilities, with no secret values
capexgraph market providers

# Normalize, quality-check, and persist an overlapping incremental update
capexgraph market sync 688019.SH AAPL 000660.KO --days 730

# Attach the same quality-checked history and a deterministic snapshot to a run
capexgraph market snapshot <run-id> 688019.SH --provider eodhd --days 400

# Force the no-key route
capexgraph market snapshot <run-id> 688019.SH --provider yahoo
```

Live tracking accepts the same provider boundary:

```powershell
capexgraph tracking add <run-id> <node-id> --market-provider eodhd
capexgraph tracking snapshot <tracked-id> --live --market-provider eodhd
```

Candidate and benchmark data must still share one market date before a tracking snapshot is stored.

## API

```text
GET  /api/v1/market/providers
POST /api/v1/market/sync
POST /api/v1/runs/{run-id}/market
```

Example sync body:

```json
{
  "tickers": ["688019.SH", "AAPL", "000660.KO"],
  "provider": "eodhd",
  "days": 730
}
```

The API is intended to run server-side. Do not place `EODHD_API_TOKEN` in the React application,
browser storage, query parameters, or request bodies.

## Remaining v0.4 work

- frozen US/CN/KR/KOSDAQ provider fixtures and independent comparison reports;
- exchange-calendar, suspension, corporate-action, and price-discontinuity checks;
- an A-share specialist enhancement/validation provider;
- point-in-time theme registry and historical membership imports;
- theme metrics and approved versioned mainline policy;
- scheduled post-close jobs, linked re-evaluation, and Cockpit data-quality views.
