import pytest
from httpx import ASGITransport, AsyncClient

from capexgraph.api.app import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["ok"] is True


@pytest.mark.anyio
async def test_market_provider_status_redacts_credentials(monkeypatch) -> None:
    token = "api-test-token-that-must-not-be-returned"
    monkeypatch.setenv("CAPEXGRAPH_MARKET_PROVIDER", "eodhd")
    monkeypatch.setenv("EODHD_API_TOKEN", token)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/market/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configuration"] == {
        "configured_provider": "eodhd",
        "eodhd_token_configured": True,
    }
    assert token not in response.text


@pytest.mark.anyio
async def test_create_theme_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/runs/theme",
            json={"subject": "A股半导体硅片", "market": "CN", "as_of_date": "2026-07-17"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "theme"
        assert payload["subject"] == "A股半导体硅片"
        assert (tmp_path / payload["id"] / "state.json").is_file()


@pytest.mark.anyio
async def test_create_only_strict_workspace_and_read_coverage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/runs/theme",
            json={
                "subject": "Alphabet AI CapEx",
                "market": "US",
                "provider": "openai",
                "evidence_mode": "strict",
                "execute": False,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "created"
        assert payload["manifest"]["evidence_mode"] == "strict"

        coverage = await client.get(f"/api/v1/runs/{payload['id']}/coverage")
        assert coverage.status_code == 200
        assert coverage.json()["status"] == "empty"
        assert coverage.json()["strict_ready"] is False


@pytest.mark.anyio
async def test_create_and_execute_fixture_theme_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/runs/theme",
            json={
                "subject": "A股半导体硅片",
                "market": "CN",
                "as_of_date": "2025-04-29",
                "provider": "fixture",
                "execute": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "needs_review"
        assert payload["manifest"]["model_provider"] == "fixture"
        assert len(payload["candidates"]) == 4
        assert (tmp_path / payload["id"] / "decision.json").is_file()


@pytest.mark.anyio
async def test_execute_and_resume_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = (
            await client.post(
                "/api/v1/runs/anchor",
                json={"subject": "兆易创新", "market": "CN", "provider": "fixture"},
            )
        ).json()

        executed = await client.post(
            f"/api/v1/runs/{created['id']}/execute",
            json={"until": "graph", "max_attempts": 2},
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "needs_review"

        resumed = await client.post(
            f"/api/v1/runs/{created['id']}/resume",
            json={"max_attempts": 2},
        )
        assert resumed.status_code == 200
        assert all(step["status"] == "completed" for step in resumed.json()["pipeline"])

        checkpoints = await client.get(f"/api/v1/runs/{created['id']}/checkpoints")
        assert checkpoints.status_code == 200
        assert len(checkpoints.json()) == len(resumed.json()["pipeline"])


@pytest.mark.anyio
async def test_create_and_execute_fixture_anchor_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/runs/anchor",
            json={
                "subject": "603986",
                "market": "CN",
                "as_of_date": "2026-04-23",
                "provider": "fixture",
                "execute": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "needs_review"
        assert payload["manifest"]["anchor_node_id"] == "company-gigadevice"
        assert len(payload["candidates"]) == 3
        assert (tmp_path / payload["id"] / "financials.json").is_file()

        artifact = await client.get(
            f"/api/v1/runs/{payload['id']}/artifacts/decision.json"
        )
        assert artifact.status_code == 200
        assert artifact.json()["research_status"] == "needs_review"


@pytest.mark.anyio
async def test_background_execute_is_pollable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = (
            await client.post(
                "/api/v1/runs/theme",
                json={
                    "subject": "A股半导体硅片",
                    "market": "CN",
                    "provider": "fixture",
                },
            )
        ).json()
        queued = await client.post(
            f"/api/v1/runs/{created['id']}/execute",
            json={"provider": "fixture", "background": True},
        )
        assert queued.status_code == 200
        polled = await client.get(f"/api/v1/runs/{created['id']}")
        assert polled.json()["status"] == "needs_review"


@pytest.mark.anyio
async def test_tracking_and_report_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        run = (
            await client.post(
                "/api/v1/runs/theme",
                json={
                    "subject": "A股半导体硅片",
                    "market": "CN",
                    "provider": "fixture",
                    "execute": True,
                },
            )
        ).json()
        node_id = run["candidates"][0]["node_id"]
        tracked = await client.post(
            f"/api/v1/runs/{run['id']}/tracking",
            json={
                "node_id": node_id,
                "call_date": "2025-04-29",
                "call_price": 100,
                "call_benchmark_price": 100,
                "capture_live": False,
            },
        )
        assert tracked.status_code == 200
        tracked_id = tracked.json()["id"]

        snapshot = await client.post(
            f"/api/v1/tracking/{tracked_id}/snapshots",
            json={
                "as_of_date": "2025-05-29",
                "price": 110,
                "benchmark_price": 105,
            },
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["alpha_pct"] == 5

        scoreboard = await client.get("/api/v1/tracking")
        assert scoreboard.status_code == 200
        assert scoreboard.json()[0]["tracked"]["id"] == tracked_id

        report = await client.get(f"/api/v1/runs/{run['id']}/report")
        assert report.status_code == 200
        assert "CapexGraph" in report.text
