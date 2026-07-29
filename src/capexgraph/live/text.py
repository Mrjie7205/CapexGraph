from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(value: object, *, limit: int = 4000) -> str:
    """Convert provider HTML-ish text into bounded plain text."""

    text = html.unescape(_TAG.sub(" ", str(value or "")))
    return _SPACE.sub(" ", text).strip()[:limit]
