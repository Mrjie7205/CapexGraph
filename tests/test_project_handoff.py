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
        "docs/V0_4_PLAN.md",
        "docs/V0_3_PLAN.md",
        "docs/PROJECT_CONTEXT.md",
        "docs/CURRENT_STATUS.md",
        "docs/DECISIONS.md",
        "docs/ARCHITECTURE.md",
        "docs/MARKET_DATA.md",
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
    v03_plan = (ROOT / "docs/V0_3_PLAN.md").read_text(encoding="utf-8")
    v04_plan = (ROOT / "docs/V0_4_PLAN.md").read_text(encoding="utf-8")
    market_data = (ROOT / "docs/MARKET_DATA.md").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert __version__ == package_version == web_version
    assert f"v{__version__}" in roadmap
    assert f"v{__version__}" in status
    assert "Catalyst Scan is only a scaffold" in status
    assert "M3 does not give the model" not in theme_doc
    assert all(issue in v03_plan for issue in ("#4", "#5", "#6", "#7"))
    assert all(milestone in v04_plan for milestone in ("M0", "M1", "M2", "M3", "M4", "M5"))
    assert all(term in v04_plan for term in ("EODHD", "recognition_score", "exposure_score"))
    assert "Catalyst Scan" in v04_plan and "v0.7" in v04_plan
    assert "cross-market data foundation and mainline monitoring" in status
    assert all(
        term in market_data
        for term in ("EODHD_API_TOKEN", "adjusted_close", "unsupported", "quality")
    )
    assert ".env" in gitignore
