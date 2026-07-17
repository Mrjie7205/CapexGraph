from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from capexgraph import __version__
from capexgraph.domain import PipelineStep, ResearchRun, RunMode
from capexgraph.runtime.artifacts import atomic_write_text
from capexgraph.runtime.store import RunStore, runs_dir

PIPELINES: dict[RunMode, list[tuple[str, str, str]]] = {
    RunMode.THEME: [
        ("intake", "Define theme boundary", "Theme Analyst"),
        ("census", "Build player census", "Universe Analyst"),
        ("graph", "Map grounded supply chain", "Chain Mapper"),
        ("audit", "Audit evidence", "Evidence Auditor"),
        ("score", "Score bottlenecks", "Bottleneck Analyst"),
        ("debate", "Bull / bear review", "Research Team"),
        ("decision", "Issue structured verdict", "Research Manager"),
    ],
    RunMode.ANCHOR: [
        ("intake", "Resolve anchor identity", "Anchor Analyst"),
        ("cause", "Explain anchor repricing", "Market Analyst"),
        ("graph", "Map 360° neighbours", "Chain Mapper"),
        ("audit", "Audit relationship evidence", "Evidence Auditor"),
        ("compare", "Compare neighbour fundamentals", "Financial Analyst"),
        ("debate", "Bull / bear review", "Research Team"),
        ("decision", "Issue structured verdict", "Research Manager"),
    ],
    RunMode.CATALYST: [
        ("intake", "Define catalyst and timeline", "Catalyst Analyst"),
        ("graph", "Map transmission paths", "Chain Mapper"),
        ("audit", "Audit event evidence", "Evidence Auditor"),
        ("decision", "Issue scenario verdict", "Research Manager"),
    ],
}


def create_run(
    mode: RunMode,
    subject: str,
    market: str,
    as_of_date: date | None = None,
) -> ResearchRun:
    now = datetime.now(UTC)
    run_id = f"{now:%Y%m%d}-{mode.value}-{uuid4().hex[:8]}"
    steps = [
        PipelineStep(
            key=key,
            label=label,
            agent=agent,
            message="Awaiting execution",
        )
        for key, label, agent in PIPELINES[mode]
    ]
    run = ResearchRun(
        id=run_id,
        mode=mode,
        subject=subject.strip(),
        market=market.upper().strip(),
        as_of_date=as_of_date or date.today(),
        pipeline=steps,
        manifest={
            "capexgraph_version": __version__,
            "schema_version": "1",
            "model_provider": None,
            "data_providers": [],
        },
    )
    return save_run(run)


def save_run(run: ResearchRun) -> ResearchRun:
    RunStore().save_run(run)
    run_dir = runs_dir() / run.id
    payload = run.model_dump_json(indent=2)
    atomic_write_text(run_dir / "state.json", payload)
    atomic_write_text(
        run_dir / "manifest.json",
        ResearchRun.model_validate_json(payload).model_dump_json(
            indent=2,
            include={"id", "mode", "subject", "market", "as_of_date", "created_at", "manifest"},
        ),
    )
    return run


def load_run(run_id: str) -> ResearchRun | None:
    if not run_id or any(char in run_id for char in ("/", "\\", "..")):
        return None
    stored = RunStore().load_run(run_id)
    if stored is not None:
        return stored
    path = runs_dir() / run_id / "state.json"
    if not path.is_file():
        return None
    run = ResearchRun.model_validate_json(path.read_text(encoding="utf-8"))
    RunStore().save_run(run)
    return run
