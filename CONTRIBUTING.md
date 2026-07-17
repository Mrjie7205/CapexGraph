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
