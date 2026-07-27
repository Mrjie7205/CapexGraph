from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class RunMode(StrEnum):
    THEME = "theme"
    ANCHOR = "anchor"
    CATALYST = "catalyst"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceKind(StrEnum):
    FILING = "filing"
    COMPANY_DISCLOSURE = "company_disclosure"
    GOVERNMENT = "government"
    TRANSCRIPT = "transcript"
    MARKET_DATA = "market_data"
    NEWS = "news"
    INDUSTRY_INFERENCE = "industry_inference"


class EvidenceStatus(StrEnum):
    PROPOSED = "proposed"
    CAPTURED = "captured"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class SourceSuggestionStatus(StrEnum):
    SUGGESTED = "suggested"
    SELECTED = "selected"
    CAPTURE_PENDING = "capture_pending"
    CAPTURED = "captured"
    DISMISSED = "dismissed"
    CAPTURE_FAILED = "capture_failed"
    DUPLICATE = "duplicate"


class SourceAuthority(StrEnum):
    REGULATOR = "regulator"
    ISSUER = "issuer"
    OTHER = "other"


class RelationshipType(StrEnum):
    SUPPLIES = "supplies"
    CUSTOMER = "customer"
    PEER = "peer"
    DEPENDS_ON = "depends_on"
    TWO_HOP = "two_hop"


class Verdict(StrEnum):
    CANDIDATE = "candidate"
    WATCH = "watch"
    EXCLUDE = "exclude"
    UNRATED = "unrated"


class Evidence(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: EvidenceKind
    source_url: HttpUrl | None = None
    published_at: date | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    excerpt: str = ""
    source_hash: str | None = None
    publisher: str | None = None
    content_type: str | None = None
    local_path: str | None = None
    status: EvidenceStatus = EvidenceStatus.PROPOSED


class SourceSuggestion(BaseModel):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    canonical_url: str = Field(min_length=1)
    kind: EvidenceKind
    publisher: str | None = None
    authority: SourceAuthority = SourceAuthority.OTHER
    reason: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    status: SourceSuggestionStatus = SourceSuggestionStatus.SUGGESTED
    published_at: date | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    selected_at: datetime | None = None
    captured_at: datetime | None = None
    evidence_id: str | None = None
    final_url: HttpUrl | None = None
    content_hash: str | None = None
    duplicate_of: str | None = None
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TickerIdentity(BaseModel):
    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1)
    market: str = Field(min_length=2)
    exchange: str = Field(min_length=2)
    currency: str = Field(min_length=3, max_length=3)
    aliases: list[str] = Field(default_factory=list)
    source_url: HttpUrl | None = None


class MarketBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class MarketSnapshot(BaseModel):
    ticker: str
    as_of_date: date
    price: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    provider: str
    ret_1m_pct: float | None = None
    ret_3m_pct: float | None = None
    range_pos_6mo_pct: float | None = None
    pct_off_6mo_high: float | None = None
    above_sma50: bool | None = None
    stage: str = "unknown"
    source_url: HttpUrl | None = None


class FinancialMetric(BaseModel):
    ticker: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    period_end: date
    value: float
    unit: str = Field(min_length=1)
    source_evidence_id: str | None = None


class SupplyChainNode(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = "company"
    ticker: str | None = None
    market: str | None = None
    layer: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupplyChainEdge(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relationship: RelationshipType
    product: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    confidence: Confidence
    evidence_ids: list[str] = Field(default_factory=list)
    as_of_date: date
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_evidence_for_stronger_claims(self) -> SupplyChainEdge:
        if self.confidence in {Confidence.HIGH, Confidence.MEDIUM} and not self.evidence_ids:
            raise ValueError("medium/high-confidence edges require at least one evidence_id")
        return self


class Trigger(BaseModel):
    metric: str = Field(min_length=1)
    operator: str = Field(pattern=r"^(>|>=|<|<=|==)$")
    value: float
    note: str = ""


class Candidate(BaseModel):
    node_id: str
    verdict: Verdict = Verdict.UNRATED
    thesis: str = ""
    archetypes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW


class PipelineStep(BaseModel):
    key: str
    label: str
    status: StepStatus = StepStatus.PENDING
    agent: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int = Field(default=0, ge=0)
    message: str = ""
    error: str = ""


class StepCheckpoint(BaseModel):
    run_id: str
    step_key: str
    status: StepStatus
    attempt: int = Field(ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str = ""
    error: str = ""
    output: dict[str, Any] = Field(default_factory=dict)


class ResearchRun(BaseModel):
    id: str
    mode: RunMode
    subject: str = Field(min_length=1)
    market: str = Field(min_length=2)
    as_of_date: date
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pipeline: list[PipelineStep] = Field(default_factory=list)
    nodes: list[SupplyChainNode] = Field(default_factory=list)
    edges: list[SupplyChainEdge] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)
