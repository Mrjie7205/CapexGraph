from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from capexgraph.domain import LiveProviderHealth, SignalObservation
from capexgraph.live.mcp import (
    AdaptivePollPolicy,
    Jin10McpClient,
    Jin10McpSource,
)
from capexgraph.live.service import LiveIngestionResult, LiveSignalService
from capexgraph.live.store import LiveSignalStore
from capexgraph.live.websocket import (
    Jin10WebSocketCodec,
    Jin10WebSocketSource,
    Jin10WebSocketWorker,
)


class LiveGatewayRuntime:
    """Single-process supervisor; MCP and WebSocket keep independent loops."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.store = LiveSignalStore(db_path)
        self.service = LiveSignalService(self.store)
        from capexgraph.live.config import LiveProviderSettings

        self.provider_settings = LiveProviderSettings.from_environment()
        self.mcp_client = Jin10McpClient(self.provider_settings)
        self.mcp_sources = {
            stream: Jin10McpSource(
                stream,
                client=self.mcp_client,
                settings=self.provider_settings,
            )
            for stream in ("flash", "calendar")
        }
        self.websocket_sources = {
            stream: Jin10WebSocketSource(
                stream,
                settings=self.provider_settings,
            )
            for stream in ("flash", "calendar", "quote")
        }
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_stop: asyncio.Event | None = None
        self._lock = threading.RLock()
        self._started_at: datetime | None = None
        self._stop_requested = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def poll_once(self, stream: str = "flash") -> LiveIngestionResult:
        if stream not in self.mcp_sources:
            raise ValueError("MCP stream must be flash or calendar")
        return self.service.poll_source(self.mcp_sources[stream])

    def _ingest_websocket(self, stream: str, observation: SignalObservation) -> None:
        source = self.websocket_sources[stream]
        source.push(observation)
        self.service.poll_source(source)

    def _set_websocket_health(
        self,
        stream: str,
        health: LiveProviderHealth,
        error: str,
    ) -> None:
        source = self.websocket_sources[stream]
        source.set_health(health, error)
        self.service.poll_source(source)

    async def _mcp_loop(self, stream: str) -> None:
        settings = self.store.get_settings()
        policy = AdaptivePollPolicy(
            urgent=settings.urgent_poll_seconds,
            normal=settings.normal_poll_seconds,
            quiet=settings.quiet_poll_seconds,
        )
        while self._async_stop is not None and not self._async_stop.is_set():
            urgent = False
            try:
                result = await asyncio.to_thread(self.poll_once, stream)
                urgent = any(
                    int(item.metadata.get("important") or 0) > 0
                    for item in result.batch.observations
                )
                checkpoint = result.batch.checkpoint
            except Exception:  # noqa: BLE001 - service persists the safe channel state
                checkpoint = self.store.get_checkpoint(
                    "jin10", self.mcp_sources[stream].descriptor.channel, stream
                )
            calls_used = checkpoint.calls_used if checkpoint else 0
            call_budget = (
                checkpoint.call_budget
                if checkpoint and checkpoint.call_budget
                else self.provider_settings.mcp_call_budget
            )
            active_hours = 0 <= datetime.now(UTC).hour < 24
            interval = policy.next_interval(
                calls_used=calls_used,
                call_budget=call_budget,
                urgent=urgent,
                active_hours=active_hours,
            )
            try:
                await asyncio.wait_for(self._async_stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()
        if self._stop_requested.is_set():
            self._async_stop.set()
        desk = self.store.get_settings()
        tasks: list[asyncio.Task[Any]] = []
        if desk.mcp_enabled and self.provider_settings.mcp_enabled:
            if desk.flash_enabled:
                tasks.append(asyncio.create_task(self._mcp_loop("flash")))
            if desk.calendar_enabled:
                tasks.append(asyncio.create_task(self._mcp_loop("calendar")))
        enabled_ws_streams = [
            stream
            for stream, enabled in (
                ("flash", desk.flash_enabled),
                ("calendar", desk.calendar_enabled),
                ("quote", desk.quote_enabled),
            )
            if enabled
        ]
        if desk.websocket_enabled and self.provider_settings.websocket_enabled:
            for stream in enabled_ws_streams:
                if stream == "quote" and not self.provider_settings.quote_categories:
                    self._set_websocket_health(
                        stream,
                        LiveProviderHealth.NOT_CONFIGURED,
                        "No WebSocket quote categories are configured.",
                    )
                    continue
                codec = Jin10WebSocketCodec(
                    stream,
                    settings=self.provider_settings,
                )
                worker = Jin10WebSocketWorker(
                    codec,
                    lambda observation, stream=stream: self._ingest_websocket(
                        stream, observation
                    ),
                    lambda health, error, stream=stream: self._set_websocket_health(
                        stream, health, error
                    ),
                )
                tasks.append(
                    asyncio.create_task(worker.run_forever(self._async_stop))
                )
        if not tasks:
            await self._async_stop.wait()
            return
        try:
            await self._async_stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        finally:
            self._loop = None
            self._async_stop = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.running:
                return self.status()
            self._stop_requested.clear()
            self._started_at = datetime.now(UTC)
            self._thread = threading.Thread(
                target=self._thread_main,
                name="capexgraph-live-gateway",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def stop(self, *, timeout: float = 5.0) -> dict[str, Any]:
        with self._lock:
            self._stop_requested.set()
            if self._loop is not None and self._async_stop is not None:
                self._loop.call_soon_threadsafe(self._async_stop.set)
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "started_at": self._started_at,
            "database": str(self.store.db_path),
            "configuration": self.provider_settings.public_status(),
            "settings": self.store.get_settings().model_dump(mode="json"),
            "checkpoints": [
                item.model_dump(mode="json") for item in self.store.list_checkpoints()
            ],
        }


_RUNTIMES: dict[Path, LiveGatewayRuntime] = {}
_RUNTIMES_LOCK = threading.Lock()


def get_live_runtime(db_path: Path | None = None) -> LiveGatewayRuntime:
    candidate = LiveSignalStore(db_path).db_path
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.get(candidate)
        if runtime is None:
            runtime = LiveGatewayRuntime(candidate)
            _RUNTIMES[candidate] = runtime
        return runtime
