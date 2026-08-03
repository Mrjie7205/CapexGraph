from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx

from capexgraph.domain import (
    LiveChannel,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveRetentionClass,
    LiveSignalCategory,
    SignalObservation,
)
from capexgraph.live.base import Clock, LiveEventBatch, LiveSourceDescriptor, SystemClock
from capexgraph.live.config import LiveProviderSettings
from capexgraph.live.text import plain_text

MCP_PROTOCOL_VERSION = "2025-11-25"
JIN10_PROVIDER_VERSION = f"mcp-{MCP_PROTOCOL_VERSION}"
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
_URL_ID = re.compile(r"(?:/|=)(\d{5,})(?:[/?#&]|$)")


class LiveProviderError(RuntimeError):
    """Credential-safe live provider failure."""


class LiveProviderConfigurationError(LiveProviderError):
    pass


class LiveProviderProtocolError(LiveProviderError):
    pass


class LiveProviderAuthenticationError(LiveProviderError):
    pass


class Jin10McpClient:
    """Small strict Streamable HTTP MCP client that prefers structuredContent."""

    def __init__(
        self,
        settings: LiveProviderSettings | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or LiveProviderSettings.from_environment()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self.settings.mcp_timeout_seconds,
            trust_env=False,
        )
        self._session_id: str | None = None
        self._request_id = 0
        self._initialized = False
        self._initialize_lock = threading.Lock()
        self._post_lock = threading.Lock()
        self.tools: tuple[str, ...] = ()
        self.resources: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.settings.mcp_enabled and self.settings.mcp_bearer_token)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        if not self.settings.mcp_bearer_token:
            raise LiveProviderConfigurationError(
                "Jin10 MCP is not configured; set JIN10_MCP_BEARER_TOKEN."
            )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.settings.mcp_bearer_token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    @staticmethod
    def _response_payload(response: httpx.Response) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            raise LiveProviderAuthenticationError("Jin10 MCP authentication failed.")
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LiveProviderError(
                f"Jin10 MCP returned HTTP {response.status_code}."
            ) from error
        if response.status_code == 202 or not response.content:
            return {}
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            events: list[dict[str, Any]] = []
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                try:
                    value = json.loads(line.removeprefix("data:").strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
            if not events:
                raise LiveProviderProtocolError(
                    "Jin10 MCP returned an empty event stream."
                )
            return events[-1]
        try:
            payload = response.json()
        except ValueError as error:
            raise LiveProviderProtocolError(
                "Jin10 MCP returned invalid JSON."
            ) from error
        if not isinstance(payload, dict):
            raise LiveProviderProtocolError("Jin10 MCP returned a non-object response.")
        return payload

    def _post(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notification: bool = False,
    ) -> dict[str, Any]:
        with self._post_lock:
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if not notification:
                self._request_id += 1
                payload["id"] = self._request_id
            if params is not None:
                payload["params"] = params
            try:
                response = self._client.post(
                    self.settings.mcp_url,
                    headers=self._headers(),
                    json=payload,
                )
            except httpx.HTTPError as error:
                raise LiveProviderError("Jin10 MCP endpoint is unreachable.") from error
            if session_id := response.headers.get("mcp-session-id"):
                self._session_id = session_id
            body = self._response_payload(response)
            if "error" in body:
                error = body["error"]
                code = error.get("code") if isinstance(error, dict) else None
                raise LiveProviderProtocolError(
                    f"Jin10 MCP protocol error{f' {code}' if code is not None else ''}."
                )
            return body

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            response = self._post(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "capexgraph", "version": "0.5.1"},
                },
            )
            negotiated = response.get("result", {}).get("protocolVersion")
            if negotiated != MCP_PROTOCOL_VERSION:
                raise LiveProviderProtocolError(
                    f"Jin10 MCP negotiated unsupported protocol {negotiated!r}."
                )
            self._post("notifications/initialized", {}, notification=True)
            tools = self._post("tools/list", {}).get("result", {}).get("tools", [])
            resources = self._post("resources/list", {}).get("result", {}).get(
                "resources", []
            )
            self.tools = tuple(
                str(item.get("name"))
                for item in tools
                if isinstance(item, dict) and item.get("name")
            )
            self.resources = tuple(
                str(item.get("uri"))
                for item in resources
                if isinstance(item, dict) and item.get("uri")
            )
            self._initialized = True

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        if name not in self.tools:
            raise LiveProviderProtocolError(f"Jin10 MCP tool is unavailable: {name}.")
        payload = self._post(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise LiveProviderProtocolError("Jin10 MCP tool result is missing.")
        if result.get("isError") is True:
            raise LiveProviderError(f"Jin10 MCP {name} returned a business error.")
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            raise LiveProviderProtocolError(
                f"Jin10 MCP {name} did not return structuredContent."
            )
        return structured

    def read_resource(self, uri: str) -> dict[str, Any]:
        self.initialize()
        if uri not in self.resources:
            raise LiveProviderProtocolError(f"Jin10 MCP resource is unavailable: {uri}.")
        result = self._post("resources/read", {"uri": uri}).get("result")
        if not isinstance(result, dict):
            raise LiveProviderProtocolError("Jin10 MCP resource result is missing.")
        return result


class AdaptivePollPolicy:
    """Deterministic 30/120/300 cadence with quota-pressure protection."""

    def __init__(self, *, urgent: int = 30, normal: int = 120, quiet: int = 300):
        self.urgent = urgent
        self.normal = normal
        self.quiet = quiet

    def next_interval(
        self,
        *,
        calls_used: int,
        call_budget: int,
        urgent: bool = False,
        active_hours: bool = True,
    ) -> int:
        remaining_ratio = max(0.0, (call_budget - calls_used) / call_budget)
        if remaining_ratio <= 0.15 or not active_hours:
            return self.quiet
        if urgent and remaining_ratio > 0.35:
            return self.urgent
        return self.normal


def _parse_jin10_time(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(UTC)


def _external_id(item: dict[str, Any], *, fallback: str) -> str:
    if item.get("id") not in (None, ""):
        return str(item["id"])
    url = str(item.get("url") or "")
    if match := _URL_ID.search(url):
        return match.group(1)
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]


def _http_url(value: object) -> str | None:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else None


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class Jin10McpSource:
    """Head-polling source for Jin10 flash or calendar data."""

    def __init__(
        self,
        stream: str,
        *,
        client: Jin10McpClient | None = None,
        settings: LiveProviderSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        if stream not in {"flash", "calendar"}:
            raise ValueError("Jin10 MCP stream must be flash or calendar")
        self.stream = stream
        self.settings = settings or LiveProviderSettings.from_environment()
        self.client = client or Jin10McpClient(self.settings)
        self.clock = clock or SystemClock()
        self._descriptor = LiveSourceDescriptor(
            provider="jin10",
            provider_version=JIN10_PROVIDER_VERSION,
            channel=LiveChannel.MCP,
            stream=stream,
            transport="mcp-streamable-http",
            requires_credentials=True,
        )

    @property
    def descriptor(self) -> LiveSourceDescriptor:
        return self._descriptor

    def _checkpoint_counts(
        self, checkpoint: LiveProviderCheckpoint | None, today: date
    ) -> int:
        return checkpoint.calls_used if checkpoint and checkpoint.budget_date == today else 0

    def read(
        self,
        checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch:
        observed_at = self.clock.now().astimezone(UTC)
        budget_date = observed_at.astimezone(SHANGHAI).date()
        calls_used = self._checkpoint_counts(checkpoint, budget_date)
        base = {
            "provider": "jin10",
            "provider_version": JIN10_PROVIDER_VERSION,
            "channel": LiveChannel.MCP,
            "stream": self.stream,
            "cursor": checkpoint.cursor if checkpoint else "",
            "last_external_id": checkpoint.last_external_id if checkpoint else None,
            "last_published_at": checkpoint.last_published_at if checkpoint else None,
            "last_observed_at": checkpoint.last_observed_at if checkpoint else None,
            "calls_used": calls_used,
            "call_budget": self.settings.mcp_call_budget,
            "budget_date": budget_date,
        }

        def failed_batch(message: str, tool: str) -> LiveEventBatch:
            failed_checkpoint = LiveProviderCheckpoint.model_validate(
                {
                    **base,
                    "last_observed_at": observed_at,
                    "health": LiveProviderHealth.DEGRADED,
                    "calls_used": calls_used + 1,
                    "error": message,
                    "metadata": {
                        "tool": tool,
                        "attempt_counted": True,
                    },
                }
            )
            return LiveEventBatch(
                descriptor=self.descriptor,
                checkpoint=failed_checkpoint,
            )
        if not self.settings.mcp_enabled:
            next_checkpoint = LiveProviderCheckpoint(
                **base,
                health=LiveProviderHealth.OFF,
                error="",
                metadata={"reason": "disabled"},
            )
            return LiveEventBatch(
                descriptor=self.descriptor, checkpoint=next_checkpoint
            )
        if not self.client.configured:
            next_checkpoint = LiveProviderCheckpoint(
                **base,
                health=LiveProviderHealth.NOT_CONFIGURED,
                error="JIN10_MCP_BEARER_TOKEN is not configured.",
            )
            return LiveEventBatch(
                descriptor=self.descriptor, checkpoint=next_checkpoint
            )
        if calls_used >= self.settings.mcp_call_budget:
            next_checkpoint = LiveProviderCheckpoint(
                **base,
                health=LiveProviderHealth.EXHAUSTED,
                error="Local Jin10 MCP daily call budget is exhausted.",
            )
            return LiveEventBatch(
                descriptor=self.descriptor, checkpoint=next_checkpoint
            )
        tool = "list_flash" if self.stream == "flash" else "list_calendar"
        try:
            structured = self.client.call_tool(tool, {})
        except LiveProviderError as error:
            return failed_batch(str(error), tool)
        data = structured.get("data")
        observations: list[SignalObservation] = []
        rejected_items = 0
        if self.stream == "flash":
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                return failed_batch(
                    "Jin10 list_flash structuredContent has an invalid data.items.",
                    tool,
                )
            items = data["items"][:limit]
            next_cursor = str(data.get("next_cursor") or "")
            has_more = bool(data.get("has_more"))
            normalizer = self._flash_observation
        else:
            if not isinstance(data, list):
                return failed_batch(
                    "Jin10 list_calendar structuredContent has invalid data.",
                    tool,
                )
            items = data[:limit]
            next_cursor = ""
            has_more = False
            normalizer = self._calendar_observation
        for item in items:
            if not isinstance(item, dict):
                rejected_items += 1
                continue
            try:
                observation = normalizer(item, observed_at)
            except (TypeError, ValueError):
                rejected_items += 1
                continue
            if observation is None:
                rejected_items += 1
            else:
                observations.append(observation)
        newest = max(
            observations,
            key=lambda item: (item.published_at, item.external_id),
            default=None,
        )
        next_checkpoint = LiveProviderCheckpoint.model_validate(
            {
                **base,
                "cursor": next_cursor,
                "last_external_id": (
                    newest.external_id if newest else base["last_external_id"]
                ),
                "last_published_at": (
                    newest.published_at if newest else base["last_published_at"]
                ),
                "last_observed_at": observed_at,
                "health": LiveProviderHealth.ACTIVE,
                "calls_used": calls_used + 1,
                "error": "",
                "metadata": {
                    "pagination_mode": "head_refresh",
                    "historical_next_cursor": next_cursor,
                    "has_more": has_more,
                    "returned": len(observations),
                    "rejected_items": rejected_items,
                },
            }
        )
        return LiveEventBatch(
            descriptor=self.descriptor,
            observations=observations,
            checkpoint=next_checkpoint,
            has_more=has_more,
        )

    def _flash_observation(
        self, item: dict[str, Any], observed_at: datetime
    ) -> SignalObservation | None:
        nested = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = plain_text(nested.get("content") or item.get("content"))
        title = plain_text(
            nested.get("title") or item.get("title") or content,
            limit=300,
        )
        published_at = _parse_jin10_time(item.get("time")) or observed_at
        external_id = _external_id(
            item,
            fallback=f"{item.get('time')}:{title}:{item.get('url')}",
        )
        if not title:
            return None
        source_url = _http_url(item.get("url"))
        return SignalObservation(
            provider="jin10",
            provider_version=JIN10_PROVIDER_VERSION,
            channel=LiveChannel.MCP,
            stream="flash",
            external_id=external_id,
            event_key=f"jin10:{external_id}",
            category=LiveSignalCategory.FLASH,
            title=title,
            content=content,
            source_url=source_url,
            published_at=min(published_at, observed_at),
            observed_at=observed_at,
            retention_class=LiveRetentionClass.METADATA_ONLY,
            metadata={
                "important": _as_int(item.get("important")),
                "type": item.get("type"),
                "action": item.get("action"),
                "categories": item.get("category") or [],
                "tags": item.get("tags") or [],
                "provider_picture_omitted": bool(nested.get("pic")),
            },
        )

    def _calendar_observation(
        self, item: dict[str, Any], observed_at: datetime
    ) -> SignalObservation | None:
        title = plain_text(item.get("title"), limit=300)
        scheduled_at = _parse_jin10_time(item.get("pub_time"))
        if not title:
            return None
        fallback = (
            f"{item.get('pub_time')}:{title}:{item.get('previous')}:"
            f"{item.get('consensus')}:{item.get('actual')}"
        )
        external_id = _external_id(item, fallback=fallback)
        calendar_key = hashlib.sha256(
            f"{item.get('pub_time')}:{title}".encode()
        ).hexdigest()[:24]
        return SignalObservation(
            provider="jin10",
            provider_version=JIN10_PROVIDER_VERSION,
            channel=LiveChannel.MCP,
            stream="calendar",
            external_id=external_id,
            event_key=f"jin10:calendar:{calendar_key}",
            category=LiveSignalCategory.CALENDAR,
            title=title,
            published_at=observed_at,
            scheduled_at=scheduled_at,
            observed_at=observed_at,
            retention_class=LiveRetentionClass.METADATA_ONLY,
            metadata={
                "star": item.get("star"),
                "previous": item.get("previous"),
                "consensus": item.get("consensus"),
                "actual": item.get("actual"),
                "revised": item.get("revised"),
                "affect": item.get("affect_txt"),
            },
        )
