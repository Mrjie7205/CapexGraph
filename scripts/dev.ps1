$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$Root'; & '$Root\.venv\Scripts\python.exe' -m capexgraph.cli serve --reload"
)

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$Root\apps\web'; npm run dev"
)

Start-Process "http://127.0.0.1:5173"
