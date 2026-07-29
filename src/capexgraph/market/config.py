from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _env_candidates(path: Path | None = None) -> list[Path]:
    if path is not None:
        return [path]
    configured = os.getenv("CAPEXGRAPH_ENV_FILE")
    candidates = [Path(configured)] if configured else []
    candidates.extend([Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env"])
    return candidates


def load_project_env(path: Path | None = None) -> Path | None:
    """Load simple KEY=VALUE entries without overriding the process environment."""

    seen: set[Path] = set()
    for candidate in _env_candidates(path):
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            continue
        for raw_line in resolved.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            name, separator, value = line.partition("=")
            name = name.strip()
            if not separator or not _ENV_NAME.fullmatch(name):
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(name, value)
        return resolved
    return None


@dataclass(frozen=True)
class MarketSettings:
    provider: str = "yahoo"
    eodhd_api_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, *, load_env: bool = True) -> MarketSettings:
        if load_env:
            load_project_env()
        provider = os.getenv("CAPEXGRAPH_MARKET_PROVIDER", "yahoo").strip().lower()
        token = os.getenv("EODHD_API_TOKEN", "").strip() or None
        return cls(provider=provider, eodhd_api_token=token)

    def public_status(self) -> dict[str, str | bool]:
        return {
            "configured_provider": self.provider,
            "eodhd_token_configured": self.eodhd_api_token is not None,
        }
