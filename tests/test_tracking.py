from __future__ import annotations

from datetime import date

from capexgraph.domain import RunMode, Trigger
from capexgraph.providers import ProviderName
from capexgraph.reporting import render_run_report
from capexgraph.research import build_executor_for_run
from capexgraph.tracking import TrackingService, TrackingStage
from capexgraph.workflows import create_run, save_run


def _completed_theme_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "A股半导体硅片", "CN", date(2025, 4, 29))
    completed = build_executor_for_run(run, provider=ProviderName.FIXTURE).execute(run.id)
    completed.candidates[0].triggers = [
        Trigger(metric="alpha_pct", operator=">=", value=5, note="relative strength")
    ]
    return save_run(completed)


def test_tracking_scorecard_alpha_trigger_and_stage(tmp_path, monkeypatch) -> None:
    run = _completed_theme_run(tmp_path, monkeypatch)
    candidate = run.candidates[0]
    service = TrackingService()

    tracked = service.track_run_candidate(
        run.id,
        candidate.node_id,
        call_date=date(2025, 4, 29),
        call_price=100,
        call_benchmark_price=100,
        capture_live=False,
    )
    snapshot = service.add_snapshot(
        tracked.id,
        as_of_date=date(2025, 5, 29),
        price=112,
        benchmark_price=104,
    )

    assert snapshot.return_pct == 12
    assert snapshot.benchmark_return_pct == 4
    assert snapshot.alpha_pct == 8
    card = service.scorecard(tracked.id)
    assert card.snapshot_count == 2
    assert card.days_tracked == 30
    assert len(card.events) == 1
    assert card.events[0].metric == "alpha_pct"

    updated = service.store.update_stage(tracked.id, TrackingStage.VALIDATED)
    assert updated.stage == TrackingStage.VALIDATED
    board = service.stage_board()
    assert board["validated"][0].tracked.id == tracked.id

    acknowledged = service.store.acknowledge_event(card.events[0].id or 0)
    assert acknowledged.acknowledged_at is not None


def test_html_report_is_portable_and_escaped(tmp_path, monkeypatch) -> None:
    run = _completed_theme_run(tmp_path, monkeypatch)
    run.subject = "<script>alert('x')</script>"
    save_run(run)

    path = render_run_report(run.id)
    content = path.read_text(encoding="utf-8")

    assert path == (tmp_path / run.id / "report.html").resolve()
    assert "&lt;script&gt;" in content
    assert "<script>alert" not in content
    assert "仅供研究和教育" in content
