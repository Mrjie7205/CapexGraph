from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from capexgraph.domain import (
    LiveChannel,
    LiveProviderCheckpoint,
    SignalObservation,
)


class LiveSourceDescriptor(BaseModel):
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    channel: LiveChannel
    stream: str = Field(min_length=1)
    transport: str = Field(min_length=1)
    requires_credentials: bool
    fixture: bool = False

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.channel.value}:{self.stream}"


class LiveEventBatch(BaseModel):
    descriptor: LiveSourceDescriptor
    observations: list[SignalObservation] = Field(default_factory=list)
    checkpoint: LiveProviderCheckpoint
    has_more: bool = False


@runtime_checkable
class LiveEventSource(Protocol):
    @property
    def descriptor(self) -> LiveSourceDescriptor: ...

    def read(
        self,
        checkpoint: LiveProviderCheckpoint | None = None,
        *,
        limit: int = 100,
    ) -> LiveEventBatch: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
