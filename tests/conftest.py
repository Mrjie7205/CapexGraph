from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep developer credentials in the local .env out of automated tests."""

    empty_env = tmp_path / "test.env"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("CAPEXGRAPH_ENV_FILE", str(empty_env))
