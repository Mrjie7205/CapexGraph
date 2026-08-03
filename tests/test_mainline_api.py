from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from capexgraph.api.app import app
from capexgraph.cli import app as cli_app
from capexgraph.domain import MarketBar, MarketBarSet
from capexgraph.market import MarketDataStore


def _bar_set(ticker: str, provider: str, scale: float) -> MarketBarSet:
    start = date(2026, 6, 1)
    bars = [
        MarketBar(
            date=start + timedelta(days=index),
            open=(100 + index) * scale,
            high=(102 + index) * scale,
            low=(99 + index) * scale,
            close=(101 + index) * scale,
            adjusted_close=(101 + index) * scale,
            volume=1000,
        )
        for index in range(40)
    ]
    raw = json.dumps([item.model_dump(mode="json") for item in bars], default=str).encode()
    return MarketBarSet(
        ticker=ticker,
        market="CN",
        exchange="SSE STAR",
        currency="CNY",
        timezone="Asia/Shanghai",
        provider=provider,
        provider_version="1",
        raw_hash=hashlib.sha256(raw).hexdigest(),
        bars=bars,
    )


@pytest.mark.anyio
async def test_theme_and_mainline_api_exposes_point_in_time_and_partial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(tmp_path / "mainline-api.db"))
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        imported = await client.post("/api/v1/themes/fixture")
        assert imported.status_code == 200
        assert imported.json()["membership_count"] == 10

        themes = await client.get("/api/v1/themes")
        assert themes.status_code == 200
        assert themes.json()[0]["theme_id"] == "memory-semiconductors"

        snapshot = await client.post(
            "/api/v1/themes/memory-semiconductors/snapshots",
            json={"as_of_date": "2024-03-01", "market": "CN"},
        )
        assert snapshot.status_code == 200
        assert {item["ticker"] for item in snapshot.json()["members"]} == {
            "603986.SH",
            "605358.SH",
        }

        policy = await client.post("/api/v1/mainline/policies/default")
        assert policy.status_code == 200
        assert policy.json()["experimental"] is True

        job = await client.post(
            "/api/v1/mainline/run",
            json={
                "theme_id": "memory-semiconductors",
                "market": "CN",
                "as_of_date": "2026-08-03",
                "provider": "not-synced",
            },
        )
        assert job.status_code == 200
        assert job.json()["status"] == "partial"

        assessments = await client.get(
            "/api/v1/mainline/assessments?theme_id=memory-semiconductors"
        )
        assert assessments.status_code == 200
        assert assessments.json()[0]["state"] == "insufficient"


@pytest.mark.anyio
async def test_market_comparison_api_uses_persisted_explicit_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "comparison-api.db"
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(db_path))
    store = MarketDataStore(db_path)
    store.save_bars(_bar_set("688019.SH", "eodhd", 1.0))
    store.save_bars(_bar_set("688019.SH", "tushare", 1.001))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/market/compare",
            json={
                "ticker": "688019.SH",
                "primary_provider": "eodhd",
                "reference_provider": "tushare",
                "as_of_date": "2026-07-10",
            },
        )
        listed = await client.get("/api/v1/market/comparisons?ticker=688019.SH")

    assert response.status_code == 200
    assert response.json()["status"] == "pass"
    assert response.json()["overlap_count"] == 40
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == response.json()["id"]


def test_theme_and_mainline_cli_no_key_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(tmp_path / "mainline-cli.db"))
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    runner = CliRunner()

    imported = runner.invoke(cli_app, ["themes", "demo"])
    snapshot = runner.invoke(
        cli_app,
        [
            "themes",
            "snapshot",
            "memory-semiconductors",
            "--as-of",
            "2025-01-02",
            "--market",
            "CN",
        ],
    )
    policy = runner.invoke(cli_app, ["mainline", "policy"])
    job = runner.invoke(
        cli_app,
        [
            "mainline",
            "run",
            "memory-semiconductors",
            "--market",
            "CN",
            "--as-of",
            "2026-08-03",
            "--provider",
            "not-synced",
        ],
    )

    assert imported.exit_code == snapshot.exit_code == policy.exit_code == job.exit_code == 0
    assert "Synthetic frozen history" in imported.stdout
    assert '"status": "partial"' in job.stdout
