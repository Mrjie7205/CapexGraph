from fastapi.testclient import TestClient

from capexgraph.api.app import app


def test_health() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_create_theme_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    response = TestClient(app).post(
        "/api/v1/runs/theme",
        json={"subject": "A股半导体硅片", "market": "CN", "as_of_date": "2026-07-17"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "theme"
    assert payload["subject"] == "A股半导体硅片"
    assert (tmp_path / payload["id"] / "state.json").is_file()
