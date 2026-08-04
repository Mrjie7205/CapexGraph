import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field, HttpUrl, SecretStr

from capexgraph import __version__
from capexgraph.connections import (
    codex_login_state,
    connect_jin10_mcp,
    connect_jin10_websocket,
    connection_status,
    disconnect_jin10_mcp,
    disconnect_jin10_websocket,
    select_codex_model,
    start_codex_login,
)
from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    CorporateEventVersion,
    DisclosureFactCandidate,
    Evidence,
    EvidenceKind,
    EvidenceMode,
    FinancialFact,
    FinancialMetric,
    LiveAlertState,
    LiveAuditEntry,
    LiveChannel,
    LiveDeskSettings,
    LiveEvidenceLink,
    LiveMatchStatus,
    LiveRetentionClass,
    LiveRunContextLink,
    LiveSignalCategory,
    LiveSoakReport,
    LiveUserAction,
    LiveVerificationTask,
    LiveVerificationTaskStatus,
    MainlineAssessment,
    MainlinePolicy,
    MainlineStateEvent,
    MarketComparisonResult,
    MarketSnapshot,
    MarketSyncResult,
    MonitorJob,
    OfficialSourceCapability,
    ProviderCapability,
    ResearchAction,
    ResearchRun,
    RunMode,
    RunStatus,
    SourceSuggestion,
    SourceSuggestionStatus,
    StepCheckpoint,
    ThemeDailyMetric,
    ThemeDefinition,
    ThemeMembership,
    ThemeResearchProposal,
    ThemeSource,
    ThemeUniverseSnapshot,
    TickerIdentity,
)
from capexgraph.events import EventCalendarService
from capexgraph.financials import FinancialFactService, ReviewedDisclosureFactService
from capexgraph.fixtures import seed_frozen_market_fixture
from capexgraph.live import (
    LiveImpactAnalyzer,
    LiveResearchBridge,
    LiveSignalStore,
    build_live_diagnostics,
    calculate_live_coverage,
    get_live_runtime,
    load_frozen_dual_channel_feeds,
)
from capexgraph.market import (
    MarketDataService,
    MarketSettings,
    build_market_provider,
    provider_capabilities,
)
from capexgraph.monitoring import MainlineService, MainlineStore
from capexgraph.providers import (
    ModelSettings,
    ProviderName,
    create_research_model,
    redact_provider_secrets,
)
from capexgraph.providers.sources import (
    build_source_provider,
    official_source_capabilities,
)
from capexgraph.reporting import render_run_report
from capexgraph.research import build_executor_for_run
from capexgraph.research.context import EvidenceCoverage, refresh_evidence_coverage
from capexgraph.research.model_runtime import select_run_provider
from capexgraph.runtime import RunStore
from capexgraph.runtime.store import runs_dir
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
from capexgraph.themes import (
    ThemeRegistryService,
    ThemeRegistryStore,
    import_theme_json,
    load_frozen_theme_fixture,
)
from capexgraph.tools import (
    EvidenceSourceRequest,
    TickerResolver,
    capture_market_snapshot,
    collect_evidence_for_run,
    read_run_evidence_text,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metric_items
from capexgraph.tracking import (
    Scorecard,
    TrackedCandidate,
    TrackingService,
    TrackingSnapshot,
    TrackingStage,
    TriggerEvent,
)
from capexgraph.workflows import create_run, load_run, save_run

app = FastAPI(
    title="CapexGraph API",
    description="Evidence-first supply-chain research runtime",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    market: str = Field(default="CN", min_length=2, max_length=12)
    as_of_date: date | None = None
    evidence_mode: EvidenceMode = EvidenceMode.PARTIAL


class ThemeRunRequest(RunRequest):
    provider: ProviderName | None = None
    execute: bool = False
    max_attempts: int = Field(default=2, ge=1, le=10)


class ExecuteRequest(BaseModel):
    until: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=10)
    provider: ProviderName | None = None
    background: bool = False
    evidence_mode: EvidenceMode | None = None


class RunDeleteRequest(BaseModel):
    confirmed: bool = False
    expected_updated_at: datetime


class RunDeleteResponse(BaseModel):
    deleted: bool
    run_id: str
    archived_path: str


class EvidenceCollectRequest(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    kind: EvidenceKind = EvidenceKind.COMPANY_DISCLOSURE
    url: HttpUrl
    published_at: date | None = None
    publisher: str | None = Field(default=None, max_length=120)


class EvidenceReviewRequest(BaseModel):
    approved: bool


class SourceDiscoverRequest(BaseModel):
    provider: str = Field(
        default="sec",
        pattern=r"^(sec|cninfo|sse|szse|bse|opendart|kind)$",
    )
    identifier: str | None = Field(default=None, max_length=200)
    forms: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=100)


class SourceSuggestRequest(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    kind: EvidenceKind = EvidenceKind.COMPANY_DISCLOSURE
    publisher: str | None = Field(default=None, max_length=160)
    published_at: date | None = None
    issuer_domains: list[str] = Field(default_factory=list, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class MarketCaptureRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=80)
    provider: str | None = Field(
        default=None,
        pattern=r"^(eodhd|tushare|yahoo|yahoo-chart)$",
    )
    days: int = Field(default=400, ge=1, le=20000)


class MarketSyncRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=500)
    provider: str | None = Field(
        default=None,
        pattern=r"^(eodhd|tushare|yahoo|yahoo-chart)$",
    )
    days: int = Field(default=400, ge=1, le=20000)


class MarketCompareRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=80)
    primary_provider: str = Field(min_length=1, max_length=80)
    reference_provider: str = Field(min_length=1, max_length=80)
    as_of_date: date
    tolerance_pct: float = Field(default=0.02, gt=0, le=1)
    minimum_overlap: int = Field(default=20, ge=1, le=5000)


class ThemeImportRequest(BaseModel):
    document: dict[str, object]


class ThemeSnapshotRequest(BaseModel):
    as_of_date: date
    knowledge_cutoff: datetime | None = None
    market: str | None = Field(default=None, min_length=2, max_length=12)


class MainlineRunRequest(BaseModel):
    theme_id: str = Field(min_length=1, max_length=120)
    market: str = Field(min_length=2, max_length=12)
    as_of_date: date
    provider: str = Field(min_length=1, max_length=80)
    policy_id: str | None = Field(default=None, max_length=120)
    weighting: str = Field(default="equal", pattern=r"^(equal|median|source_weight)$")


class MainlineBatchRequest(BaseModel):
    market: str = Field(min_length=2, max_length=12)
    as_of_date: date
    provider: str = Field(min_length=1, max_length=80)
    theme_ids: list[str] = Field(default_factory=list, max_length=500)
    weighting: str = Field(default="equal", pattern=r"^(equal|median|source_weight)$")


class ProposalDecisionRequest(BaseModel):
    accepted: bool


class FinancialMetricsRequest(BaseModel):
    items: list[FinancialMetric] = Field(min_length=1, max_length=5000)


class FinancialExtractRequest(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str = Field(default="sec", pattern=r"^(sec|opendart)$")


class DisclosurePreviewRequest(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=200)


class TrackCandidateRequest(BaseModel):
    node_id: str = Field(min_length=1)
    benchmark_ticker: str = "000300.SH"
    call_date: date | None = None
    call_price: float | None = Field(default=None, gt=0)
    call_benchmark_price: float | None = Field(default=None, gt=0)
    capture_live: bool = True
    market_provider: str | None = Field(
        default=None,
        pattern=r"^(eodhd|yahoo|yahoo-chart)$",
    )


class TrackingSnapshotRequest(BaseModel):
    as_of_date: date | None = None
    price: float | None = Field(default=None, gt=0)
    benchmark_price: float | None = Field(default=None, gt=0)
    capture_live: bool = False
    market_provider: str | None = Field(
        default=None,
        pattern=r"^(eodhd|yahoo|yahoo-chart)$",
    )


class TrackingStageRequest(BaseModel):
    stage: TrackingStage


class LivePollRequest(BaseModel):
    stream: str = Field(default="flash", pattern=r"^(flash|calendar)$")


class LiveAnalyzeRequest(BaseModel):
    provider: ProviderName | None = None
    force_model: bool = False


class LiveActionRequest(BaseModel):
    action: ResearchAction
    note: str = Field(default="", max_length=500)


class LiveVerifyRequest(BaseModel):
    run_id: str | None = Field(default=None, max_length=160)
    query: str | None = Field(default=None, max_length=500)
    note: str = Field(default="", max_length=500)
    confirmed: bool = False


class LiveOfficialSourceRequest(BaseModel):
    run_id: str | None = Field(default=None, max_length=160)
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    kind: EvidenceKind = EvidenceKind.COMPANY_DISCLOSURE
    publisher: str | None = Field(default=None, max_length=160)
    published_at: date | None = None
    issuer_domains: list[str] = Field(default_factory=list, max_length=20)
    reason: str | None = Field(default=None, max_length=500)
    confirmed: bool = False


class LiveCaptureTaskRequest(BaseModel):
    retry: bool = False
    confirmed: bool = False


class LiveConfirmationRequest(BaseModel):
    confirmed: bool = False


class LiveTaskReviewRequest(BaseModel):
    approved: bool
    confirmed: bool = False


class LiveRunContextRequest(BaseModel):
    signal_reference: str = Field(min_length=1, max_length=200)
    include_observations: bool = True
    include_analysis: bool = True
    include_proposal: bool = True
    note: str = Field(default="", max_length=500)
    confirmed: bool = False


class LiveLinkedRunRequest(BaseModel):
    parent_run_id: str | None = Field(default=None, max_length=160)
    mode: RunMode | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    market: str | None = Field(default=None, min_length=2, max_length=12)
    as_of_date: date | None = None
    evidence_mode: EvidenceMode | None = None
    provider: ProviderName | None = None
    note: str = Field(default="", max_length=500)
    confirmed: bool = False


class LiveVerificationTaskRecord(BaseModel):
    task: LiveVerificationTask
    source_suggestion: SourceSuggestion | None = None
    evidence: Evidence | None = None
    evidence_link: LiveEvidenceLink | None = None
    run: ResearchRun | None = None


class LiveLinkedRunResponse(BaseModel):
    run: ResearchRun
    link: LiveRunContextLink


class LiveSettingsPatch(BaseModel):
    mcp_enabled: bool | None = None
    websocket_enabled: bool | None = None
    flash_enabled: bool | None = None
    calendar_enabled: bool | None = None
    quote_enabled: bool | None = None
    normal_poll_seconds: int | None = Field(default=None, ge=15, le=3600)
    urgent_poll_seconds: int | None = Field(default=None, ge=15, le=3600)
    quiet_poll_seconds: int | None = Field(default=None, ge=30, le=7200)
    alert_score_threshold: float | None = Field(default=None, ge=0, le=100)
    model_score_threshold: float | None = Field(default=None, ge=0, le=100)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    include_keywords: list[str] | None = Field(default=None, max_length=100)
    exclude_keywords: list[str] | None = Field(default=None, max_length=100)
    entity_aliases: dict[str, list[str]] | None = None
    theme_keywords: dict[str, list[str]] | None = None
    desktop_notifications: bool | None = None
    model_provider: ProviderName | None = None


class SecretConnectionRequest(BaseModel):
    secret: SecretStr = Field(min_length=1, max_length=4096)


class ConnectionConfirmationRequest(BaseModel):
    confirmed: bool = False


class CodexModelSelectionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "name": "CapexGraph", "version": __version__}


@app.get("/api/v1/meta")
def meta() -> dict[str, object]:
    return {
        "name": "CapexGraph",
        "version": __version__,
        "status": "alpha",
        "modes": [mode.value for mode in RunMode],
    }


@app.post("/api/v1/runs/theme", response_model=ResearchRun)
def create_theme_run(request: ThemeRunRequest) -> ResearchRun:
    run = create_run(
        RunMode.THEME,
        request.subject,
        request.market,
        request.as_of_date,
        request.evidence_mode,
    )
    if request.provider is not None:
        run.manifest["model_provider"] = request.provider.value
        run = save_run(run)
    if not request.execute:
        return run
    try:
        return build_executor_for_run(
            run,
            provider=request.provider,
            max_attempts=request.max_attempts,
        ).execute(run.id)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/anchor", response_model=ResearchRun)
def create_anchor_run(request: ThemeRunRequest) -> ResearchRun:
    run = create_run(
        RunMode.ANCHOR,
        request.subject,
        request.market,
        request.as_of_date,
        request.evidence_mode,
    )
    if request.provider is not None:
        run.manifest["model_provider"] = request.provider.value
        run = save_run(run)
    if not request.execute:
        return run
    try:
        return build_executor_for_run(
            run,
            provider=request.provider,
            max_attempts=request.max_attempts,
        ).execute(run.id)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/runs", response_model=list[ResearchRun])
def list_research_runs(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    status: Annotated[RunStatus | None, Query()] = None,
) -> list[ResearchRun]:
    return RunStore().list_runs(limit=limit, status=status)


@app.get("/api/v1/runs/{run_id}", response_model=ResearchRun)
def get_run(run_id: str) -> ResearchRun:
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return run


@app.delete("/api/v1/runs/{run_id}", response_model=RunDeleteResponse)
def delete_run(run_id: str, request: RunDeleteRequest) -> RunDeleteResponse:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required.")
    try:
        archived_path = RunStore().delete_empty_run(
            run_id,
            expected_updated_at=request.expected_updated_at,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RunDeleteResponse(
        deleted=True,
        run_id=run_id,
        archived_path=archived_path.as_posix(),
    )


@app.get("/api/v1/runs/{run_id}/checkpoints", response_model=list[StepCheckpoint])
def get_checkpoints(run_id: str) -> list[StepCheckpoint]:
    if load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return RunStore().list_checkpoints(run_id)


ARTIFACT_ALLOWLIST = {
    "graph.json",
    "evidence.json",
    "financials.json",
    "candidates.json",
    "decision.json",
    "manifest.json",
    "sources.json",
    "coverage.json",
    "evidence-bootstrap.json",
}


@app.get("/api/v1/runs/{run_id}/artifacts/{filename}")
def get_run_artifact(run_id: str, filename: str) -> JSONResponse:
    if load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if filename not in ARTIFACT_ALLOWLIST:
        raise HTTPException(status_code=404, detail="Artifact is not exposed")
    path = runs_dir() / run_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=409, detail="Artifact is invalid JSON") from error
    return JSONResponse(payload)


@app.post("/api/v1/runs/{run_id}/evidence/collect", response_model=Evidence)
def collect_run_evidence(run_id: str, request: EvidenceCollectRequest) -> Evidence:
    try:
        document = collect_evidence_for_run(
            run_id,
            EvidenceSourceRequest(**request.model_dump()),
        )
        return document.evidence
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/evidence/{evidence_id}/review", response_model=Evidence)
def review_evidence(
    run_id: str,
    evidence_id: str,
    request: EvidenceReviewRequest,
) -> Evidence:
    try:
        return review_run_evidence(run_id, evidence_id, approved=request.approved)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/runs/{run_id}/evidence/{evidence_id}/text",
    response_class=PlainTextResponse,
)
def get_evidence_text(run_id: str, evidence_id: str) -> PlainTextResponse:
    try:
        return PlainTextResponse(read_run_evidence_text(run_id, evidence_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}/coverage", response_model=EvidenceCoverage)
def get_evidence_coverage(run_id: str) -> EvidenceCoverage:
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    coverage = refresh_evidence_coverage(run)
    save_run(run)
    return coverage


@app.post("/api/v1/runs/{run_id}/sources/discover", response_model=list[SourceSuggestion])
def discover_run_sources(
    run_id: str,
    request: SourceDiscoverRequest,
) -> list[SourceSuggestion]:
    try:
        provider = build_source_provider(request.provider)
        return SourceDiscoveryService().discover(
            run_id,
            provider=provider,
            identifier=request.identifier,
            forms=request.forms,
            limit=request.limit,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/api/v1/runs/{run_id}/events/discover",
    response_model=list[CorporateEventVersion],
)
def discover_run_events(
    run_id: str,
    request: SourceDiscoverRequest,
) -> list[CorporateEventVersion]:
    try:
        provider = build_source_provider(request.provider)
        return EventCalendarService().discover_official(
            run_id,
            provider=provider,
            identifier=request.identifier,
            forms=request.forms,
            limit=request.limit,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/official/providers",
    response_model=list[OfficialSourceCapability],
)
def list_official_source_providers() -> list[OfficialSourceCapability]:
    """Expose official-source coverage and auth requirements without secrets."""

    return official_source_capabilities()


@app.post(
    "/api/v1/runs/{run_id}/events/refresh",
    response_model=list[CorporateEventVersion],
)
def refresh_run_events(run_id: str) -> list[CorporateEventVersion]:
    try:
        return EventCalendarService().refresh_from_sources(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/runs/{run_id}/events",
    response_model=list[CorporateEventVersion],
)
def list_run_events(
    run_id: str,
    history: Annotated[bool, Query()] = False,
    as_of: Annotated[datetime | None, Query()] = None,
    ticker: Annotated[str | None, Query()] = None,
    event_type: Annotated[CorporateEventType | None, Query(alias="type")] = None,
    status: Annotated[CorporateEventStatus | None, Query()] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> list[CorporateEventVersion]:
    try:
        if as_of is not None and as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return EventCalendarService().list(
            run_id,
            as_of=as_of,
            latest_only=not history,
            ticker=ticker.upper() if ticker else None,
            event_type=event_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/sources/suggest", response_model=SourceSuggestion)
def suggest_run_source(
    run_id: str,
    request: SourceSuggestRequest,
) -> SourceSuggestion:
    try:
        return SourceDiscoveryService().suggest_url(
            run_id,
            url=str(request.url),
            title=request.title,
            kind=request.kind,
            publisher=request.publisher,
            published_at=request.published_at,
            issuer_domains=request.issuer_domains,
            reason=request.reason,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}/sources", response_model=list[SourceSuggestion])
def list_run_sources(
    run_id: str,
    status: Annotated[SourceSuggestionStatus | None, Query()] = None,
) -> list[SourceSuggestion]:
    try:
        return SourceDiscoveryService().list(run_id, status=status)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post(
    "/api/v1/runs/{run_id}/sources/{suggestion_id}/capture",
    response_model=SourceSuggestion,
)
def capture_run_source(run_id: str, suggestion_id: str) -> SourceSuggestion:
    try:
        return SourceDiscoveryService().capture(run_id, suggestion_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, SourceCaptureError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/api/v1/runs/{run_id}/sources/{suggestion_id}/retry",
    response_model=SourceSuggestion,
)
def retry_run_source(run_id: str, suggestion_id: str) -> SourceSuggestion:
    try:
        return SourceDiscoveryService().retry(run_id, suggestion_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, SourceCaptureError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/api/v1/runs/{run_id}/sources/{suggestion_id}/dismiss",
    response_model=SourceSuggestion,
)
def dismiss_run_source(run_id: str, suggestion_id: str) -> SourceSuggestion:
    try:
        return SourceDiscoveryService().dismiss(run_id, suggestion_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/market", response_model=MarketSnapshot)
def capture_run_market(run_id: str, request: MarketCaptureRequest) -> MarketSnapshot:
    try:
        return capture_market_snapshot(
            run_id,
            request.ticker,
            provider=build_market_provider(request.provider),
            days=request.days,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/market/providers")
def market_provider_status() -> dict[str, object]:
    settings = MarketSettings.from_environment()
    capabilities: list[ProviderCapability] = provider_capabilities()
    return {
        "configuration": settings.public_status(),
        "capabilities": [
            capability.model_dump(mode="json") for capability in capabilities
        ],
    }


@app.get("/api/v1/model/providers")
def model_provider_status(probe_codex: bool = False) -> dict[str, object]:
    """Expose model-channel readiness without returning credentials."""

    return {
        "providers": ModelSettings.from_environment().provider_status(
            probe_codex=probe_codex
        )
    }


@app.get("/api/v1/connections")
def local_connection_status(probe_mcp: bool = False) -> dict[str, object]:
    """Return local integration readiness without returning credentials."""

    return connection_status(probe_mcp=probe_mcp)


@app.post("/api/v1/connections/jin10-mcp")
def connect_mcp(request: SecretConnectionRequest) -> dict[str, object]:
    try:
        return connect_jin10_mcp(request.secret.get_secret_value())
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error


@app.post("/api/v1/connections/jin10-mcp/disconnect")
def disconnect_mcp(
    request: ConnectionConfirmationRequest,
) -> dict[str, object]:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required.")
    return disconnect_jin10_mcp()


@app.post("/api/v1/connections/jin10-websocket")
def connect_websocket(request: SecretConnectionRequest) -> dict[str, object]:
    try:
        return connect_jin10_websocket(request.secret.get_secret_value())
    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error


@app.post("/api/v1/connections/jin10-websocket/disconnect")
def disconnect_websocket(
    request: ConnectionConfirmationRequest,
) -> dict[str, object]:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required.")
    return disconnect_jin10_websocket()


@app.post("/api/v1/connections/codex/login")
def connect_codex_account(
    request: ConnectionConfirmationRequest,
) -> dict[str, object]:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required.")
    try:
        return start_codex_login()
    except RuntimeError as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error


@app.get("/api/v1/connections/codex/login")
def get_codex_login_state() -> dict[str, object]:
    try:
        return codex_login_state()
    except RuntimeError as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error


@app.post("/api/v1/connections/codex/model")
def save_codex_model(request: CodexModelSelectionRequest) -> dict[str, object]:
    try:
        return select_codex_model(request.model)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error


@app.post("/api/v1/market/sync", response_model=list[MarketSyncResult])
def sync_market_history(request: MarketSyncRequest) -> list[MarketSyncResult]:
    try:
        service = MarketDataService(provider=build_market_provider(request.provider))
        return service.sync_many(request.tickers, days=request.days)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/market/compare", response_model=MarketComparisonResult)
def compare_market_history(request: MarketCompareRequest) -> MarketComparisonResult:
    try:
        return MarketDataService().compare(
            request.ticker,
            primary_provider=request.primary_provider,
            reference_provider=request.reference_provider,
            as_of_date=request.as_of_date,
            tolerance_pct=request.tolerance_pct,
            minimum_overlap=request.minimum_overlap,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/market/comparisons", response_model=list[MarketComparisonResult])
def list_market_comparisons(
    ticker: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
) -> list[MarketComparisonResult]:
    return MarketDataService().store.list_comparisons(
        ticker.upper() if ticker else None,
        limit=limit,
    )


@app.post("/api/v1/themes/fixture")
def import_frozen_theme_fixture() -> dict[str, object]:
    service = ThemeRegistryService()
    result = load_frozen_theme_fixture()
    definition = service.persist_import(result)
    market = seed_frozen_market_fixture()
    return {
        "definition": definition.model_dump(mode="json"),
        "source_count": len(result.sources),
        "membership_count": len(result.memberships),
        "market": market,
        "notice": "Synthetic frozen history; not current constituent data.",
    }


@app.post("/api/v1/themes/import")
def import_theme_document(request: ThemeImportRequest) -> dict[str, object]:
    try:
        result = import_theme_json(request.document)
        definition = ThemeRegistryService().persist_import(result)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "definition": definition.model_dump(mode="json"),
        "source_count": len(result.sources),
        "membership_count": len(result.memberships),
    }


@app.get("/api/v1/themes", response_model=list[ThemeDefinition])
def list_themes() -> list[ThemeDefinition]:
    return ThemeRegistryService().list_definitions()


@app.get("/api/v1/themes/{theme_id}/sources", response_model=list[ThemeSource])
def list_theme_sources(theme_id: str) -> list[ThemeSource]:
    return ThemeRegistryService().list_sources(theme_id)


@app.get(
    "/api/v1/themes/{theme_id}/memberships",
    response_model=list[ThemeMembership],
)
def list_theme_memberships(
    theme_id: str,
    as_of_date: Annotated[date, Query(alias="as_of")],
    knowledge_cutoff: Annotated[datetime | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=12)] = None,
) -> list[ThemeMembership]:
    try:
        return ThemeRegistryService().list_memberships(
            theme_id,
            as_of_date=as_of_date,
            knowledge_cutoff=knowledge_cutoff,
            market=market.upper() if market else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/api/v1/themes/{theme_id}/snapshots",
    response_model=ThemeUniverseSnapshot,
)
def create_theme_snapshot(
    theme_id: str,
    request: ThemeSnapshotRequest,
) -> ThemeUniverseSnapshot:
    try:
        return ThemeRegistryService().snapshot(
            theme_id,
            as_of_date=request.as_of_date,
            knowledge_cutoff=request.knowledge_cutoff,
            market=request.market,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/themes/{theme_id}/snapshots",
    response_model=list[ThemeUniverseSnapshot],
)
def list_theme_snapshots(
    theme_id: str,
    as_of_date: Annotated[date | None, Query(alias="as_of")] = None,
) -> list[ThemeUniverseSnapshot]:
    return ThemeRegistryStore().list_snapshots(theme_id, as_of_date=as_of_date)


@app.post("/api/v1/mainline/policies/default", response_model=MainlinePolicy)
def create_default_mainline_policy() -> MainlinePolicy:
    return MainlineService().ensure_default_policy()


@app.get("/api/v1/mainline/policies", response_model=list[MainlinePolicy])
def list_mainline_policies() -> list[MainlinePolicy]:
    return MainlineStore().list_policies()


@app.post("/api/v1/mainline/run", response_model=MonitorJob)
def run_mainline_monitor(request: MainlineRunRequest) -> MonitorJob:
    try:
        return MainlineService().run_daily(
            request.theme_id,
            market=request.market,
            as_of_date=request.as_of_date,
            provider=request.provider,
            policy_id=request.policy_id,
            weighting=request.weighting,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/mainline/run-all", response_model=list[MonitorJob])
def run_all_mainline_monitors(request: MainlineBatchRequest) -> list[MonitorJob]:
    return MainlineService().run_batch(
        market=request.market,
        as_of_date=request.as_of_date,
        provider=request.provider,
        theme_ids=request.theme_ids or None,
        weighting=request.weighting,
    )


@app.get(
    "/api/v1/mainline/assessments",
    response_model=list[MainlineAssessment],
)
def list_mainline_assessments(
    theme_id: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[MainlineAssessment]:
    return MainlineStore().list_assessments(theme_id, limit=limit)


@app.get("/api/v1/mainline/metrics", response_model=list[ThemeDailyMetric])
def list_mainline_metrics(
    theme_id: Annotated[str, Query(min_length=1, max_length=120)],
    market: Annotated[str | None, Query(max_length=12)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
) -> list[ThemeDailyMetric]:
    return MainlineStore().list_metrics(
        theme_id,
        market=market.upper() if market else None,
        limit=limit,
    )


@app.get("/api/v1/mainline/events", response_model=list[MainlineStateEvent])
def list_mainline_events(
    theme_id: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[MainlineStateEvent]:
    return MainlineStore().list_state_events(theme_id, limit=limit)


@app.post(
    "/api/v1/mainline/events/{event_id}/acknowledge",
    response_model=MainlineStateEvent,
)
def acknowledge_mainline_event(event_id: str) -> MainlineStateEvent:
    try:
        return MainlineStore().acknowledge_state_event(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/mainline/jobs", response_model=list[MonitorJob])
def list_mainline_jobs(
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[MonitorJob]:
    return MainlineStore().list_jobs(limit=limit)


@app.get(
    "/api/v1/mainline/proposals",
    response_model=list[ThemeResearchProposal],
)
def list_mainline_proposals(
    theme_id: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[ThemeResearchProposal]:
    return MainlineStore().list_proposals(theme_id, limit=limit)


@app.post(
    "/api/v1/mainline/proposals/{proposal_id}/decision",
    response_model=ThemeResearchProposal,
)
def decide_mainline_proposal(
    proposal_id: str,
    request: ProposalDecisionRequest,
) -> ThemeResearchProposal:
    try:
        return MainlineService().decide_proposal(
            proposal_id,
            accepted=request.accepted,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/financials", response_model=list[FinancialMetric])
def attach_run_financials(
    run_id: str,
    request: FinancialMetricsRequest,
) -> list[FinancialMetric]:
    try:
        return attach_financial_metric_items(run_id, request.items)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/financials/extract", response_model=list[FinancialFact])
def extract_run_financial_facts(
    run_id: str,
    request: FinancialExtractRequest,
) -> list[FinancialFact]:
    try:
        service = FinancialFactService()
        return service.extract(
            run_id,
            identifier=request.identifier,
            provider=service.provider(request.provider),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}/financials", response_model=list[FinancialFact])
def list_run_financial_facts(run_id: str) -> list[FinancialFact]:
    try:
        return FinancialFactService().list(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post(
    "/api/v1/runs/{run_id}/financials/preview-reviewed",
    response_model=list[DisclosureFactCandidate],
)
def preview_reviewed_disclosure_facts(
    run_id: str,
    request: DisclosurePreviewRequest,
) -> list[DisclosureFactCandidate]:
    try:
        return ReviewedDisclosureFactService().preview(run_id, request.evidence_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/runs/{run_id}/financials/candidates",
    response_model=list[DisclosureFactCandidate],
)
def list_reviewed_disclosure_fact_candidates(
    run_id: str,
) -> list[DisclosureFactCandidate]:
    if load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return ReviewedDisclosureFactService().store.list(run_id)


@app.post(
    "/api/v1/runs/{run_id}/financials/candidates/{candidate_id}/decision",
    response_model=DisclosureFactCandidate,
)
def decide_reviewed_disclosure_fact_candidate(
    run_id: str,
    candidate_id: str,
    request: ProposalDecisionRequest,
) -> DisclosureFactCandidate:
    try:
        return ReviewedDisclosureFactService().decide(
            run_id,
            candidate_id,
            accepted=request.accepted,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/tickers/resolve", response_model=TickerIdentity)
def resolve_ticker(query: Annotated[str, Query(min_length=1, max_length=80)]) -> TickerIdentity:
    try:
        return TickerResolver().resolve(query)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/tracking", response_model=TrackedCandidate)
def track_run_candidate(run_id: str, request: TrackCandidateRequest) -> TrackedCandidate:
    try:
        return TrackingService().track_run_candidate(
            run_id,
            request.node_id,
            benchmark_ticker=request.benchmark_ticker,
            call_date=request.call_date,
            call_price=request.call_price,
            call_benchmark_price=request.call_benchmark_price,
            provider=(
                build_market_provider(request.market_provider)
                if request.capture_live
                else None
            ),
            capture_live=request.capture_live,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v1/tracking", response_model=list[Scorecard])
def tracking_scoreboard() -> list[Scorecard]:
    return TrackingService().scoreboard()


@app.get("/api/v1/tracking/stages", response_model=dict[str, list[Scorecard]])
def tracking_stage_board() -> dict[str, list[Scorecard]]:
    return TrackingService().stage_board()


@app.get("/api/v1/tracking/compare", response_model=dict[str, list[Scorecard]])
def compare_tracked_runs() -> dict[str, list[Scorecard]]:
    grouped: dict[str, list[Scorecard]] = {}
    for card in TrackingService().scoreboard():
        grouped.setdefault(card.tracked.run_id, []).append(card)
    return grouped


@app.post("/api/v1/tracking/{tracked_id}/snapshots", response_model=TrackingSnapshot)
def add_tracking_snapshot(
    tracked_id: str,
    request: TrackingSnapshotRequest,
) -> TrackingSnapshot:
    service = TrackingService()
    try:
        if request.capture_live:
            return service.capture_live_snapshot(
                tracked_id,
                provider=build_market_provider(request.market_provider),
            )
        if request.price is None or request.benchmark_price is None:
            raise ValueError("Manual snapshots require price and benchmark_price")
        return service.add_snapshot(
            tracked_id,
            as_of_date=request.as_of_date or date.today(),
            price=request.price,
            benchmark_price=request.benchmark_price,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.patch("/api/v1/tracking/{tracked_id}/stage", response_model=TrackedCandidate)
def update_tracking_stage(
    tracked_id: str,
    request: TrackingStageRequest,
) -> TrackedCandidate:
    try:
        return TrackingService().store.update_stage(tracked_id, request.stage)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/v1/tracking/events/{event_id}/ack", response_model=TriggerEvent)
def acknowledge_trigger_event(event_id: int) -> TriggerEvent:
    try:
        return TrackingService().store.acknowledge_event(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}/report", response_class=HTMLResponse)
def get_run_report(run_id: str) -> HTMLResponse:
    try:
        path = render_run_report(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return HTMLResponse(path.read_text(encoding="utf-8"))


def _background_execute(
    run_id: str,
    provider: ProviderName | None,
    max_attempts: int,
    until: str | None,
    retry_failed: bool,
) -> None:
    run = load_run(run_id)
    if run is None:
        return
    try:
        build_executor_for_run(
            run,
            provider=provider,
            max_attempts=max_attempts,
        ).execute(run_id, until=until, retry_failed=retry_failed)
    except Exception as error:  # noqa: BLE001 - persist background failures for the UI
        current = load_run(run_id)
        if current is not None:
            current.status = RunStatus.FAILED
            current.manifest["background_error"] = (
                f"{type(error).__name__}: {redact_provider_secrets(error)}"
            )
            save_run(current)


@app.post("/api/v1/runs/{run_id}/execute", response_model=ResearchRun)
def execute_run(
    run_id: str,
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
) -> ResearchRun:
    try:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        if request.evidence_mode is not None:
            run.manifest["evidence_mode"] = request.evidence_mode.value
            run = save_run(run)
        selected_provider = request.provider
        if run.mode in {RunMode.THEME, RunMode.ANCHOR}:
            selected_provider = select_run_provider(run, request.provider)
        if request.background:
            background_tasks.add_task(
                _background_execute,
                run_id,
                selected_provider,
                request.max_attempts,
                request.until,
                False,
            )
            return run
        return build_executor_for_run(
            run,
            provider=selected_provider,
            max_attempts=request.max_attempts,
        ).execute(
            run_id,
            until=request.until,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/resume", response_model=ResearchRun)
def resume_run(
    run_id: str,
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
) -> ResearchRun:
    try:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        if request.evidence_mode is not None:
            run.manifest["evidence_mode"] = request.evidence_mode.value
            run = save_run(run)
        selected_provider = request.provider
        if run.mode in {RunMode.THEME, RunMode.ANCHOR}:
            selected_provider = select_run_provider(run, request.provider)
        if request.background:
            background_tasks.add_task(
                _background_execute,
                run_id,
                selected_provider,
                request.max_attempts,
                request.until,
                True,
            )
            return run
        return build_executor_for_run(
            run,
            provider=selected_provider,
            max_attempts=request.max_attempts,
        ).execute(
            run_id,
            until=request.until,
            retry_failed=True,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _live_bridge() -> LiveResearchBridge:
    return LiveResearchBridge(get_live_runtime().store)


def _live_task_record(
    bridge: LiveResearchBridge,
    task: LiveVerificationTask,
) -> LiveVerificationTaskRecord:
    suggestion = (
        bridge.source_service.store.get(task.source_suggestion_id)
        if task.source_suggestion_id
        else None
    )
    run = load_run(task.run_id) if task.run_id else None
    evidence = (
        next((item for item in run.evidence if item.id == task.evidence_id), None)
        if run is not None and task.evidence_id
        else None
    )
    link = (
        bridge.store.get_evidence_link(task.evidence_link_id)
        if task.evidence_link_id
        else None
    )
    return LiveVerificationTaskRecord(
        task=task,
        source_suggestion=suggestion,
        evidence=evidence,
        evidence_link=link,
        run=run,
    )


def _live_source_scope(observations) -> str:
    fixture_observations = sum(
        item.retention_class == LiveRetentionClass.FIXTURE for item in observations
    )
    if observations and fixture_observations == len(observations):
        return "fixture"
    if fixture_observations:
        return "mixed"
    return "live"


def _observations_by_ids_batched(
    store: LiveSignalStore,
    observation_ids: list[str],
) -> list:
    observations: list = []
    for start in range(0, len(observation_ids), 500):
        observations.extend(
            store.observations_by_ids(observation_ids[start : start + 500])
        )
    return observations


def _live_event_payload(
    signal,
    *,
    observations,
    assessment,
    proposal,
    analysis,
    alert,
    actions,
    verification_tasks,
    evidence_links,
    run_links,
) -> dict[str, object]:
    return {
        "signal": signal.model_dump(mode="json"),
        "observations": [item.model_dump(mode="json") for item in observations],
        "assessment": (
            assessment.model_dump(mode="json") if assessment is not None else None
        ),
        "proposal": proposal.model_dump(mode="json") if proposal is not None else None,
        "analysis": analysis.model_dump(mode="json") if analysis is not None else None,
        "alert": alert.model_dump(mode="json") if alert is not None else None,
        "actions": [item.model_dump(mode="json") for item in actions],
        "verification_tasks": [
            item.model_dump(mode="json") for item in verification_tasks
        ],
        "evidence_links": [item.model_dump(mode="json") for item in evidence_links],
        "run_links": [item.model_dump(mode="json") for item in run_links],
        "source_scope": _live_source_scope(observations),
        "trust_notice": (
            "The aggregator message remains a secondary signal, not Evidence. "
            "Only separately listed reviewed official Evidence links may support "
            "factual research claims."
        ),
    }


def _live_event_record(store: LiveSignalStore, signal) -> dict[str, object]:
    proposals = store.list_proposals(signal_key=signal.signal_key)
    analyses = store.list_analyses(signal_key=signal.signal_key)
    return _live_event_payload(
        signal,
        observations=store.observations_by_ids(signal.observation_ids),
        assessment=store.get_assessment(signal.id),
        proposal=proposals[0] if proposals else None,
        analysis=analyses[0] if analyses else None,
        alert=store.get_alert(signal.signal_key),
        actions=store.list_user_actions(signal.signal_key),
        verification_tasks=store.list_verification_tasks(
            signal_key=signal.signal_key
        ),
        evidence_links=store.list_evidence_links(signal_key=signal.signal_key),
        run_links=store.list_run_context_links(signal_key=signal.signal_key),
    )


def _live_event_records(store: LiveSignalStore, signals: list) -> list[dict[str, object]]:
    if not signals:
        return []
    signal_keys = {signal.signal_key for signal in signals}
    signal_ids = {signal.id for signal in signals}
    observation_ids = list(
        dict.fromkeys(
            observation_id
            for signal in signals
            for observation_id in signal.observation_ids
        )
    )
    observations_by_id = {
        item.id: item
        for item in _observations_by_ids_batched(store, observation_ids)
    }
    assessments_by_signal_id = {
        item.signal_version_id: item
        for item in store.list_assessments()
        if item.signal_version_id in signal_ids
    }
    proposals_by_key = {}
    for item in store.list_proposals():
        if item.signal_key in signal_keys:
            proposals_by_key.setdefault(item.signal_key, item)
    analyses_by_key = {}
    for item in store.list_analyses():
        if item.signal_key in signal_keys:
            analyses_by_key.setdefault(item.signal_key, item)
    alerts_by_key = {
        item.signal_key: item
        for item in store.list_alerts(limit=1_000_000)
        if item.signal_key in signal_keys
    }

    def group_by_signal(items) -> dict[str, list]:
        grouped: dict[str, list] = {}
        for item in items:
            if item.signal_key in signal_keys:
                grouped.setdefault(item.signal_key, []).append(item)
        return grouped

    actions_by_key = group_by_signal(store.list_user_actions())
    tasks_by_key = group_by_signal(store.list_verification_tasks())
    evidence_by_key = group_by_signal(store.list_evidence_links())
    runs_by_key = group_by_signal(store.list_run_context_links())
    return [
        _live_event_payload(
            signal,
            observations=[
                observations_by_id[item_id]
                for item_id in signal.observation_ids
                if item_id in observations_by_id
            ],
            assessment=assessments_by_signal_id.get(signal.id),
            proposal=proposals_by_key.get(signal.signal_key),
            analysis=analyses_by_key.get(signal.signal_key),
            alert=alerts_by_key.get(signal.signal_key),
            actions=actions_by_key.get(signal.signal_key, []),
            verification_tasks=tasks_by_key.get(signal.signal_key, []),
            evidence_links=evidence_by_key.get(signal.signal_key, []),
            run_links=runs_by_key.get(signal.signal_key, []),
        )
        for signal in signals
    ]


def _filtered_live_signals(
    store: LiveSignalStore,
    *,
    channel: LiveChannel | None = None,
    category: LiveSignalCategory | None = None,
    match_status: LiveMatchStatus | None = None,
    state: LiveAlertState | None = None,
    q: str | None = None,
    source_scope: str = "all",
    min_score: float | None = None,
    theme: str | None = None,
    entity: str | None = None,
    alerts_only: bool = False,
) -> list:
    all_signals = store.list_signals()
    candidates: list = []
    query = q.casefold() if q else None
    theme_query = theme.casefold() if theme else None
    entity_query = entity.casefold() if entity else None
    for signal in all_signals:
        if channel is not None and channel not in signal.channels:
            continue
        if category is not None and signal.category != category:
            continue
        if match_status is not None and signal.match_status != match_status:
            continue
        if query and query not in signal.title.casefold():
            continue
        candidates.append(signal)

    alerts_by_key = (
        {
            item.signal_key: item
            for item in store.list_alerts(limit=max(1, len(all_signals)))
        }
        if alerts_only or state is not None
        else {}
    )
    observations_by_id = {}
    if source_scope != "all":
        observation_ids = list(
            dict.fromkeys(
                observation_id
                for signal in candidates
                for observation_id in signal.observation_ids
            )
        )
        observations_by_id = {
            item.id: item
            for item in _observations_by_ids_batched(store, observation_ids)
        }
    assessments_by_signal_id = (
        {
            item.signal_version_id: item
            for item in store.list_assessments()
        }
        if min_score is not None or theme_query or entity_query
        else {}
    )

    signals: list = []
    for signal in candidates:
        alert = alerts_by_key.get(signal.signal_key)
        if alerts_only and alert is None:
            continue
        if state is not None and (alert is None or alert.state != state):
            continue
        if source_scope != "all":
            record_scope = _live_source_scope([
                observations_by_id[item_id]
                for item_id in signal.observation_ids
                if item_id in observations_by_id
            ])
            if source_scope == "formal" and record_scope == "fixture":
                continue
            if source_scope != "formal" and record_scope != source_scope:
                continue
        assessment = assessments_by_signal_id.get(signal.id)
        if min_score is not None and (
            assessment is None or assessment.total_score < min_score
        ):
            continue
        if theme_query and (
            assessment is None
            or not any(
                theme_query in value.casefold()
                for value in assessment.matched_themes
            )
        ):
            continue
        if entity_query and (
            assessment is None
            or not any(
                entity_query in value.casefold()
                for value in assessment.matched_entities
            )
        ):
            continue
        signals.append(signal)
    return signals


@app.get("/api/v1/live/status")
def live_gateway_status() -> dict[str, object]:
    runtime = get_live_runtime()
    status = runtime.status()
    alerts = runtime.store.list_alerts(
        states=[LiveAlertState.UNREAD],
        limit=1000,
    )
    coverage = calculate_live_coverage(
        runtime.store.list_signals(),
        runtime.store.list_observations(limit=5000),
    )
    return {
        **status,
        "unread_alerts": len(alerts),
        "coverage": coverage.model_dump(mode="json"),
        "latest_soak": (
            reports[0].model_dump(mode="json")
            if (reports := runtime.store.list_soak_reports(limit=1))
            else None
        ),
    }


@app.get("/api/v1/live/doctor")
def live_gateway_doctor() -> dict[str, object]:
    return build_live_diagnostics()


@app.get(
    "/api/v1/live/soak-reports",
    response_model=list[LiveSoakReport],
)
def list_live_soak_reports(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[LiveSoakReport]:
    return get_live_runtime().store.list_soak_reports(limit=limit)


@app.post("/api/v1/live/poll")
def poll_live_gateway(request: LivePollRequest) -> dict[str, object]:
    try:
        result = get_live_runtime().poll_once(request.stream)
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=502,
            detail=redact_provider_secrets(error),
        ) from error
    return {
        "stream": request.stream,
        "observations": len(result.batch.observations),
        "created_versions": result.created_versions,
        "duplicates": result.duplicate_observations,
        "checkpoint": result.batch.checkpoint.model_dump(mode="json"),
    }


@app.post("/api/v1/live/demo")
def replay_live_demo() -> dict[str, object]:
    runtime = get_live_runtime()
    results = [
        runtime.service.poll_source(feed)
        for feed in load_frozen_dual_channel_feeds()
    ]
    return {
        "fixture": "jin10-dual-channel-synthetic-v1",
        "notice": "Synthetic replay only; not current market data.",
        "channels": [
            {
                "channel": result.batch.descriptor.channel.value,
                "observations": len(result.batch.observations),
                "created_versions": result.created_versions,
            }
            for result in results
        ],
    }


@app.post("/api/v1/live/monitor/start")
def start_live_gateway() -> dict[str, object]:
    return get_live_runtime().start()


@app.post("/api/v1/live/monitor/stop")
def stop_live_gateway() -> dict[str, object]:
    return get_live_runtime().stop()


@app.get("/api/v1/live/events")
def list_live_events(
    channel: LiveChannel | None = None,
    category: LiveSignalCategory | None = None,
    match_status: LiveMatchStatus | None = None,
    state: LiveAlertState | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, object]]:
    store = get_live_runtime().store
    signals = _filtered_live_signals(
        store,
        channel=channel,
        category=category,
        match_status=match_status,
        state=state,
        q=q,
    )
    return _live_event_records(store, signals[:limit])


@app.get("/api/v1/live/events/page")
def page_live_events(
    channel: LiveChannel | None = None,
    category: LiveSignalCategory | None = None,
    match_status: LiveMatchStatus | None = None,
    state: LiveAlertState | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    source_scope: Annotated[
        str,
        Query(pattern=r"^(all|formal|live|fixture|mixed)$"),
    ] = "all",
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    theme: Annotated[str | None, Query(max_length=120)] = None,
    entity: Annotated[str | None, Query(max_length=120)] = None,
    alerts_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    store = get_live_runtime().store
    signals = _filtered_live_signals(
        store,
        channel=channel,
        category=category,
        match_status=match_status,
        state=state,
        q=q,
        source_scope=source_scope,
        min_score=min_score,
        theme=theme,
        entity=entity,
        alerts_only=alerts_only,
    )
    total = len(signals)
    items = _live_event_records(store, signals[offset : offset + limit])
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


@app.get("/api/v1/live/events/{signal_reference}")
def get_live_event(signal_reference: str) -> dict[str, object]:
    store = get_live_runtime().store
    signal = store.get_signal(signal_reference) or store.latest_signal(signal_reference)
    if signal is None:
        raise HTTPException(status_code=404, detail="Live signal not found.")
    return _live_event_record(store, signal)


@app.get("/api/v1/live/coverage")
def get_live_coverage() -> dict[str, object]:
    store = get_live_runtime().store
    return calculate_live_coverage(
        store.list_signals(),
        store.list_observations(limit=5000),
    ).model_dump(mode="json")


@app.get("/api/v1/live/settings", response_model=LiveDeskSettings)
def get_live_settings() -> LiveDeskSettings:
    return get_live_runtime().store.get_settings()


@app.get("/api/v1/live/settings/schema")
def get_live_settings_schema() -> dict[str, object]:
    schema = LiveDeskSettings.model_json_schema()
    schema["credential_notice"] = (
        "Provider credentials are backend-only environment variables and are never "
        "accepted or returned by this endpoint."
    )
    return schema


@app.patch("/api/v1/live/settings", response_model=LiveDeskSettings)
def patch_live_settings(request: LiveSettingsPatch) -> LiveDeskSettings:
    runtime = get_live_runtime()
    current = runtime.store.get_settings()
    updates = request.model_dump(exclude_none=True, mode="json")
    updates["updated_at"] = datetime.now(UTC)
    try:
        updated = LiveDeskSettings.model_validate(
            {**current.model_dump(mode="json"), **updates}
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    was_running = runtime.running
    if was_running:
        runtime.stop()
    runtime.store.save_settings(updated)
    if was_running:
        runtime.start()
    return updated


@app.post("/api/v1/live/events/{signal_reference}/analyze")
def analyze_live_event(
    signal_reference: str,
    request: LiveAnalyzeRequest,
) -> dict[str, object]:
    store = get_live_runtime().store
    signal = store.get_signal(signal_reference) or store.latest_signal(signal_reference)
    if signal is None:
        raise HTTPException(status_code=404, detail="Live signal not found.")
    model = None
    if request.provider not in {None, ProviderName.FIXTURE}:
        try:
            model = create_research_model(
                request.provider,
                subject=signal.title,
                mode="catalyst",
            )
        except (ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=409,
                detail=redact_provider_secrets(error),
            ) from error
    try:
        proposal, analysis = LiveImpactAnalyzer(store).analyze(
            signal.signal_key,
            model=model,
            force_model=request.force_model,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=409,
            detail=redact_provider_secrets(error),
        ) from error
    return {
        "proposal": proposal.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
    }


@app.get(
    "/api/v1/live/verification-tasks",
    response_model=list[LiveVerificationTaskRecord],
)
def list_live_verification_tasks(
    signal_key: Annotated[str | None, Query(max_length=200)] = None,
    run_id: Annotated[str | None, Query(max_length=160)] = None,
    status: Annotated[LiveVerificationTaskStatus | None, Query()] = None,
) -> list[LiveVerificationTaskRecord]:
    bridge = _live_bridge()
    tasks = bridge.store.list_verification_tasks(
        signal_key=signal_key,
        run_id=run_id,
        statuses=[status] if status else None,
    )
    return [_live_task_record(bridge, task) for task in tasks]


@app.get(
    "/api/v1/live/verification-tasks/{task_id}",
    response_model=LiveVerificationTaskRecord,
)
def get_live_verification_task(task_id: str) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    task = bridge.store.get_verification_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Verification task not found.")
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/events/{signal_reference}/verify",
    response_model=LiveVerificationTaskRecord,
)
def verify_live_event(
    signal_reference: str,
    request: LiveVerifyRequest,
) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    try:
        task = bridge.create_verification_task(
            signal_reference,
            run_id=request.run_id,
            query=request.query,
            note=request.note,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/verification-tasks/{task_id}/sources",
    response_model=LiveVerificationTaskRecord,
)
def add_live_verification_source(
    task_id: str,
    request: LiveOfficialSourceRequest,
) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    try:
        task = bridge.add_official_source(
            task_id,
            run_id=request.run_id,
            url=str(request.url),
            title=request.title,
            kind=request.kind,
            publisher=request.publisher,
            published_at=request.published_at,
            issuer_domains=tuple(request.issuer_domains),
            reason=request.reason,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/verification-tasks/{task_id}/capture",
    response_model=LiveVerificationTaskRecord,
)
def capture_live_verification_source(
    task_id: str,
    request: LiveCaptureTaskRequest,
) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    try:
        task = bridge.capture_task_source(
            task_id,
            retry=request.retry,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/verification-tasks/{task_id}/review",
    response_model=LiveVerificationTaskRecord,
)
def review_live_verification_evidence(
    task_id: str,
    request: LiveTaskReviewRequest,
) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    try:
        task = bridge.review_task_evidence(
            task_id,
            approved=request.approved,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/verification-tasks/{task_id}/attach",
    response_model=LiveVerificationTaskRecord,
)
def attach_live_verification_evidence(
    task_id: str,
    request: LiveConfirmationRequest,
) -> LiveVerificationTaskRecord:
    bridge = _live_bridge()
    try:
        task = bridge.attach_reviewed_evidence(
            task_id,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _live_task_record(bridge, task)


@app.post(
    "/api/v1/live/events/{signal_reference}/runs",
    response_model=LiveLinkedRunResponse,
)
def create_live_linked_run(
    signal_reference: str,
    request: LiveLinkedRunRequest,
) -> LiveLinkedRunResponse:
    bridge = _live_bridge()
    try:
        run, link = bridge.create_linked_run(
            signal_reference,
            parent_run_id=request.parent_run_id,
            mode=request.mode,
            subject=request.subject,
            market=request.market,
            as_of_date=request.as_of_date,
            evidence_mode=request.evidence_mode,
            model_provider=request.provider.value if request.provider else None,
            note=request.note,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return LiveLinkedRunResponse(run=run, link=link)


@app.post(
    "/api/v1/live/events/{signal_reference}/reevaluate",
    response_model=LiveLinkedRunResponse,
)
def create_live_reevaluation_run(
    signal_reference: str,
    request: LiveLinkedRunRequest,
) -> LiveLinkedRunResponse:
    if not request.parent_run_id:
        raise HTTPException(
            status_code=422,
            detail="Linked re-evaluation requires parent_run_id.",
        )
    return create_live_linked_run(signal_reference, request)


@app.post(
    "/api/v1/runs/{run_id}/live-context",
    response_model=LiveRunContextLink,
)
def attach_live_context_to_run(
    run_id: str,
    request: LiveRunContextRequest,
) -> LiveRunContextLink:
    bridge = _live_bridge()
    try:
        return bridge.link_run_context(
            run_id,
            request.signal_reference,
            include_observations=request.include_observations,
            include_analysis=request.include_analysis,
            include_proposal=request.include_proposal,
            note=request.note,
            confirmed=request.confirmed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/api/v1/runs/{run_id}/live-context",
    response_model=list[LiveRunContextLink],
)
def list_run_live_context(run_id: str) -> list[LiveRunContextLink]:
    if load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return _live_bridge().store.list_run_context_links(run_id=run_id)


@app.get(
    "/api/v1/live/events/{signal_reference}/audit",
    response_model=list[LiveAuditEntry],
)
def get_live_event_audit(signal_reference: str) -> list[LiveAuditEntry]:
    try:
        return _live_bridge().audit_timeline(signal_reference)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/v1/live/events/{signal_reference}/actions")
def act_on_live_event(
    signal_reference: str,
    request: LiveActionRequest,
) -> dict[str, object]:
    store = get_live_runtime().store
    signal = store.get_signal(signal_reference) or store.latest_signal(signal_reference)
    if signal is None:
        raise HTTPException(status_code=404, detail="Live signal not found.")
    if request.action in {
        ResearchAction.ATTACH,
        ResearchAction.LINKED_REEVALUATION,
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Use the M7 verification-task or linked-run endpoints so Evidence review, "
                "explicit confirmation, immutable context, and audit lineage are enforced."
            ),
        )
    now = datetime.now(UTC)
    action_id = hashlib.sha256(
        f"{signal.signal_key}:{request.action.value}:{now.isoformat()}".encode()
    ).hexdigest()[:24]
    action = store.save_user_action(
        LiveUserAction(
            id=f"live-action-{action_id}",
            signal_key=signal.signal_key,
            action=request.action,
            note=request.note,
            created_at=now,
        )
    )
    alert = store.get_alert(signal.signal_key)
    if alert is not None:
        state = {
            ResearchAction.DISMISS: LiveAlertState.DISMISSED,
            ResearchAction.IGNORE: LiveAlertState.DISMISSED,
            ResearchAction.MUTE: LiveAlertState.MUTED,
            ResearchAction.READ: LiveAlertState.READ,
            ResearchAction.WATCH: LiveAlertState.READ,
            ResearchAction.VERIFY: LiveAlertState.READ,
        }.get(request.action)
        if state is not None:
            alert = store.update_alert_state(signal.signal_key, state)
    return {
        "action": action.model_dump(mode="json"),
        "alert": alert.model_dump(mode="json") if alert is not None else None,
    }


@app.get("/api/v1/live/stream")
async def stream_live_events(
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
    once: bool = False,
) -> StreamingResponse:
    header = request.headers.get("last-event-id", "").strip()
    if header.isdigit():
        after = max(after, int(header))
    store = get_live_runtime().store

    async def generate():
        cursor = after
        heartbeat = 0
        yield (
            "event: live.ready\n"
            f"data: {json.dumps({'connected_at': datetime.now(UTC).isoformat()})}\n\n"
        )
        while True:
            alerts = store.list_alerts(after_id=cursor, limit=100)
            for alert in alerts:
                cursor = alert.id or cursor
                signal = store.latest_signal(alert.signal_key)
                if signal is None:
                    continue
                payload = json.dumps(
                    _live_event_record(store, signal),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {cursor}\nevent: live.signal\ndata: {payload}\n\n"
            if once:
                break
            if await request.is_disconnected():
                break
            heartbeat += 1
            if heartbeat >= 15:
                heartbeat = 0
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
