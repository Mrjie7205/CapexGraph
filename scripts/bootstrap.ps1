$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -e ".[dev]"

Push-Location "apps\web"
try {
    npm ci
}
finally {
    Pop-Location
}

Write-Host "CapexGraph is ready. Run .\scripts\dev.ps1 to start the API and Cockpit."
