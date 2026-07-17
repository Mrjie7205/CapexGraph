import json
from datetime import date
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    StepCheckpoint,
    TickerIdentity,
)
from capexgraph.providers import ProviderName
from capexgraph.research import build_executor_for_run
from capexgraph.runtime import RunStore
from capexgraph.runtime.store import runs_dir
from capexgraph.tools import (
    EvidenceSourceRequest,
    TickerResolver,
    capture_market_snapshot,
    collect_evidence_for_run,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metric_items
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


class MarketCaptureRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=80)


class FinancialMetricsRequest(BaseModel):
    items: list[FinancialMetric] = Field(min_length=1, max_length=5000)


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "name": "CapexGraph", "version": __version__}


@app.get("/api/v1/meta")
def meta() -> dict[str, object]:
    return {
        "name": "CapexGraph",
        "version": __version__,
        "status": "pre-alpha",
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
