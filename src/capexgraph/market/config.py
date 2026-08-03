from __future__ import annotations

import os
from dataclasses import dataclass, field

from capexgraph.config import load_project_env


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
