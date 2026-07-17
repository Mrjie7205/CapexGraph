from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a text artifact atomically so interruptions cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
