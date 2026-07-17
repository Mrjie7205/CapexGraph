from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from capexgraph.domain import Trigger


class TrackingStage(StrEnum):
    RESEARCH = "research"
    WATCH = "watch"
    VALIDATED = "validated"
    TRIGGERED = "triggered"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class TrackedCandidate(BaseModel):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    label: str = Field(min_length=1)
    benchmark_ticker: str = Field(min_length=1)
    call_date: date
    call_price: float | None = Field(default=None, gt=0)
    call_benchmark_price: float | None = Field(default=None, gt=0)
    stage: TrackingStage = TrackingStage.WATCH
    thesis: str = ""
    invalidation: list[str] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrackingSnapshot(BaseModel):
    id: int | None = None
    tracked_id: str
    as_of_date: date
    price: float = Field(gt=0)
    benchmark_price: float = Field(gt=0)
    return_pct: float
    benchmark_return_pct: float
    alpha_pct: float
    source: str = Field(min_length=1)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TriggerEvent(BaseModel):
    id: int | None = None
    tracked_id: str
    metric: str
    operator: str
    threshold: float
    observed_value: float
    note: str = ""
    as_of_date: date
    acknowledged_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Scorecard(BaseModel):
    tracked: TrackedCandidate
    latest: TrackingSnapshot | None = None
    events: list[TriggerEvent] = Field(default_factory=list)
    snapshot_count: int = 0
    days_tracked: int = 0
