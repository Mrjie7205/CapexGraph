from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from capexgraph import connections


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_mcp_connection_verifies_before_persisting_and_never_returns_secret(
    tmp_path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("UNRELATED_SETTING=preserved\n", encoding="utf-8")
    secret = "jin10-secret-that-must-not-leak"
    monkeypatch.setenv("CAPEXGRAPH_ENV_FILE", str(env_path))
    monkeypatch.delenv("JIN10_MCP_BEARER_TOKEN", raising=False)
    reloaded: list[bool] = []

    class FakeMcpClient:
        def __init__(self, settings) -> None:
            assert settings.mcp_bearer_token == secret
            self.tools: tuple[str, ...] = ()
            self.resources: tuple[str, ...] = ()

        def initialize(self) -> None:
            self.tools = ("list_flash", "list_calendar")
            self.resources = ("quote://codes",)

        def close(self) -> None:
            return None

    monkeypatch.setattr(connections, "Jin10McpClient", FakeMcpClient)
    monkeypatch.setattr(
        connections,
        "reload_live_runtime",
        lambda: reloaded.append(True),
    )

    result = connections.connect_jin10_mcp(secret)

    assert result["reachability"] == "ready"
    assert result["tools"] == ["list_flash", "list_calendar"]
    assert secret not in json.dumps(result)
    assert env_path.read_text(encoding="utf-8") == (
        "UNRELATED_SETTING=preserved\n\n"
        f"JIN10_MCP_BEARER_TOKEN={secret}\n"
    )
    assert reloaded == [True]

    disconnected = connections.disconnect_jin10_mcp()
    assert disconnected["configured"] is False
    assert "JIN10_MCP_BEARER_TOKEN" not in env_path.read_text(encoding="utf-8")
    assert "UNRELATED_SETTING=preserved" in env_path.read_text(encoding="utf-8")
    assert reloaded == [True, True]


def test_websocket_connection_is_local_only_and_redacted(
    tmp_path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    secret = "websocket-secret-that-must-not-leak"
    monkeypatch.setenv("CAPEXGRAPH_ENV_FILE", str(env_path))
    monkeypatch.delenv("JIN10_WEBSOCKET_SECRET_KEY", raising=False)
    public_status = {
        "websocket": {
            "streams": {"flash": [1, 4], "calendar": ["cj"], "quote": []}
        }
    }
    monkeypatch.setattr(
        connections,
        "reload_live_runtime",
        lambda: SimpleNamespace(
            provider_settings=SimpleNamespace(
                public_status=lambda: public_status,
            )
        ),
    )

    result = connections.connect_jin10_websocket(secret)

    assert result["reachability"] == "live_probe_pending"
    assert secret not in json.dumps(result)
    assert f"JIN10_WEBSOCKET_SECRET_KEY={secret}" in env_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.anyio
async def test_connection_api_requires_confirmation_and_never_echoes_secret(
    monkeypatch,
) -> None:
    app_module = importlib.import_module("capexgraph.api.app")
    secret = "browser-secret-that-must-not-leak"
    received: list[str] = []

    def fake_connect(value: str) -> dict[str, object]:
        received.append(value)
        return {
            "configured": True,
            "reachability": "live_probe_pending",
            "streams": {"flash": [1, 4]},
            "error": None,
        }

    monkeypatch.setattr(app_module, "connect_jin10_websocket", fake_connect)
    monkeypatch.setattr(
        app_module,
        "connection_status",
        lambda **_kwargs: {
            "local_only": True,
            "storage": "repository_env",
            "jin10_mcp": {"configured": False},
            "jin10_websocket": {"configured": False},
            "codex_subscription": {"authenticated": False},
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=app_module.app),
        base_url="http://test",
    ) as client:
        connected = await client.post(
            "/api/v1/connections/jin10-websocket",
            json={"secret": secret},
        )
        status = await client.get("/api/v1/connections")
        rejected = await client.post(
            "/api/v1/connections/jin10-websocket/disconnect",
            json={"confirmed": False},
        )

    assert connected.status_code == 200
    assert status.status_code == 200
    assert rejected.status_code == 409
    assert received == [secret]
    assert secret not in connected.text
    assert secret not in status.text
