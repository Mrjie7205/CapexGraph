# Contributing

CapexGraph accepts focused bug fixes, provider adapters, research schemas, source fixtures, and
Cockpit improvements. Keep facts, inference, and market data visibly separate.

## Local checks

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Push-Location apps\web
npm run build
Pop-Location
```

Every relationship at medium or high confidence must carry evidence IDs. Golden fixtures must
be frozen, source-linked, reproducible, and clearly dated. Do not add private research outputs,
credentials, scraped paywalled text, or unlicensed datasets.

Pull requests should describe the user path, evidence boundary, test coverage, and any schema or
migration impact.

## Handoff documentation contract

Any pull request that changes shipped behavior must update the relevant workflow document and
`docs/CURRENT_STATUS.md`. Update `CHANGELOG.md` for user-visible behavior. Update `ROADMAP.md` when
scope, priority, or acceptance criteria change, and add an entry to `docs/DECISIONS.md` when a trust
boundary, durable object, provider contract, or repository boundary changes.

Do not make a new session depend on private chat history or local memory. `AGENTS.md` and the files
it links are the repository-owned continuation contract.
