from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from capexgraph.domain import LiveProviderHealth, LiveVerificationTaskStatus
from capexgraph.live.config import LiveProviderSettings
from capexgraph.live.store import LiveSignalStore
from capexgraph.runtime import database_status


def build_live_diagnostics(db_path: Path | None = None) -> dict[str, Any]:
    """Inspect local live-gateway readiness without network calls or secret output."""

    store = LiveSignalStore(db_path)
    provider = LiveProviderSettings.from_environment()
    schema = database_status(store.db_path)
    with closing(sqlite3.connect(store.db_path)) as connection:
        integrity_row = connection.execute("PRAGMA quick_check").fetchone()
    integrity = str(integrity_row[0]) if integrity_row else "unknown"
    checkpoints = store.list_checkpoints()
    failed_tasks = store.list_verification_tasks(
        statuses=[LiveVerificationTaskStatus.FAILED]
    )
    open_tasks = store.list_verification_tasks(
        statuses=[
            LiveVerificationTaskStatus.PENDING,
            LiveVerificationTaskStatus.SOURCE_SUGGESTED,
            LiveVerificationTaskStatus.CAPTURE_PENDING,
            LiveVerificationTaskStatus.CAPTURED,
        ]
    )
    soak_reports = store.list_soak_reports(limit=1)
    warnings: list[str] = []
    if not provider.mcp_bearer_token:
        warnings.append("MCP live polling is not configured.")
    if not provider.websocket_secret_key:
        warnings.append("WebSocket live streaming is not configured.")
    if any(
        item.health in {LiveProviderHealth.DEGRADED, LiveProviderHealth.OFF}
        for item in checkpoints
    ):
        warnings.append("At least one persisted live channel is degraded or off.")
    if failed_tasks:
        warnings.append(f"{len(failed_tasks)} official-source task(s) need retry.")
    if not soak_reports:
        warnings.append("No persisted live soak report is available.")
    elif not soak_reports[0].passed:
        warnings.append("The latest live soak report did not pass.")

    ready = (
        schema.up_to_date
        and integrity == "ok"
        and not provider.configuration_errors
        and not failed_tasks
        and bool(soak_reports)
        and soak_reports[0].passed
    )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "ready": ready,
        "database": {
            "path": str(store.db_path),
            "integrity": integrity,
            "schema_version": schema.current_version,
            "latest_schema_version": schema.latest_version,
            "up_to_date": schema.up_to_date,
        },
        "configuration": provider.public_status(),
        "channels": [
            {
                "key": item.key,
                "health": item.health.value,
                "updated_at": item.updated_at.isoformat(),
                "error": item.error,
            }
            for item in checkpoints
        ],
        "verification_queue": {
            "open": len(open_tasks),
            "failed": len(failed_tasks),
        },
        "latest_soak": (
            soak_reports[0].model_dump(mode="json") if soak_reports else None
        ),
        "warnings": warnings,
        "notice": (
            "Readiness covers local integrity and completed release gates; "
            "it is not a market-data or trading guarantee."
        ),
    }
