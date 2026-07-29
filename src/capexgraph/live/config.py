from __future__ import annotations

import os
from dataclasses import dataclass, field

from capexgraph.config import load_project_env

JIN10_MCP_URL = "https://mcp.jin10.com/mcp"
JIN10_WS_ENDPOINTS = {
    "flash": "wss://open-api-ws.jin10.com/flash",
    "calendar": "wss://open-api-ws.jin10.com/calendar",
    "quote": "wss://open-api-ws.jin10.com/quotes",
}
JIN10_DAILY_HARD_LIMIT = 1500


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class LiveProviderSettings:
    mcp_bearer_token: str | None = field(default=None, repr=False)
    websocket_secret_key: str | None = field(default=None, repr=False)
    mcp_url: str = JIN10_MCP_URL
    mcp_timeout_seconds: float = 20.0
    mcp_call_budget: int = 1200
    mcp_enabled: bool = True
    websocket_enabled: bool = True
    flash_categories: tuple[int, ...] = (1, 4)
    calendar_categories: tuple[str, ...] = ("cj",)
    quote_categories: tuple[str, ...] = ()
    configuration_errors: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls, *, load_env: bool = True) -> LiveProviderSettings:
        if load_env:
            load_project_env()
        errors: list[str] = []
        try:
            timeout = float(
                os.getenv("CAPEXGRAPH_JIN10_MCP_TIMEOUT_SECONDS", "20").strip()
            )
            if not 1 <= timeout <= 120:
                raise ValueError
        except ValueError:
            timeout = 20.0
            errors.append(
                "CAPEXGRAPH_JIN10_MCP_TIMEOUT_SECONDS must be between 1 and 120."
            )
        try:
            budget = int(os.getenv("CAPEXGRAPH_JIN10_MCP_CALL_BUDGET", "1200").strip())
            if not 1 <= budget <= JIN10_DAILY_HARD_LIMIT:
                raise ValueError
        except ValueError:
            budget = 1200
            errors.append(
                "CAPEXGRAPH_JIN10_MCP_CALL_BUDGET must be between 1 and 1500."
            )
        try:
            flash_categories = tuple(
                int(item)
                for item in _csv(
                    "CAPEXGRAPH_JIN10_WS_FLASH_CATEGORIES",
                    ("1", "4"),
                )
            )
            if any(item not in {1, 2, 3, 4, 5} for item in flash_categories):
                raise ValueError
        except ValueError:
            flash_categories = (1, 4)
            errors.append(
                "CAPEXGRAPH_JIN10_WS_FLASH_CATEGORIES must use category IDs 1-5."
            )
        return cls(
            mcp_bearer_token=os.getenv("JIN10_MCP_BEARER_TOKEN", "").strip() or None,
            websocket_secret_key=(
                os.getenv("JIN10_WEBSOCKET_SECRET_KEY", "").strip() or None
            ),
            mcp_url=os.getenv("CAPEXGRAPH_JIN10_MCP_URL", "").strip() or JIN10_MCP_URL,
            mcp_timeout_seconds=timeout,
            mcp_call_budget=budget,
            mcp_enabled=_enabled("CAPEXGRAPH_JIN10_MCP_ENABLED", True),
            websocket_enabled=_enabled("CAPEXGRAPH_JIN10_WEBSOCKET_ENABLED", True),
            flash_categories=flash_categories,
            calendar_categories=_csv(
                "CAPEXGRAPH_JIN10_WS_CALENDAR_CATEGORIES",
                ("cj",),
            ),
            quote_categories=_csv(
                "CAPEXGRAPH_JIN10_WS_QUOTE_CATEGORIES",
                (),
            ),
            configuration_errors=tuple(errors),
        )

    def public_status(self) -> dict[str, object]:
        return {
            "provider": "jin10",
            "mcp": {
                "enabled": self.mcp_enabled,
                "configured": bool(self.mcp_bearer_token),
                "url": self.mcp_url,
                "call_budget": self.mcp_call_budget,
                "hard_limit": JIN10_DAILY_HARD_LIMIT,
                "missing": [] if self.mcp_bearer_token else ["JIN10_MCP_BEARER_TOKEN"],
            },
            "websocket": {
                "enabled": self.websocket_enabled,
                "configured": bool(self.websocket_secret_key),
                "streams": {
                    "flash": list(self.flash_categories),
                    "calendar": list(self.calendar_categories),
                    "quote": list(self.quote_categories),
                },
                "missing": (
                    []
                    if self.websocket_secret_key
                    else ["JIN10_WEBSOCKET_SECRET_KEY"]
                ),
            },
            "errors": list(self.configuration_errors),
        }
