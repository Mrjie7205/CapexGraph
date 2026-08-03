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

The built-in filing provider captures the official SEC Company Facts response, stores and hashes
the raw JSON as Evidence, and deterministically normalizes a bounded US-GAAP metric set:

- income statement: revenue, operating income, and net income;
- cash flow: operating cash flow, capital expenditures, and derived free cash flow; and
- balance sheet: cash, debt, and property/plant/equipment.

```powershell
capexgraph financials extract <run-id> --identifier GOOGL
capexgraph financials list <run-id>
capexgraph evidence review <run-id> <sec-companyfacts-evidence-id>
```

Each fact stores canonical company/ticker, statement, normalized metric, original concept, period,
fiscal fields, form, filed date, accession, value/unit, fact type, evidence ID, and exact JSON
locator. A derived fact additionally stores its formula and input fact IDs. A later restatement is
stored beside the original value; it never silently overwrites history. Missing values remain
`missing` with `value=null`, never zero. Unit or same-filing period/value conflicts fail
deterministically and are persisted as provider errors.

The raw response is captured but not automatically human-approved. It can be reviewed through the
same evidence ledger. Theme and Anchor prompts receive a bounded copy of the stored facts on their
next uncompleted stage.

The legacy evidence-linked CSV path remains available for company-specific metrics not covered by
the SEC adapter. Its columns are:

```text
ticker,metric,period_end,value,unit,source_evidence_id
```

```powershell
capexgraph financials import <run-id> .\financial_metrics.csv
```

When `source_evidence_id` is present, the import fails unless that evidence exists in the same run.

Automatic structured extraction supports SEC Company Facts and a conservative OpenDART account
subset. Reviewed regulator/issuer Evidence can also produce deterministic fact candidates that
require explicit human acceptance. A-share disclosures without reliable structured fields remain
candidate-only rather than being guessed into facts.

SEC asks automated clients to send an identifying User-Agent. Configure
`CAPEXGRAPH_SEC_USER_AGENT` in the repository-local `.env` with your application/name and a real
contact address; the SEC adapters load it automatically. A 403 or network block is persisted as a
provider failure and shown in the Cockpit; CapexGraph does not bypass the regulator's access
controls. Exact CIK input bypasses only the separate remote ticker-registry lookup, not the Company
Facts endpoint itself.

## Official filing event calendar

The v0.5 development path can turn SEC filing metadata into an append-only calendar without
pretending the filing title proves a specific business event:

```powershell
capexgraph events sync <run-id> --identifier GOOGL --form 10-Q --form 8-K
capexgraph events list <run-id>
```

The sync writes the same official documents into the source-suggestion queue and maps periodic
reports to `financial_report`; other forms remain `regulatory_filing`. At this point the event
references a suggestion, not captured Evidence.

Capture the source through the existing guarded path:

```powershell
capexgraph sources capture <run-id> <suggestion-id>
capexgraph events list <run-id> --history
```

Successful capture appends a second event version with `evidence_id` and source hash. The original
discovery version remains queryable. Current and historical views are available through:

```powershell
capexgraph events list <run-id>
capexgraph events list <run-id> --history
capexgraph events list <run-id> --as-of 2026-07-23
capexgraph events list <run-id> --type financial_report
```

`known_at` is the SEC acceptance timestamp when available. `observed_at` is when CapexGraph found or
captured the record. `--as-of` applies the system-observed cutoff so a later backfill cannot alter
what an earlier run knew.

SEC discovery lazily loads bounded historical submission shards. CNINFO/SSE/SZSE/BSE and
OpenDART/KIND official discovery adapters are also available. Issuer calendars still use the
guarded manual issuer-source path, and content-level interpretation remains conservative.

## Evidence modes and execution

`partial` is the default. It permits research with incomplete coverage, but unreviewed/model-only
relationships are forced to low confidence and the report exposes the gap.

`strict` requires at least one reviewed, hash-valid capture before a non-fixture workflow begins and
blocks any medium/high relationship proposal whose citations are not all reviewed:

```powershell
capexgraph theme "AI data-center power" --market US --provider openai `
  --evidence-mode strict
capexgraph run <run-id> --provider openai --evidence-mode strict
```

Failures are ordinary durable checkpoints. Capture/review the missing source and use
`capexgraph resume <run-id>`; completed stages are not regenerated.
