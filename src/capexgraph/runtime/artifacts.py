from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a text artifact atomically so interruptions cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace a binary artifact atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialize a portable JSON artifact and replace it atomically."""
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    )
