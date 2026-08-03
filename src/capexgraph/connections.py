from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from capexgraph.config import load_project_env
from capexgraph.live import reload_live_runtime
from capexgraph.live.config import LiveProviderSettings
from capexgraph.live.mcp import Jin10McpClient
from capexgraph.providers.codex_cli import (
    codex_connection_status,
    get_codex_app_server,
)

_WRITABLE_SETTINGS = {
    "JIN10_MCP_BEARER_TOKEN",
    "JIN10_WEBSOCKET_SECRET_KEY",
    "CAPEXGRAPH_CODEX_MODEL",
}


def _env_path() -> Path:
    configured = os.getenv("CAPEXGRAPH_ENV_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if loaded := load_project_env():
        return loaded
    return (Path.cwd() / ".env").resolve()


def _validate_value(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Connection value cannot be empty.")
    if any(character in normalized for character in ("\r", "\n", "\0")):
        raise ValueError("Connection value contains unsupported control characters.")
    return normalized


def _write_env_value(name: str, value: str | None) -> Path:
    if name not in _WRITABLE_SETTINGS:
        raise ValueError(f"{name} is not a supported local connection setting.")
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        path.read_text(encoding="utf-8-sig").splitlines()
        if path.is_file()
        else []
    )
    replacement = f"{name}={value}" if value is not None else None
    output: list[str] = []
    replaced = False
    for line in lines:
        candidate = line.strip()
        if candidate.startswith("export "):
            candidate = candidate.removeprefix("export ").strip()
        key, separator, _ = candidate.partition("=")
        if separator and key.strip() == name:
            if replacement is not None and not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if replacement is not None and not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(replacement)
    serialized = "\n".join(output).rstrip() + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(serialized)
        temporary = Path(handle.name)
    os.replace(temporary, path)
    if os.name != "nt":
        path.chmod(0o600)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    return path


def connection_status(*, probe_mcp: bool = False) -> dict[str, object]:
    live = LiveProviderSettings.from_environment()
    mcp: dict[str, object] = {
        "configured": bool(live.mcp_bearer_token),
        "enabled": live.mcp_enabled,
        "reachability": (
            "not_checked" if live.mcp_bearer_token else "not_configured"
        ),
        "tools": [],
        "resources": [],
        "call_budget": live.mcp_call_budget,
        "error": None,
    }
    if probe_mcp and live.mcp_bearer_token:
        client = Jin10McpClient(live)
        try:
            client.initialize()
            mcp.update(
                {
                    "reachability": "ready",
                    "tools": list(client.tools),
                    "resources": list(client.resources),
                }
            )
        except Exception as error:  # safe provider errors contain no token
            mcp.update(
                {
                    "reachability": "unreachable",
                    "error": str(error),
                }
            )
        finally:
            client.close()
    websocket = {
        "configured": bool(live.websocket_secret_key),
        "enabled": live.websocket_enabled,
        "reachability": (
            "live_probe_pending"
            if live.websocket_secret_key
            else "not_configured"
        ),
        "streams": {
            "flash": list(live.flash_categories),
            "calendar": list(live.calendar_categories),
            "quote": list(live.quote_categories),
        },
        "error": None,
    }
    return {
        "local_only": True,
        "storage": "repository_env",
        "jin10_mcp": mcp,
        "jin10_websocket": websocket,
        "codex_subscription": codex_connection_status(include_models=True),
    }


def connect_jin10_mcp(token: str) -> dict[str, object]:
    normalized = _validate_value(token)
    current = LiveProviderSettings.from_environment()
    candidate = replace(current, mcp_bearer_token=normalized)
    client = Jin10McpClient(candidate)
    try:
        client.initialize()
        tools = list(client.tools)
        resources = list(client.resources)
    finally:
        client.close()
    _write_env_value("JIN10_MCP_BEARER_TOKEN", normalized)
    reload_live_runtime()
    return {
        "configured": True,
        "reachability": "ready",
        "tools": tools,
        "resources": resources,
        "call_budget": candidate.mcp_call_budget,
        "error": None,
    }


def disconnect_jin10_mcp() -> dict[str, object]:
    _write_env_value("JIN10_MCP_BEARER_TOKEN", None)
    reload_live_runtime()
    return {
        "configured": False,
        "reachability": "not_configured",
        "tools": [],
        "resources": [],
        "error": None,
    }


def connect_jin10_websocket(secret_key: str) -> dict[str, object]:
    normalized = _validate_value(secret_key)
    _write_env_value("JIN10_WEBSOCKET_SECRET_KEY", normalized)
    runtime = reload_live_runtime()
    return {
        "configured": True,
        "reachability": "live_probe_pending",
        "streams": runtime.provider_settings.public_status()["websocket"]["streams"],
        "error": None,
    }


def disconnect_jin10_websocket() -> dict[str, object]:
    _write_env_value("JIN10_WEBSOCKET_SECRET_KEY", None)
    reload_live_runtime()
    return {
        "configured": False,
        "reachability": "not_configured",
        "streams": {},
        "error": None,
    }


def start_codex_login() -> dict[str, object]:
    return get_codex_app_server().start_chatgpt_login()


def codex_login_state() -> dict[str, object]:
    client = get_codex_app_server()
    return {
        **client.login_state(),
        "connection": codex_connection_status(include_models=True),
    }


def select_codex_model(model: str) -> dict[str, Any]:
    normalized = _validate_value(model)
    status = codex_connection_status(include_models=True)
    models = status.get("models")
    available = {
        str(item["id"])
        for item in models
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(models, list) else set()
    if available and normalized not in available:
        raise ValueError("Selected Codex model is not available to this account.")
    _write_env_value("CAPEXGRAPH_CODEX_MODEL", normalized)
    return {
        **status,
        "selected_model": normalized,
    }
