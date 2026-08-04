from __future__ import annotations

import hashlib
import json
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
    AGENT_REVIEWED = "agent_reviewed"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class EvidenceReviewActor(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


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


class ThemeSourceKind(StrEnum):
    INDEX = "index"
    ETF = "etf"
    VENDOR = "vendor"
    MANUAL = "manual"
    EVIDENCE_GRAPH = "evidence_graph"


class ThemeMembershipRole(StrEnum):
    CORE = "core"
    EQUIPMENT = "equipment"
    MATERIAL = "material"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    OTHER = "other"


class MainlineState(StrEnum):
    INSUFFICIENT = "insufficient"
    WATCH = "watch"
    EMERGING = "emerging"
    CONFIRMED = "confirmed"
    FRAGILE = "fragile"
    EXITED = "exited"


class MonitorJobStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


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


class ExtractionCandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class LiveChannel(StrEnum):
    MCP = "mcp"
    WEBSOCKET = "websocket"
    FIXTURE = "fixture"


class LiveSignalCategory(StrEnum):
    FLASH = "flash"
    CALENDAR = "calendar"
    QUOTE = "quote"
    NEWS = "news"
    OTHER = "other"


class LiveRetentionClass(StrEnum):
    EPHEMERAL = "ephemeral"
    METADATA_ONLY = "metadata_only"
    LICENSED_ARCHIVE = "licensed_archive"
    FIXTURE = "fixture"


class LiveMatchStatus(StrEnum):
    SINGLE_CHANNEL = "single_channel"
    MATCHED = "matched"
    DIVERGENT = "divergent"


class LiveVerificationState(StrEnum):
    SIGNAL_ONLY = "signal_only"
    OFFICIAL_SOURCE_PENDING = "official_source_pending"
    EVIDENCE_LINKED = "evidence_linked"


class LiveProviderHealth(StrEnum):
    NOT_CONFIGURED = "not_configured"
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFF = "off"
    EXHAUSTED = "exhausted"
    REPLAY = "replay"


class LiveAlertState(StrEnum):
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"
    MUTED = "muted"


class LiveAnalysisStatus(StrEnum):
    RULES_ONLY = "rules_only"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class LiveVerificationTaskStatus(StrEnum):
    PENDING = "pending"
    SOURCE_SUGGESTED = "source_suggested"
    CAPTURE_PENDING = "capture_pending"
    CAPTURED = "captured"
    EVIDENCE_LINKED = "evidence_linked"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchAction(StrEnum):
    IGNORE = "ignore"
    READ = "read"
    DISMISS = "dismiss"
    MUTE = "mute"
    WATCH = "watch"
    VERIFY = "verify"
    ATTACH = "attach"
    LINKED_REEVALUATION = "linked_reevaluation"


class ProposalHumanStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ImpactDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


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


class EvidenceReviewRecord(BaseModel):
    actor: EvidenceReviewActor
    decision: str = "approved"
    reviewer: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    transport: str | None = None
    source_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    prompt_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rationale: str = Field(min_length=1)
    supporting_quotes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_agent_provenance(self) -> EvidenceReviewRecord:
        if any(not quote.strip() for quote in self.supporting_quotes):
            raise ValueError("Evidence review supporting quotes cannot be blank")
        if self.actor == EvidenceReviewActor.AGENT:
            if not self.provider or not self.model or not self.prompt_hash:
                raise ValueError("Agent review requires provider, model, and prompt hash")
            if self.decision == "approved" and not self.supporting_quotes:
                raise ValueError("Agent review requires at least one exact supporting quote")
        return self


class Evidence(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: EvidenceKind
    source_url: HttpUrl | None = None
    published_at: date | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    excerpt: str = ""
    source_hash: str | None = None
    text_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    publisher: str | None = None
    content_type: str | None = None
    local_path: str | None = None
    status: EvidenceStatus = EvidenceStatus.PROPOSED
    review: EvidenceReviewRecord | None = None


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


class OfficialSourceCapability(BaseModel):
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    markets: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list)
    authentication: str = Field(min_length=1)
    discovery: CoverageLevel
    original_documents: CoverageLevel
    history: CoverageLevel
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


class MarketComparisonResult(BaseModel):
    id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    primary_provider: str = Field(min_length=1)
    reference_provider: str = Field(min_length=1)
    as_of_date: date
    overlap_count: int = Field(ge=0)
    primary_only_count: int = Field(ge=0)
    reference_only_count: int = Field(ge=0)
    max_close_diff_pct: float | None = Field(default=None, ge=0)
    median_close_diff_pct: float | None = Field(default=None, ge=0)
    status: DataQualityStatus
    issues: list[DataQualityIssue] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    comparison_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ThemeDefinition(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    markets: list[str] = Field(default_factory=list)
    benchmark_tickers: dict[str, str] = Field(default_factory=dict)
    valid_from: date
    valid_to: date | None = None
    known_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_definition_time(self) -> ThemeDefinition:
        if self.known_at.tzinfo is None or self.created_at.tzinfo is None:
            raise ValueError("theme timestamps must be timezone-aware")
        self.known_at = self.known_at.astimezone(UTC)
        self.created_at = self.created_at.astimezone(UTC)
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("theme valid_to cannot precede valid_from")
        return self


class ThemeSource(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    kind: ThemeSourceKind
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    market: str = Field(min_length=2)
    source_url: HttpUrl | None = None
    license: str = Field(min_length=1)
    coverage: CoverageLevel = CoverageLevel.PARTIAL
    observed_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_time(self) -> ThemeSource:
        if self.observed_at.tzinfo is None:
            raise ValueError("theme source observed_at must be timezone-aware")
        self.observed_at = self.observed_at.astimezone(UTC)
        return self


class ThemeMembership(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    entity_name: str = Field(min_length=1)
    market: str = Field(min_length=2)
    exchange: str = Field(min_length=2)
    role: ThemeMembershipRole = ThemeMembershipRole.CORE
    valid_from: date
    valid_to: date | None = None
    known_at: datetime
    observed_at: datetime
    membership_weight: float | None = Field(default=None, ge=0)
    recognition_score: float = Field(default=0, ge=0, le=1)
    exposure_score: float | None = Field(default=None, ge=0, le=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_membership_time(self) -> ThemeMembership:
        if self.known_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("membership timestamps must be timezone-aware")
        self.known_at = self.known_at.astimezone(UTC)
        self.observed_at = self.observed_at.astimezone(UTC)
        if self.known_at > self.observed_at:
            raise ValueError("membership cannot be observed before it became knowable")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("membership valid_to cannot precede valid_from")
        return self


class ThemeUniverseMember(BaseModel):
    ticker: str = Field(min_length=1)
    entity_name: str = Field(min_length=1)
    market: str = Field(min_length=2)
    exchange: str = Field(min_length=2)
    roles: list[ThemeMembershipRole] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    recognition_score: float = Field(ge=0, le=1)
    exposure_score: float | None = Field(default=None, ge=0, le=1)
    weight: float | None = Field(default=None, ge=0)


class ThemeUniverseSnapshot(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    definition_id: str = Field(min_length=1)
    as_of_date: date
    knowledge_cutoff: datetime
    members: list[ThemeUniverseMember] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    partial: bool = False
    missing_sources: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_snapshot_time(self) -> ThemeUniverseSnapshot:
        if self.knowledge_cutoff.tzinfo is None or self.generated_at.tzinfo is None:
            raise ValueError("snapshot timestamps must be timezone-aware")
        self.knowledge_cutoff = self.knowledge_cutoff.astimezone(UTC)
        self.generated_at = self.generated_at.astimezone(UTC)
        return self


class ThemeDailyMetric(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    as_of_date: date
    market: str = Field(min_length=2)
    provider: str = Field(min_length=1)
    benchmark_ticker: str = Field(min_length=1)
    weighting: str = Field(pattern=r"^(equal|median|source_weight)$")
    return_20d: float | None = None
    return_60d: float | None = None
    benchmark_return_20d: float | None = None
    relative_strength_20d: float | None = None
    breadth_above_20d: float | None = Field(default=None, ge=0, le=1)
    positive_participation_20d: float | None = Field(default=None, ge=0, le=1)
    dispersion_20d: float | None = Field(default=None, ge=0)
    annualized_volatility: float | None = Field(default=None, ge=0)
    persistence_ratio: float | None = Field(default=None, ge=0, le=1)
    sample_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    quality_status: DataQualityStatus
    issues: list[str] = Field(default_factory=list)
    member_returns: dict[str, float | None] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_metric_time(self) -> ThemeDailyMetric:
        if self.computed_at.tzinfo is None:
            raise ValueError("metric computed_at must be timezone-aware")
        self.computed_at = self.computed_at.astimezone(UTC)
        return self


class MainlinePolicy(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    effective_from: date
    known_at: datetime
    weights: dict[str, float]
    thresholds: dict[str, float]
    min_coverage_ratio: float = Field(ge=0, le=1)
    min_sample_count: int = Field(ge=1)
    experimental: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy(self) -> MainlinePolicy:
        if self.known_at.tzinfo is None or self.created_at.tzinfo is None:
            raise ValueError("policy timestamps must be timezone-aware")
        self.known_at = self.known_at.astimezone(UTC)
        self.created_at = self.created_at.astimezone(UTC)
        if not self.weights or sum(self.weights.values()) <= 0:
            raise ValueError("mainline policy requires positive weights")
        return self


class MainlineAssessment(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    as_of_date: date
    state: MainlineState
    previous_state: MainlineState | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    changed: bool = False
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    component_scores: dict[str, float] = Field(default_factory=dict)
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class MainlineStateEvent(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    as_of_date: date
    from_state: MainlineState | None = None
    to_state: MainlineState
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None


class ThemeResearchProposal(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    action: str = Field(pattern=r"^(theme_scan|reevaluate_candidates)$")
    human_status: ProposalHumanStatus = ProposalHumanStatus.PENDING
    auto_execute: bool = False
    run_id: str | None = None
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MonitorJob(BaseModel):
    id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    market: str = Field(min_length=2)
    as_of_date: date
    policy_id: str = Field(min_length=1)
    status: MonitorJobStatus
    steps: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None
    error: str = ""
    assessment_id: str | None = None
    proposal_id: str | None = None
    artifact_path: str | None = None


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


class SignalObservation(BaseModel):
    id: str = Field(default="", min_length=1)
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    channel: LiveChannel
    stream: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    event_key: str = Field(default="", min_length=1)
    category: LiveSignalCategory
    title: str = Field(min_length=1)
    content: str = ""
    source_url: HttpUrl | None = None
    published_at: datetime
    scheduled_at: datetime | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$")
    retention_class: LiveRetentionClass = LiveRetentionClass.METADATA_ONLY
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def derive_identity(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        provider = str(payload.get("provider", "")).strip()
        channel = str(payload.get("channel", "")).strip()
        external_id = str(payload.get("external_id", "")).strip()
        if not payload.get("event_key") and provider and external_id:
            payload["event_key"] = f"{provider}:{external_id}"
        if not payload.get("content_hash"):
            semantic = {
                "title": str(payload.get("title", "")).strip(),
                "content": str(payload.get("content", "")).strip(),
                "source_url": str(payload.get("source_url") or ""),
                "category": str(payload.get("category", "")).strip(),
            }
            raw = json.dumps(
                semantic,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            payload["content_hash"] = hashlib.sha256(raw).hexdigest()
        if not payload.get("id") and provider and channel and external_id:
            identity = (
                f"{provider}:{channel}:{external_id}:{payload['content_hash']}".encode()
            )
            payload["id"] = f"observation-{hashlib.sha256(identity).hexdigest()[:24]}"
        return payload

    @model_validator(mode="after")
    def validate_observation_timeline(self) -> SignalObservation:
        if self.published_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("signal published_at and observed_at must be timezone-aware")
        self.published_at = self.published_at.astimezone(UTC)
        self.observed_at = self.observed_at.astimezone(UTC)
        if self.scheduled_at is not None:
            if self.scheduled_at.tzinfo is None:
                raise ValueError("signal scheduled_at must be timezone-aware")
            self.scheduled_at = self.scheduled_at.astimezone(UTC)
        if self.published_at > self.observed_at:
            raise ValueError("signal cannot be observed before it was published")
        return self


class LiveSignalVersion(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    version: int = Field(ge=1)
    version_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: LiveSignalCategory
    title: str = Field(min_length=1)
    published_at: datetime
    first_observed_at: datetime
    last_observed_at: datetime
    observation_ids: list[str] = Field(min_length=1)
    channels: list[LiveChannel] = Field(min_length=1)
    match_status: LiveMatchStatus
    verification_state: LiveVerificationState = LiveVerificationState.SIGNAL_ONLY
    revision_reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_signal_version(self) -> LiveSignalVersion:
        timestamps = (
            self.published_at,
            self.first_observed_at,
            self.last_observed_at,
        )
        if any(item.tzinfo is None for item in timestamps):
            raise ValueError("live signal timestamps must be timezone-aware")
        self.published_at = self.published_at.astimezone(UTC)
        self.first_observed_at = self.first_observed_at.astimezone(UTC)
        self.last_observed_at = self.last_observed_at.astimezone(UTC)
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("first_observed_at cannot follow last_observed_at")
        self.observation_ids = sorted(set(self.observation_ids))
        self.channels = sorted(set(self.channels), key=lambda item: item.value)
        if self.match_status == LiveMatchStatus.MATCHED and len(self.channels) < 2:
            raise ValueError("matched signals require at least two channels")
        return self


class LiveProviderCheckpoint(BaseModel):
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    channel: LiveChannel
    stream: str = Field(min_length=1)
    cursor: str = ""
    last_external_id: str | None = None
    last_published_at: datetime | None = None
    last_observed_at: datetime | None = None
    health: LiveProviderHealth
    calls_used: int = Field(default=0, ge=0)
    call_budget: int | None = Field(default=None, ge=1)
    budget_date: date | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.channel.value}:{self.stream}"

    @model_validator(mode="after")
    def validate_checkpoint_timestamps(self) -> LiveProviderCheckpoint:
        for name in ("last_published_at", "last_observed_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None:
                    raise ValueError(f"{name} must be timezone-aware")
                setattr(self, name, value.astimezone(UTC))
        return self


class LiveDeadLetter(BaseModel):
    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    channel: LiveChannel
    stream: str = Field(min_length=1)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    error: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dead_letter_time(self) -> LiveDeadLetter:
        if self.observed_at.tzinfo is None:
            raise ValueError("dead-letter observed_at must be timezone-aware")
        self.observed_at = self.observed_at.astimezone(UTC)
        return self


class LiveRuleAssessment(BaseModel):
    id: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    ruleset_version: str = Field(min_length=1)
    ruleset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relevance: float = Field(ge=0, le=100)
    urgency: float = Field(ge=0, le=100)
    novelty: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=100)
    total_score: float = Field(ge=0, le=100)
    matched_entities: list[str] = Field(default_factory=list)
    matched_themes: list[str] = Field(default_factory=list)
    matched_graph_nodes: list[str] = Field(default_factory=list)
    injection_flags: list[str] = Field(default_factory=list)
    should_alert: bool = False
    rationale: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_assessment_time(self) -> LiveRuleAssessment:
        if self.created_at.tzinfo is None:
            raise ValueError("assessment created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        self.matched_entities = sorted(set(self.matched_entities))
        self.matched_themes = sorted(set(self.matched_themes))
        self.matched_graph_nodes = sorted(set(self.matched_graph_nodes))
        self.injection_flags = sorted(set(self.injection_flags))
        return self


class LiveSignalAnalysis(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    analysis_version: int = Field(ge=1)
    status: LiveAnalysisStatus
    proposal_id: str | None = None
    model_provider: str | None = None
    model: str | None = None
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_call_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_status: str = Field(default="not_applicable", min_length=1)
    failure: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_analysis(self) -> LiveSignalAnalysis:
        if self.created_at.tzinfo is None:
            raise ValueError("analysis created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if self.model_provider is None and (
            self.model is not None or self.prompt_hash is not None or self.model_call_count
        ):
            raise ValueError("model analysis metadata requires model_provider")
        if self.status == LiveAnalysisStatus.COMPLETED and self.model_provider is None:
            raise ValueError("completed model analysis requires model_provider")
        return self


class LiveAlertDelivery(BaseModel):
    id: int | None = Field(default=None, ge=1)
    signal_key: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    state: LiveAlertState = LiveAlertState.UNREAD
    score: float = Field(ge=0, le=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_alert_times(self) -> LiveAlertDelivery:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("alert timestamps must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        self.updated_at = self.updated_at.astimezone(UTC)
        return self


class LiveDeskSettings(BaseModel):
    mcp_enabled: bool = True
    websocket_enabled: bool = True
    flash_enabled: bool = True
    calendar_enabled: bool = True
    quote_enabled: bool = False
    normal_poll_seconds: int = Field(default=120, ge=15, le=3600)
    urgent_poll_seconds: int = Field(default=30, ge=15, le=3600)
    quiet_poll_seconds: int = Field(default=300, ge=30, le=7200)
    alert_score_threshold: float = Field(default=55, ge=0, le=100)
    model_score_threshold: float = Field(default=75, ge=0, le=100)
    cooldown_seconds: int = Field(default=900, ge=0, le=86400)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    entity_aliases: dict[str, list[str]] = Field(default_factory=dict)
    theme_keywords: dict[str, list[str]] = Field(default_factory=dict)
    desktop_notifications: bool = False
    model_provider: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_live_settings(self) -> LiveDeskSettings:
        if self.updated_at.tzinfo is None:
            raise ValueError("live settings updated_at must be timezone-aware")
        self.updated_at = self.updated_at.astimezone(UTC)
        if self.urgent_poll_seconds > self.normal_poll_seconds:
            raise ValueError("urgent poll interval cannot exceed normal interval")
        if self.normal_poll_seconds > self.quiet_poll_seconds:
            raise ValueError("normal poll interval cannot exceed quiet interval")
        self.include_keywords = sorted(
            {item.strip() for item in self.include_keywords if item.strip()}
        )
        self.exclude_keywords = sorted(
            {item.strip() for item in self.exclude_keywords if item.strip()}
        )
        return self


class LiveUserAction(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    action: ResearchAction
    note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_action_time(self) -> LiveUserAction:
        if self.created_at.tzinfo is None:
            raise ValueError("user action created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        return self


class LiveVerificationTask(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    status: LiveVerificationTaskStatus = LiveVerificationTaskStatus.PENDING
    run_id: str | None = None
    source_suggestion_id: str | None = None
    evidence_id: str | None = None
    evidence_link_id: str | None = None
    note: str = ""
    attempts: int = Field(default=0, ge=0)
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_verification_task(self) -> LiveVerificationTask:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("verification-task timestamps must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        self.updated_at = self.updated_at.astimezone(UTC)
        if self.updated_at < self.created_at:
            raise ValueError("verification task cannot be updated before creation")
        if self.evidence_id and not self.run_id:
            raise ValueError("verification-task evidence requires a research run")
        if self.evidence_link_id and self.status != LiveVerificationTaskStatus.EVIDENCE_LINKED:
            raise ValueError("evidence_link_id requires evidence_linked task status")
        return self


class LiveEvidenceLink(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    verification_task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    link_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    linked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    linked_by: str = Field(default="human", min_length=1)

    @model_validator(mode="after")
    def validate_evidence_link(self) -> LiveEvidenceLink:
        if self.linked_at.tzinfo is None:
            raise ValueError("evidence-link timestamp must be timezone-aware")
        self.linked_at = self.linked_at.astimezone(UTC)
        return self


class LiveRunContextLink(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    signal_version_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    parent_run_id: str | None = None
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context: dict[str, Any]
    note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="human", min_length=1)

    @model_validator(mode="after")
    def validate_run_context_link(self) -> LiveRunContextLink:
        if self.created_at.tzinfo is None:
            raise ValueError("run-context timestamp must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if not self.context:
            raise ValueError("run-context links require an immutable context snapshot")
        return self


class LiveAuditEntry(BaseModel):
    id: int | None = Field(default=None, ge=1)
    signal_key: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    actor: str = Field(default="system", min_length=1)
    summary: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_audit_entry(self) -> LiveAuditEntry:
        if self.occurred_at.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        self.occurred_at = self.occurred_at.astimezone(UTC)
        return self


class LiveSoakReport(BaseModel):
    id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    cycles: int = Field(ge=1)
    observations: int = Field(ge=0)
    created_versions: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    injected_failures: int = Field(ge=0)
    observed_failures: int = Field(ge=0)
    checkpoint_isolation_ok: bool
    passed: bool
    started_at: datetime
    completed_at: datetime
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_soak_report(self) -> LiveSoakReport:
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("soak-report timestamps must be timezone-aware")
        self.started_at = self.started_at.astimezone(UTC)
        self.completed_at = self.completed_at.astimezone(UTC)
        if self.completed_at < self.started_at:
            raise ValueError("soak report cannot complete before it starts")
        return self


class LiveCoverageMetrics(BaseModel):
    total_signals: int = Field(ge=0)
    matched: int = Field(ge=0)
    divergent: int = Field(ge=0)
    mcp_only: int = Field(ge=0)
    websocket_only: int = Field(ge=0)
    fixture_only: int = Field(ge=0)
    overlap_ratio: float = Field(ge=0, le=1)
    delivery_delay_p50_seconds: float | None = Field(default=None, ge=0)
    delivery_delay_p95_seconds: float | None = Field(default=None, ge=0)
    freshest_by_channel: dict[str, datetime | None] = Field(default_factory=dict)


class ResearchActionProposal(BaseModel):
    id: str = Field(min_length=1)
    signal_key: str = Field(min_length=1)
    analysis_version: int = Field(ge=1)
    ruleset_version: str = Field(min_length=1)
    model_provider: str | None = None
    model: str | None = None
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    themes: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    graph_nodes: list[str] = Field(default_factory=list)
    direction: ImpactDirection = ImpactDirection.UNKNOWN
    horizon: str = Field(min_length=1)
    novelty: float = Field(ge=0, le=1)
    impact_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    transmission_path: list[str] = Field(default_factory=list)
    price_confirmation: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)
    recommended_action: ResearchAction
    trigger_conditions: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)
    human_status: ProposalHumanStatus = ProposalHumanStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_proposal(self) -> ResearchActionProposal:
        if self.created_at.tzinfo is None:
            raise ValueError("proposal created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if self.model_provider is None and (self.model is not None or self.prompt_hash is not None):
            raise ValueError("model metadata requires model_provider")
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


class DisclosureFactCandidate(BaseModel):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    source_suggestion_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    market: str = Field(min_length=2)
    statement: FinancialStatement
    metric: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    period_end: date
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    value: float
    unit: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    status: ExtractionCandidateStatus = ExtractionCandidateStatus.PENDING
    validation_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    fact_id: str | None = None


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
