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


class EvidenceMode(StrEnum):
    PARTIAL = "partial"
    STRICT = "strict"


class CoverageLevel(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FORWARD_ONLY = "forward_only"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"


class DataQualityStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class CorporateEventType(StrEnum):
    REGULATORY_FILING = "regulatory_filing"
    FINANCIAL_REPORT = "financial_report"
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    DIVIDEND = "dividend"
    SPLIT = "split"
    INDEX_CHANGE = "index_change"
    LOCKUP_EXPIRY = "lockup_expiry"
    INVESTOR_DAY = "investor_day"
    CAPEX_MILESTONE = "capex_milestone"
    PRODUCTION_MILESTONE = "production_milestone"
    OTHER = "other"


class CorporateEventStatus(StrEnum):
    SCHEDULED = "scheduled"
    ANNOUNCED = "announced"
    REVISED = "revised"
    OCCURRED = "occurred"
    CANCELLED = "cancelled"


class QualitySeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


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
    adjusted_close: float | None = None
    volume: float | None = None

    @property
    def return_close(self) -> float:
        """Price series used for total-return comparisons."""

        return self.adjusted_close if self.adjusted_close is not None else self.close


class ProviderCapability(BaseModel):
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    markets: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)
    history: CoverageLevel
    adjusted_close: bool
    corporate_actions: CoverageLevel
    delisted_securities: CoverageLevel
    rate_limit: str = ""
    license: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class DataQualityIssue(BaseModel):
    code: str = Field(min_length=1)
    severity: QualitySeverity
    message: str = Field(min_length=1)
    dates: list[date] = Field(default_factory=list)


class DataQualityResult(BaseModel):
    status: DataQualityStatus
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bar_count: int = Field(ge=0)
    first_date: date | None = None
    latest_date: date | None = None
    issues: list[DataQualityIssue] = Field(default_factory=list)

    @property
    def blocks_persistence(self) -> bool:
        return self.status == DataQualityStatus.FAIL


class MarketBarSet(BaseModel):
    ticker: str = Field(min_length=1)
    market: str = Field(min_length=2)
    exchange: str = Field(min_length=2)
    currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_url: HttpUrl | None = None
    raw_hash: str = Field(min_length=64, max_length=64)
    bars: list[MarketBar]


class MarketSyncResult(BaseModel):
    bar_set: MarketBarSet
    quality: DataQualityResult
    persisted_bars: int = Field(ge=0)
    raw_path: str | None = None


class CorporateEventVersion(BaseModel):
    id: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    version: int = Field(ge=1)
    version_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    ticker: str | None = None
    entity_name: str = Field(min_length=1)
    market: str = Field(min_length=2)
    event_type: CorporateEventType
    status: CorporateEventStatus
    title: str = Field(min_length=1)
    description: str = ""
    announced_date: date | None = None
    expected_date: date | None = None
    effective_date: date | None = None
    occurred_date: date | None = None
    cancelled_date: date | None = None
    known_at: datetime
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_suggestion_id: str | None = None
    evidence_id: str | None = None
    source_url: HttpUrl
    source_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    revision_reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_event_timeline(self) -> CorporateEventVersion:
        if self.known_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("event known_at and observed_at must be timezone-aware")
        self.known_at = self.known_at.astimezone(UTC)
        self.observed_at = self.observed_at.astimezone(UTC)
        if self.known_at > self.observed_at:
            raise ValueError("event cannot be observed before its source was public")
        if not any(
            (
                self.announced_date,
                self.expected_date,
                self.effective_date,
                self.occurred_date,
                self.cancelled_date,
            )
        ):
            raise ValueError("event requires an announced, expected, effective, or occurred date")
        if not self.source_suggestion_id and not self.evidence_id:
            raise ValueError("event requires a source suggestion or captured evidence")
        if self.status == CorporateEventStatus.SCHEDULED and self.expected_date is None:
            raise ValueError("scheduled events require expected_date")
        if (
            self.status == CorporateEventStatus.OCCURRED
            and self.occurred_date is None
            and self.effective_date is None
        ):
            raise ValueError("occurred events require occurred_date or effective_date")
        if self.status == CorporateEventStatus.CANCELLED and self.cancelled_date is None:
            raise ValueError("cancelled events require cancelled_date")
        return self


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
    price_basis: str = "raw_close"
    return_basis: str = "adjusted_close_with_raw_fallback"
    source_url: HttpUrl | None = None


class FinancialMetric(BaseModel):
    ticker: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    period_end: date
    value: float
    unit: str = Field(min_length=1)
    source_evidence_id: str | None = None


class FinancialStatement(StrEnum):
    INCOME = "income_statement"
    CASH_FLOW = "cash_flow"
    BALANCE_SHEET = "balance_sheet"
    SUPPLEMENTAL = "supplemental"


class FinancialFactType(StrEnum):
    REPORTED = "reported"
    DERIVED = "derived"
    RESTATED = "restated"
    MISSING = "missing"


class FinancialFact(BaseModel):
    id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    statement: FinancialStatement
    metric: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    period_start: date | None = None
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filed_date: date | None = None
    accession: str | None = None
    value: float | None = None
    unit: str = Field(min_length=1)
    fact_type: FinancialFactType = FinancialFactType.REPORTED
    source_evidence_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    formula: str | None = None
    input_fact_ids: list[str] = Field(default_factory=list)
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fact_shape(self) -> FinancialFact:
        if self.fact_type == FinancialFactType.MISSING:
            if self.value is not None:
                raise ValueError("missing financial facts cannot contain a value")
        elif self.value is None:
            raise ValueError("reported, restated, and derived facts require a value")
        if self.fact_type == FinancialFactType.DERIVED:
            if not self.formula or not self.input_fact_ids:
                raise ValueError("derived financial facts require a formula and input_fact_ids")
        elif self.formula or self.input_fact_ids:
            raise ValueError("only derived financial facts may declare formula inputs")
        return self


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
