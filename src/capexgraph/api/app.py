from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from capexgraph import __version__
from capexgraph.domain import ResearchRun, RunMode, RunStatus, StepCheckpoint
from capexgraph.runtime import RunStore, WorkflowExecutor
from capexgraph.workflows import create_run, load_run

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


class ExecuteRequest(BaseModel):
    until: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=10)


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
def create_theme_run(request: RunRequest) -> ResearchRun:
    return create_run(RunMode.THEME, request.subject, request.market, request.as_of_date)


@app.post("/api/v1/runs/anchor", response_model=ResearchRun)
def create_anchor_run(request: RunRequest) -> ResearchRun:
    return create_run(RunMode.ANCHOR, request.subject, request.market, request.as_of_date)


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


@app.post("/api/v1/runs/{run_id}/execute", response_model=ResearchRun)
def execute_run(run_id: str, request: ExecuteRequest) -> ResearchRun:
    try:
        return WorkflowExecutor(max_attempts=request.max_attempts).execute(
            run_id,
            until=request.until,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/resume", response_model=ResearchRun)
def resume_run(run_id: str, request: ExecuteRequest) -> ResearchRun:
    try:
        return WorkflowExecutor(max_attempts=request.max_attempts).execute(
            run_id,
            until=request.until,
            retry_failed=True,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
