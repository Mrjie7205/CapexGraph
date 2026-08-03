from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from capexgraph.domain import (
    LiveChannel,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveSoakReport,
)
from capexgraph.live.base import LiveEventBatch, LiveEventSource, LiveSourceDescriptor
from capexgraph.live.config import LiveProviderSettings
from capexgraph.live.fixture import FrozenClock, FrozenEventFeed, load_frozen_dual_channel_feeds
from capexgraph.live.runtime import LiveGatewayRuntime
from capexgraph.live.service import LiveSignalService
from capexgraph.live.store import LiveSignalStore


class _ReplaySource:
    """Replay a frozen source from its head to exercise ingestion idempotency."""

    def __init__(self, source: FrozenEventFeed) -> None:
        self.source = source

    @property
    def descriptor(self) -> LiveSourceDescriptor:
        return self.source.descriptor

    def read(
        self,
        _checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch:
        return self.source.read(None, limit=limit)


class _FailingSource:
    def __init__(self, descriptor: LiveSourceDescriptor) -> None:
        self._descriptor = descriptor

    @property
    def descriptor(self) -> LiveSourceDescriptor:
        return self._descriptor

    def read(
        self,
        _checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch:
        del limit
        raise RuntimeError("synthetic channel failure")


def _checkpoint_fingerprint(checkpoint: LiveProviderCheckpoint | None) -> str:
    return checkpoint.model_dump_json() if checkpoint is not None else ""


class LiveSoakRunner:
    """Bounded release-gate exercises for fixture and credentialed provider paths."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.store = LiveSignalStore(db_path)

    def run_fixture(
        self,
        *,
        cycles: int = 6,
        failure_every: int = 3,
    ) -> LiveSoakReport:
        if not 1 <= cycles <= 10_000:
            raise ValueError("fixture soak cycles must be between 1 and 10000")
        if not 0 <= failure_every <= cycles:
            raise ValueError("failure_every must be zero or no greater than cycles")

        started_at = datetime.now(UTC)
        clock = FrozenClock(datetime(2026, 7, 29, 2, 6, tzinfo=UTC))
        observations = 0
        created_versions = 0
        duplicates = 0
        injected_failures = 0
        observed_failures = 0
        checkpoint_isolation_ok = True
        failed_channels: list[LiveChannel] = []
        fixture_feeds = load_frozen_dual_channel_feeds(clock=clock)
        fixture_provider = fixture_feeds[0].descriptor.provider
        fixture_stream = fixture_feeds[0].descriptor.stream

        with TemporaryDirectory(prefix="capexgraph-live-soak-") as directory:
            exercise_store = LiveSignalStore(Path(directory) / "fixture-soak.db")
            service = LiveSignalService(exercise_store)
            for cycle in range(1, cycles + 1):
                sources: list[LiveEventSource] = [
                    _ReplaySource(source)
                    for source in load_frozen_dual_channel_feeds(clock=clock)
                ]
                failure_channel: LiveChannel | None = None
                if failure_every and cycle % failure_every == 0 and cycle < cycles:
                    failure_index = injected_failures % len(sources)
                    failure_channel = sources[failure_index].descriptor.channel
                    sources[failure_index] = _FailingSource(
                        sources[failure_index].descriptor
                    )
                    injected_failures += 1
                    failed_channels.append(failure_channel)

                for source in sources:
                    other_channel = (
                        LiveChannel.WEBSOCKET
                        if source.descriptor.channel == LiveChannel.MCP
                        else LiveChannel.MCP
                    )
                    other_before = _checkpoint_fingerprint(
                        exercise_store.get_checkpoint(
                            source.descriptor.provider,
                            other_channel,
                            source.descriptor.stream,
                        )
                    )
                    try:
                        result = service.poll_source(source)
                    except RuntimeError:
                        observed_failures += 1
                        other_after = _checkpoint_fingerprint(
                            exercise_store.get_checkpoint(
                                source.descriptor.provider,
                                other_channel,
                                source.descriptor.stream,
                            )
                        )
                        checkpoint_isolation_ok &= other_before == other_after
                        continue
                    observations += len(result.batch.observations)
                    created_versions += result.created_versions
                    duplicates += result.duplicate_observations

                if failure_channel is not None:
                    failed = exercise_store.get_checkpoint(
                        fixture_provider,
                        failure_channel,
                        fixture_stream,
                    )
                    checkpoint_isolation_ok &= (
                        failed is not None
                        and failed.health == LiveProviderHealth.DEGRADED
                    )

            checkpoints = {
                item.channel: item
                for item in exercise_store.list_checkpoints()
                if item.provider == fixture_provider and item.stream == fixture_stream
            }
            recovered = all(
                checkpoints.get(channel) is not None
                and checkpoints[channel].health == LiveProviderHealth.REPLAY
                for channel in (LiveChannel.MCP, LiveChannel.WEBSOCKET)
            )
            canonical_signals = len(exercise_store.list_signals(latest_only=True))
        replay_exercised = cycles == 1 or duplicates > 0
        passed = all(
            (
                checkpoint_isolation_ok,
                recovered,
                canonical_signals == 3,
                observed_failures == injected_failures,
                replay_exercised,
            )
        )
        completed_at = datetime.now(UTC)
        report = LiveSoakReport(
            id=f"live-soak-fixture-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}",
            mode="fixture_chaos",
            cycles=cycles,
            observations=observations,
            created_versions=created_versions,
            duplicates=duplicates,
            injected_failures=injected_failures,
            observed_failures=observed_failures,
            checkpoint_isolation_ok=checkpoint_isolation_ok,
            passed=passed,
            started_at=started_at,
            completed_at=completed_at,
            notes=[
                "Synthetic replay only; no current market data was used.",
                f"canonical_signals={canonical_signals}",
                f"recovered={str(recovered).lower()}",
                "failed_channels="
                + (",".join(item.value for item in failed_channels) or "none"),
            ],
        )
        return self.store.save_soak_report(report)

    def run_providers(
        self,
        *,
        cycles: int = 6,
        interval_seconds: float = 10,
    ) -> LiveSoakReport:
        if not 1 <= cycles <= 10_000:
            raise ValueError("provider soak cycles must be between 1 and 10000")
        if not 0 <= interval_seconds <= 3600:
            raise ValueError("provider soak interval must be between 0 and 3600 seconds")
        settings = LiveProviderSettings.from_environment()
        missing: list[str] = []
        if not settings.mcp_bearer_token:
            missing.append("JIN10_MCP_BEARER_TOKEN")
        if not settings.websocket_secret_key:
            missing.append("JIN10_WEBSOCKET_SECRET_KEY")
        if missing:
            raise ValueError(
                "credentialed provider soak requires both equal-priority channels: "
                + ", ".join(missing)
            )

        started_at = datetime.now(UTC)
        runtime = LiveGatewayRuntime(self.store.db_path)
        observed_failures = 0
        runtime.start()
        try:
            for cycle in range(cycles):
                if interval_seconds and cycle:
                    time.sleep(interval_seconds)
                for checkpoint in self.store.list_checkpoints():
                    if checkpoint.provider == "jin10" and checkpoint.health in {
                        LiveProviderHealth.DEGRADED,
                        LiveProviderHealth.NOT_CONFIGURED,
                        LiveProviderHealth.OFF,
                    }:
                        observed_failures += 1
        finally:
            runtime.stop()

        checkpoints = [
            item for item in self.store.list_checkpoints() if item.provider == "jin10"
        ]
        channels = {item.channel for item in checkpoints}
        checkpoint_isolation_ok = {
            LiveChannel.MCP,
            LiveChannel.WEBSOCKET,
        } <= channels
        passed = checkpoint_isolation_ok and observed_failures == 0
        completed_at = datetime.now(UTC)
        report = LiveSoakReport(
            id=f"live-soak-providers-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}",
            mode="credentialed_providers",
            cycles=cycles,
            observations=len(self.store.list_observations(limit=5000)),
            created_versions=len(self.store.list_signals(latest_only=False)),
            duplicates=0,
            injected_failures=0,
            observed_failures=observed_failures,
            checkpoint_isolation_ok=checkpoint_isolation_ok,
            passed=passed,
            started_at=started_at,
            completed_at=completed_at,
            notes=[
                "Live provider credentials were present; no credential values were persisted.",
                "channels=" + ",".join(sorted(item.value for item in channels)),
            ],
        )
        return self.store.save_soak_report(report)
