# Official disclosures, events, and reviewed facts

CapexGraph v0.5 treats discovery metadata, captured Evidence, interpreted events, and financial
facts as different trust layers. Finding an announcement does not make its title a verified fact.

## Provider coverage

| Market | Provider | Credential | Role |
|---|---|---|---|
| US | SEC EDGAR | identifying `CAPEXGRAPH_SEC_USER_AGENT` | submissions, bounded historical shards, Company Facts |
| CN | CNINFO | none in the adapter contract | listed-company announcements |
| CN | SSE / SZSE / BSE | none in the adapter contract | exchange announcements and coverage cross-check |
| KR | OpenDART | `OPENDART_API_KEY` | disclosure list and normalized official financial accounts |
| KR | KIND/KRX | none in the adapter contract | exchange disclosure supplement |

Run `capexgraph events providers` or open **来源与证据** in the Cockpit to inspect current
capability and configuration. Status responses never return secret values.

Real endpoints may enforce rate limits, headers, access policies, anti-automation controls, or
change their public response shape. A configured adapter is not a guarantee of live availability;
errors remain visible and no provider silently substitutes for another.

## Trust flow

```text
official discovery metadata
  → SourceSuggestion
  → conservative CorporateEventVersion
  → guarded HTML/PDF capture
  → captured Evidence + SHA-256
  → explicit human review
  → reviewed Evidence link
  → deterministic fact candidate
  → explicit accept/reject
  → immutable FinancialFact
```

- Discovery can establish that an official source published an item.
- Capture proves which bytes CapexGraph retrieved and hashes them.
- Review records that a human approved the unchanged capture.
- Event mapping is conservative: a periodic report can be classified as a financial report, but a
  generic filing or headline does not prove a specific earnings, guidance, or capex conclusion.
- Reviewed disclosure extraction is allowlisted and deterministic. It proposes candidates; it does
  not let an LLM write numbers into the fact store.

## Point-in-time behavior

`known_at` is when the source made information public. `observed_at` is when this workspace actually
ingested it. Historical system queries use `observed_at` as the knowledge cutoff and keep
`known_at` for audit. Updates append event versions under one stable key; they never rewrite what a
past run knew.

SEC historical submission shards are fetched lazily and only until the requested bound is met.
OpenDART facts preserve report code, fiscal period, account identity, currency/unit, official
response hash, and retrieval lineage.

## CLI paths

```powershell
capexgraph events providers
capexgraph events sync <run-id> --provider sec --identifier GOOGL --form 10-Q
capexgraph events sync <run-id> --provider cninfo --identifier 688019.SH
capexgraph events sync <run-id> --provider opendart --identifier 000660
capexgraph events list <run-id> --history

capexgraph financials preview-reviewed <run-id> <evidence-id>
capexgraph financials candidates <run-id>
capexgraph financials decide <run-id> <candidate-id> --accept
```

Use `capexgraph --help` and subcommand help for the exact provider-specific identifiers. The
Cockpit is the recommended non-technical path because it limits provider choices by market and
keeps capture, review, and fact acceptance visibly separate.

## Monitoring bridge

When a new official event maps to a member of a known theme, CapexGraph may create a
`reevaluate_candidates` proposal tied to the latest mainline assessment. It does not automatically
launch a model, alter the original run, or convert the event into an investment instruction. A
human must accept or reject the proposal.

## Boundaries

- Jin10 and other aggregators are discovery signals, not official Evidence.
- A reviewed source does not mean every interpretation of it is correct.
- Missing structured data remains missing; headline prose is not converted into a precise number.
- Issuer IR pages can enter through the guarded manual official-source path, but a complete global
  issuer-calendar adapter is not claimed.
- Broker consensus estimates and historical revisions belong to v0.6.
