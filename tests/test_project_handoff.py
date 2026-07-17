from __future__ import annotations

import json
import tomllib
from pathlib import Path

from capexgraph import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_cross_session_handoff_files_exist() -> None:
    required = [
        "AGENTS.md",
        "ROADMAP.md",
        "docs/PROJECT_CONTEXT.md",
        "docs/CURRENT_STATUS.md",
        "docs/DECISIONS.md",
        "docs/ARCHITECTURE.md",
        "CONTRIBUTING.md",
        ".github/pull_request_template.md",
    ]
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    assert missing == [], f"Missing cross-session handoff files: {missing}"


def test_handoff_version_and_capability_boundaries_do_not_drift() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        package_version = tomllib.load(handle)["project"]["version"]
    web_version = json.loads(
        (ROOT / "apps/web/package.json").read_text(encoding="utf-8")
    )["version"]
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    status = (ROOT / "docs/CURRENT_STATUS.md").read_text(encoding="utf-8")
    theme_doc = (ROOT / "docs/THEME_SCAN.md").read_text(encoding="utf-8")

    assert __version__ == package_version == web_version
    assert f"v{__version__}" in roadmap
    assert f"v{__version__}" in status
    assert "Catalyst Scan is only a scaffold" in status
    assert "M3 does not give the model" not in theme_doc
