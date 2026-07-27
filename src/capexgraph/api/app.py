import json
from datetime import date
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl

from capexgraph import __version__
from capexgraph.domain import (
    Evidence,
    EvidenceKind,
    FinancialMetric,
    MarketSnapshot,
    ResearchRun,
    RunMode,
    RunStatus,
    SourceSuggestion,
    SourceSuggestionStatus,
    StepCheckpoint,
    TickerIdentity,
)
from capexgraph.providers import ProviderName
from capexgraph.reporting import render_run_report
from capexgraph.research import build_executor_for_run
from capexgraph.runtime import RunStore
from capexgraph.runtime.store import runs_dir
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    market: str = Field(default="CN", min_length=2, max_length=12)
    as_of_date: date | None = None


class ThemeRunRequest(RunRequest):
    provider: ProviderName | None = None
    execute: bool = False
    max_attempts: int = Field(default=2, ge=1, le=10)


class ExecuteRequest(BaseModel):
    until: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=10)
    provider: ProviderName | None = None
    background: bool = False


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
    provider: str = Field(default="sec", pattern=r"^sec$")
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


class FinancialMetricsRequest(BaseModel):
    items: list[FinancialMetric] = Field(min_length=1, max_length=5000)


class TrackCandidateRequest(BaseModel):
    node_id: str = Field(min_length=1)
    benchmark_ticker: str = "000300.SH"
    call_date: date | None = None
    call_price: float | None = Field(default=None, gt=0)
    call_benchmark_price: float | None = Field(default=None, gt=0)
    capture_live: bool = True


class TrackingSnapshotRequest(BaseModel):
    as_of_date: date | None = None
    price: float | None = Field(default=None, gt=0)
    benchmark_price: float | None = Field(default=None, gt=0)
    capture_live: bool = False


class TrackingStageRequest(BaseModel):
    stage: TrackingStage


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
    run = create_run(RunMode.THEME, request.subject, request.market, request.as_of_date)
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
    run = create_run(RunMode.ANCHOR, request.subject, request.market, request.as_of_date)
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


@app.post("/api/v1/runs/{run_id}/sources/discover", response_model=list[SourceSuggestion])
def discover_run_sources(
    run_id: str,
    request: SourceDiscoverRequest,
) -> list[SourceSuggestion]:
    try:
        return SourceDiscoveryService().discover(
            run_id,
            identifier=request.identifier,
            forms=request.forms,
            limit=request.limit,
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
        return capture_market_snapshot(run_id, request.ticker)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, RuntimeError) as error:
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
            return service.capture_live_snapshot(tracked_id)
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
            current.manifest["background_error"] = f"{type(error).__name__}: {error}"
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
        if request.background:
            background_tasks.add_task(
                _background_execute,
                run_id,
                request.provider,
                request.max_attempts,
                request.until,
                False,
            )
            return run
        return build_executor_for_run(
            run,
            provider=request.provider,
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
        if request.background:
            background_tasks.add_task(
                _background_execute,
                run_id,
                request.provider,
                request.max_attempts,
                request.until,
                True,
            )
            return run
        return build_executor_for_run(
            run,
            provider=request.provider,
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
