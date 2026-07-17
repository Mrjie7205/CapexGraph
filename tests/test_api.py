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
