from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.resources import files

from capexgraph.domain import (
    LiveChannel,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    SignalObservation,
)
from capexgraph.live.base import (
    Clock,
    LiveEventBatch,
    LiveSourceDescriptor,
)


class FrozenClock:
    def __init__(self, value: datetime) -> None:
        self.advance_to(value)

    def now(self) -> datetime:
        return self._value

    def advance_to(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("frozen clock requires a timezone-aware datetime")
        self._value = value.astimezone(UTC)


class FrozenEventFeed:
    """Deterministic source that replays one channel from a synthetic fixture."""

    def __init__(
        self,
        descriptor: LiveSourceDescriptor,
        observations: list[SignalObservation],
        *,
        clock: Clock,
        fixture_id: str,
    ) -> None:
        invalid = [
            item.id
            for item in observations
            if item.channel != descriptor.channel
            or item.provider != descriptor.provider
            or item.stream != descriptor.stream
        ]
        if invalid:
            raise ValueError(
                f"observations do not match source descriptor: {', '.join(invalid)}"
            )
        self._descriptor = descriptor
        self._observations = sorted(
            observations,
            key=lambda item: (item.observed_at, item.external_id),
        )
        self._clock = clock
        self.fixture_id = fixture_id

    @property
    def descriptor(self) -> LiveSourceDescriptor:
        return self._descriptor

    def read(
        self,
        checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch:
        if not 1 <= limit <= 500:
            raise ValueError("live-event batch limit must be between 1 and 500")
        if checkpoint is not None and (
            checkpoint.provider != self.descriptor.provider
            or checkpoint.channel != self.descriptor.channel
            or checkpoint.stream != self.descriptor.stream
        ):
            raise ValueError("checkpoint belongs to a different live source")
        try:
            start = int(checkpoint.cursor) if checkpoint and checkpoint.cursor else 0
        except ValueError as error:
            raise ValueError("frozen feed cursor must be an integer offset") from error
        if not 0 <= start <= len(self._observations):
            raise ValueError("frozen feed cursor is outside the fixture")

        now = self._clock.now()
        available: list[SignalObservation] = []
        index = start
        while index < len(self._observations) and len(available) < limit:
            item = self._observations[index]
            if item.observed_at > now:
                break
            available.append(item)
            index += 1
        has_more = (
            index < len(self._observations)
            and self._observations[index].observed_at <= now
        )
        last = available[-1] if available else None
        next_checkpoint = LiveProviderCheckpoint(
            provider=self.descriptor.provider,
            provider_version=self.descriptor.provider_version,
            channel=self.descriptor.channel,
            stream=self.descriptor.stream,
            cursor=str(index),
            last_external_id=(
                last.external_id
                if last is not None
                else checkpoint.last_external_id if checkpoint else None
            ),
            last_published_at=(
                last.published_at
                if last is not None
                else checkpoint.last_published_at if checkpoint else None
            ),
            last_observed_at=(
                last.observed_at
                if last is not None
                else checkpoint.last_observed_at if checkpoint else None
            ),
            health=LiveProviderHealth.REPLAY,
            calls_used=(checkpoint.calls_used if checkpoint else 0) + 1,
            updated_at=now,
            metadata={
                "fixture_id": self.fixture_id,
                "synthetic": True,
                "remaining": len(self._observations) - index,
            },
        )
        return LiveEventBatch(
            descriptor=self.descriptor,
            observations=available,
            checkpoint=next_checkpoint,
            has_more=has_more,
        )


def load_frozen_dual_channel_feeds(
    *,
    clock: Clock | None = None,
) -> tuple[FrozenEventFeed, FrozenEventFeed]:
    fixture_path = files("capexgraph.fixtures").joinpath(
        "live_jin10_dual_channel.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture = payload["fixture"]
    observations = [
        SignalObservation(
            provider=fixture["provider"],
            provider_version=fixture["provider_version"],
            stream=fixture["stream"],
            **item,
        )
        for item in payload["events"]
    ]
    resolved_clock = clock or FrozenClock(
        max(item.observed_at for item in observations)
    )

    def build(channel: LiveChannel) -> FrozenEventFeed:
        descriptor = LiveSourceDescriptor(
            provider=fixture["provider"],
            provider_version=fixture["provider_version"],
            channel=channel,
            stream=fixture["stream"],
            transport="frozen_fixture",
            requires_credentials=False,
            fixture=True,
        )
        return FrozenEventFeed(
            descriptor,
            [item for item in observations if item.channel == channel],
            clock=resolved_clock,
            fixture_id=fixture["id"],
        )

    return build(LiveChannel.MCP), build(LiveChannel.WEBSOCKET)
