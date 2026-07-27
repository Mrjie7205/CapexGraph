# Live research tools

v0.3 separates source discovery from evidence capture. A discovery result is a queue item, not a
fact and not Evidence.

## Official-source review queue

```text
suggested → selected → capture_pending → captured Evidence
       ↘ dismissed          ↘ capture_failed → retry
                             ↘ duplicate
```

Discover recent SEC filings by exact ticker, SEC company name, or CIK:

```powershell
capexgraph sources discover <run-id> --identifier GOOGL
capexgraph sources list <run-id>
capexgraph sources capture <run-id> <suggestion-id>
```

Or add a known issuer/regulator URL without downloading it:

```powershell
capexgraph sources add <run-id> "https://issuer.example/report" `
  --title "Issuer report" `
  --issuer-domain issuer.example
```

The queue records provider/version, discovery reason, authority classification, canonical URL,
status, errors, duplicate identity, and any resulting evidence ID. URL duplicates and identical
downloaded bytes are handled separately. SEC suggestions are prioritized as regulator sources but
still require capture and human review. Discovery-provider errors and capture failures remain
visible after restart.

## Evidence lifecycle

```text
proposed → captured → reviewed
                    ↘ rejected
```

`captured` means CapexGraph downloaded the source, stored the raw file and extracted text, and recorded a SHA-256 hash. `reviewed` additionally means a human approved the unchanged capture for use in grounded claims. A hash proves file integrity, not that a claim is economically correct.

```powershell
capexgraph evidence collect <run-id> "https://example.com/report.pdf" `
  --id company-annual-report `
  --title "Company annual report" `
  --kind filing

capexgraph evidence review <run-id> company-annual-report
```

The collector accepts public HTTP/HTTPS sources, follows redirects, limits each source to 20 MiB, blocks credentials and private/loopback destinations, stores the original HTML/PDF under `sources/`, and writes extracted text beside it. Set `CAPEXGRAPH_ALLOW_PRIVATE_URLS=1` only for an intentionally local deployment.

Redirect destinations are validated before they are requested. Only HTML and PDF captures enter the
evidence ledger; unsupported content types, oversized files, unsafe destinations, and failed
downloads stay in the source queue as explicit failures.

## Ticker identity

```powershell
capexgraph ticker resolve 兆易创新
capexgraph ticker resolve 603986
```

The bundled registry owns company names and aliases. Code formatting can canonicalize an unknown six-digit A-share ticker, but it will not invent the associated company name. Extend the registry with `CAPEXGRAPH_TICKER_FILE`.

## Market snapshot

```powershell
capexgraph market snapshot <run-id> 603986
```

The default no-key adapter captures adjusted daily history from Yahoo's chart endpoint and calculates 1-month/3-month returns, six-month range position, distance from the six-month high, SMA50 state, and a coarse stage. The raw bars and the derived snapshot are saved together and hashed. This best-effort public feed is suitable for research workflow demos; production users should implement the provider protocol against their licensed feed.

## Financial facts

CapexGraph imports normalized financial facts instead of scraping unverified numbers into the system of record. The CSV columns are:

```text
ticker,metric,period_end,value,unit,source_evidence_id
```

```powershell
capexgraph financials import <run-id> .\financial_metrics.csv
```

When `source_evidence_id` is present, the import fails unless that evidence exists in the same run.
