from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLESHEET = ROOT / "apps" / "web" / "src" / "styles.css"


def test_cockpit_typography_has_a_readable_minimum_scale() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")

    for token in (
        "--font-micro: 10px;",
        "--font-caption: 11px;",
        "--font-control: 12px;",
        "--font-body: 14px;",
    ):
        assert token in css

    declared_sizes = [
        float(match.group("size"))
        for match in re.finditer(
            r"\bfont(?:-size)?\s*:\s*[^;{}]*?(?P<size>\d+(?:\.\d+)?)px",
            css,
        )
    ]

    assert declared_sizes
    assert min(declared_sizes) >= 10


def test_mobile_workflow_status_wraps_inside_the_viewport() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    mobile_rules = css.split("@media (max-width: 620px)", maxsplit=1)[1]

    assert ".steps li { grid-template-columns: 32px minmax(0, 1fr);" in mobile_rules
    assert ".steps i { grid-column: 2;" in mobile_rules
