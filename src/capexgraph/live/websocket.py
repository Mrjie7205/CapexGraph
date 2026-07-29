from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import random
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import websockets

from capexgraph.domain import (
    LiveChannel,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveRetentionClass,
    LiveSignalCategory,
    SignalObservation,
)
from capexgraph.live.base import Clock, LiveEventBatch, LiveSourceDescriptor, SystemClock
from capexgraph.live.config import JIN10_WS_ENDPOINTS, LiveProviderSettings
from capexgraph.live.mcp import (
    LiveProviderAuthenticationError,
    LiveProviderProtocolError,
    _as_int,
    _parse_jin10_time,
)
from capexgraph.live.text import plain_text

JIN10_WEBSOCKET_VERSION = "open-platform-websocket-v1"
ObservationCallback = Callable[[SignalObservation], Awaitable[None] | None]
HealthCallback = Callable[[LiveProviderHealth, str], Awaitable[None] | None]


class Jin10WebSocketCodec:
    """Official Jin10 auth/subscription envelopes and normalized event decoder."""

    def __init__(
        self,
        stream: str,
        *,
        settings: LiveProviderSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        if stream not in JIN10_WS_ENDPOINTS:
            raise ValueError("Jin10 WebSocket stream must be flash, calendar, or quote")
        self.stream = stream
        self.settings = settings or LiveProviderSettings.from_environment()
        self.clock = clock or SystemClock()

    @property
    def endpoint(self) -> str:
        return JIN10_WS_ENDPOINTS[self.stream]

    def auth_message(self) -> dict[str, Any]:
        return {
            "action": "auth",
            "params": {"secret-key": self.settings.websocket_secret_key or ""},
        }

    def subscribe_message(self) -> dict[str, Any]:
        if self.stream == "flash":
            categories: Sequence[int | str] = self.settings.flash_categories
        elif self.stream == "calendar":
            categories = self.settings.calendar_categories
        else:
            categories = self.settings.quote_categories
        return {"action": "subscribe", "params": {"category": list(categories)}}

    @staticmethod
    def parse_message(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise LiveProviderProtocolError(
                "Jin10 WebSocket returned invalid JSON."
            ) from error
        if not isinstance(value, dict):
            raise LiveProviderProtocolError(
                "Jin10 WebSocket returned a non-object message."
            )
        return value

    def validate_ack(self, raw: str | bytes | dict[str, Any], expected: str) -> None:
        payload = self.parse_message(raw)
        if payload.get("type") != expected:
            raise LiveProviderProtocolError(
                f"Jin10 WebSocket expected {expected}, received {payload.get('type')!r}."
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise LiveProviderProtocolError("Jin10 WebSocket acknowledgement is invalid.")
        code_field = {
            "connected_result": "connected_result",
            "auth_result": "auth_result",
            "subscribe_result": "subscribe_result",
        }[expected]
        if int(data.get(code_field) or 0) != 200:
            if expected == "auth_result":
                raise LiveProviderAuthenticationError(
                    "Jin10 WebSocket authentication failed."
                )
            raise LiveProviderProtocolError(
                f"Jin10 WebSocket {expected} was rejected."
            )

    def decode(self, raw: str | bytes | dict[str, Any]) -> SignalObservation | None:
        envelope = self.parse_message(raw)
        if envelope.get("type") != "data":
            return None
        payload = envelope.get("data")
        if not isinstance(payload, dict):
            raise LiveProviderProtocolError("Jin10 WebSocket data payload is invalid.")
        observed_at = self.clock.now().astimezone(UTC)
        if self.stream == "flash":
            return self._flash(payload, observed_at)
        if self.stream == "calendar":
            return self._calendar(payload, observed_at)
        return self._quote(payload, observed_at)

    def _flash(
        self, payload: dict[str, Any], observed_at: datetime
    ) -> SignalObservation | None:
        nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        content = plain_text(nested.get("content"))
        title = plain_text(nested.get("title") or content, limit=300)
        if not title:
            return None
        external_id = str(payload.get("id") or "").strip()
        if not external_id:
            external_id = hashlib.sha256(
                f"{payload.get('time')}:{title}".encode()
            ).hexdigest()[:24]
        published_at = _parse_jin10_time(payload.get("time")) or observed_at
        return SignalObservation(
            provider="jin10",
            provider_version=JIN10_WEBSOCKET_VERSION,
            channel=LiveChannel.WEBSOCKET,
            stream="flash",
            external_id=external_id,
            event_key=f"jin10:{external_id}",
            category=LiveSignalCategory.FLASH,
            title=title,
            content=content,
            published_at=min(published_at, observed_at),
            observed_at=observed_at,
            retention_class=LiveRetentionClass.METADATA_ONLY,
            metadata={
                "important": _as_int(payload.get("important")),
                "type": payload.get("type"),
                "action": payload.get("action"),
                "categories": payload.get("category") or [],
                "tags": payload.get("tags") or [],
                "classify": payload.get("classify") or [],
                "provider_picture_omitted": bool(nested.get("pic")),
            },
        )

    def _calendar(
        self, payload: dict[str, Any], observed_at: datetime
    ) -> SignalObservation | None:
        item = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        title = plain_text(item.get("title") or item.get("name"), limit=300)
        if not title:
            return None
        external_id = str(item.get("id") or "").strip()
        if not external_id:
            external_id = hashlib.sha256(
                f"{item.get('pub_time')}:{title}".encode()
            ).hexdigest()[:24]
        calendar_key = hashlib.sha256(
            f"{item.get('pub_time')}:{title}".encode()
        ).hexdigest()[:24]
        return SignalObservation(
            provider="jin10",
            provider_version=JIN10_WEBSOCKET_VERSION,
            channel=LiveChannel.WEBSOCKET,
            stream="calendar",
            external_id=external_id,
            event_key=f"jin10:calendar:{calendar_key}",
            category=LiveSignalCategory.CALENDAR,
            title=title,
            published_at=observed_at,
            scheduled_at=_parse_jin10_time(item.get("pub_time")),
            observed_at=observed_at,
            retention_class=LiveRetentionClass.METADATA_ONLY,
            metadata={
                "action": payload.get("action"),
                "data_type": payload.get("data_type"),
                "indicator_id": item.get("indicator_id"),
                "country": item.get("country"),
                "star": item.get("star"),
                "unit": item.get("unit"),
                "previous": item.get("previous"),
                "consensus": item.get("consensus"),
                "actual": item.get("actual"),
                "revised": item.get("revised"),
                "affect": item.get("affect"),
                "affect_status": item.get("affect_status"),
                "categories": item.get("category") or [],
            },
        )

    def _quote(
        self, payload: dict[str, Any], observed_at: datetime
    ) -> SignalObservation | None:
        code = str(payload.get("c") or "").strip()
        if not code:
            return None
        timestamp = payload.get("t")
        try:
            published_at = datetime.fromtimestamp(float(timestamp), tz=UTC)
        except (TypeError, ValueError, OSError):
            published_at = observed_at
        external_id = f"{code}:{int(published_at.timestamp())}"
        price = payload.get("p")
        return SignalObservation(
            provider="jin10",
            provider_version=JIN10_WEBSOCKET_VERSION,
            channel=LiveChannel.WEBSOCKET,
            stream="quote",
            external_id=external_id,
            event_key=f"jin10:quote:{external_id}",
            category=LiveSignalCategory.QUOTE,
            title=f"{code} quote update {price}",
            published_at=min(published_at, observed_at),
            observed_at=observed_at,
            retention_class=LiveRetentionClass.EPHEMERAL,
            metadata={
                "code": code,
                "exchange": payload.get("e"),
                "instrument_type": payload.get("type"),
                "ask": payload.get("a"),
                "bid": payload.get("b"),
                "price": price,
                "open": payload.get("o"),
                "high": payload.get("h"),
                "low": payload.get("l"),
            },
        )


class Jin10WebSocketSource:
    """Thread-safe queue exposed through the common LiveEventSource contract."""

    def __init__(
        self,
        stream: str,
        *,
        settings: LiveProviderSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings or LiveProviderSettings.from_environment()
        self.codec = Jin10WebSocketCodec(stream, settings=self.settings, clock=clock)
        self.clock = clock or SystemClock()
        self._queue: deque[SignalObservation] = deque()
        self._health = LiveProviderHealth.NOT_CONFIGURED
        self._error = ""
        self._received = 0
        self._descriptor = LiveSourceDescriptor(
            provider="jin10",
            provider_version=JIN10_WEBSOCKET_VERSION,
            channel=LiveChannel.WEBSOCKET,
            stream=stream,
            transport="websocket",
            requires_credentials=True,
        )

    @property
    def descriptor(self) -> LiveSourceDescriptor:
        return self._descriptor

    def push(self, observation: SignalObservation) -> None:
        self._queue.append(observation)
        self._received += 1
        self._health = LiveProviderHealth.ACTIVE
        self._error = ""

    def set_health(self, health: LiveProviderHealth, error: str = "") -> None:
        self._health = health
        self._error = error

    def read(
        self,
        checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch:
        if not self.settings.websocket_enabled:
            health = LiveProviderHealth.OFF
            error = ""
        elif not self.settings.websocket_secret_key:
            health = LiveProviderHealth.NOT_CONFIGURED
            error = "JIN10_WEBSOCKET_SECRET_KEY is not configured."
        else:
            health = self._health
            error = self._error
        observations: list[SignalObservation] = []
        while self._queue and len(observations) < limit:
            observations.append(self._queue.popleft())
        last = observations[-1] if observations else None
        cursor_value = (
            int(checkpoint.cursor)
            if checkpoint and checkpoint.cursor.isdigit()
            else 0
        )
        next_checkpoint = LiveProviderCheckpoint(
            provider="jin10",
            provider_version=JIN10_WEBSOCKET_VERSION,
            channel=LiveChannel.WEBSOCKET,
            stream=self.descriptor.stream,
            cursor=str(cursor_value + len(observations)),
            last_external_id=(
                last.external_id
                if last
                else checkpoint.last_external_id if checkpoint else None
            ),
            last_published_at=(
                last.published_at
                if last
                else checkpoint.last_published_at if checkpoint else None
            ),
            last_observed_at=(
                last.observed_at
                if last
                else checkpoint.last_observed_at if checkpoint else None
            ),
            health=health,
            updated_at=self.clock.now(),
            error=error,
            metadata={
                "messages_received": self._received,
                "queued": len(self._queue),
                "endpoint": self.codec.endpoint,
            },
        )
        return LiveEventBatch(
            descriptor=self.descriptor,
            observations=observations,
            checkpoint=next_checkpoint,
            has_more=bool(self._queue),
        )


async def _invoke(
    callback: ObservationCallback | HealthCallback,
    *args: Any,
) -> None:
    result = callback(*args)
    if inspect.isawaitable(result):
        await result


class Jin10WebSocketWorker:
    """Authenticated stream worker with heartbeat and jittered exponential reconnect."""

    def __init__(
        self,
        codec: Jin10WebSocketCodec,
        on_observation: ObservationCallback,
        on_health: HealthCallback,
        *,
        connect: Callable[..., Any] | None = None,
        random_source: random.Random | None = None,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 60.0,
    ) -> None:
        self.codec = codec
        self.on_observation = on_observation
        self.on_health = on_health
        self.connect = connect or websockets.connect
        self.random = random_source or random.Random()
        self.backoff_base_seconds = max(0.001, backoff_base_seconds)
        self.backoff_max_seconds = max(
            self.backoff_base_seconds,
            backoff_max_seconds,
        )

    async def run_once(self) -> None:
        if not self.codec.settings.websocket_secret_key:
            await _invoke(
                self.on_health,
                LiveProviderHealth.NOT_CONFIGURED,
                "JIN10_WEBSOCKET_SECRET_KEY is not configured.",
            )
            return
        async with self.connect(
            self.codec.endpoint,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
            close_timeout=5,
            max_size=2**20,
        ) as connection:
            self.codec.validate_ack(await connection.recv(), "connected_result")
            await connection.send(
                json.dumps(self.codec.auth_message(), ensure_ascii=False)
            )
            self.codec.validate_ack(await connection.recv(), "auth_result")
            await connection.send(
                json.dumps(self.codec.subscribe_message(), ensure_ascii=False)
            )
            self.codec.validate_ack(await connection.recv(), "subscribe_result")
            await _invoke(self.on_health, LiveProviderHealth.ACTIVE, "")
            async for raw in connection:
                try:
                    observation = self.codec.decode(raw)
                except (TypeError, ValueError, LiveProviderProtocolError) as error:
                    await _invoke(
                        self.on_health,
                        LiveProviderHealth.DEGRADED,
                        f"{type(error).__name__}: invalid WebSocket message.",
                    )
                    continue
                if observation is not None:
                    await _invoke(self.on_observation, observation)

    async def run_forever(self, stop: asyncio.Event) -> None:
        failures = 0
        while not stop.is_set():
            try:
                await self.run_once()
                failures = 0
                if not self.codec.settings.websocket_secret_key:
                    return
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - channel health owns retry state
                failures += 1
                await _invoke(
                    self.on_health,
                    LiveProviderHealth.DEGRADED,
                    f"{type(error).__name__}: WebSocket stream disconnected.",
                )
            delay = min(
                self.backoff_max_seconds,
                self.backoff_base_seconds * 2 ** min(failures, 5),
            )
            delay += self.random.uniform(0, min(3.0, delay * 0.25))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                continue
