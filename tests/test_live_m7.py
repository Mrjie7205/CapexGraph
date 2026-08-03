from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from capexgraph.api.app import app
from capexgraph.cli import app as cli_app
from capexgraph.domain import (
    EvidenceKind,
    EvidenceStatus,
    LiveVerificationState,
    LiveVerificationTaskStatus,
    RunMode,
)
from capexgraph.live import (
    FrozenClock,
    LiveResearchBridge,
    LiveSignalService,
    LiveSignalStore,
    LiveSoakRunner,
    load_frozen_dual_channel_feeds,
)
from capexgraph.research.context import build_research_context
from capexgraph.tools.evidence import EvidenceCollector
from capexgraph.workflows import create_run, load_run


def _public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _official_collector() -> EvidenceCollector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                b"<html><body><h1>Official capacity update</h1>"
                b"<p>The issuer approved a reviewed capital expenditure plan.</p>"
                b"</body></html>"
            ),
            request=request,
        )

    return EvidenceCollector(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=_public_resolver,
    )


def _live_state(tmp_path: Path, monkeypatch):
    runs_dir = tmp_path / "runs"
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(db_path))
    store = LiveSignalStore(db_path)
    run = create_run(RunMode.THEME, "Memory capacity", "CN")
    clock = FrozenClock(datetime(2026, 7, 29, 2, 6, tzinfo=UTC))
    service = LiveSignalService(store)
    for feed in load_frozen_dual_channel_feeds(clock=clock):
        service.poll_source(feed)
    signal = next(
        item for item in store.list_signals() if "更新资本开支计划" in item.title
    )
    return store, run, signal


def test_migration_8_adds_research_bridge_tables(tmp_path: Path) -> None:
    store = LiveSignalStore(tmp_path / "bridge.db")
    with closing(sqlite3.connect(store.db_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 8
    assert {
        "live_verification_tasks",
        "live_evidence_links",
        "live_run_context_links",
        "live_audit_entries",
        "live_soak_reports",
    } <= tables


def test_official_source_review_links_evidence_and_keeps_signal_append_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, run, signal = _live_state(tmp_path, monkeypatch)
    bridge = LiveResearchBridge(store, evidence_collector=_official_collector())

    with pytest.raises(ValueError, match="explicit human confirmation"):
        bridge.create_verification_task(signal.id, confirmed=False)

    task = bridge.create_verification_task(
        signal.id,
        run_id=run.id,
        query="official issuer capacity announcement",
        note="Verify the capex claim.",
        confirmed=True,
    )
    assert task.status == LiveVerificationTaskStatus.PENDING
    assert store.latest_signal(signal.signal_key).verification_state == (
        LiveVerificationState.OFFICIAL_SOURCE_PENDING
    )
    assert len(store.list_signal_versions(signal.signal_key)) == signal.version + 1

    with pytest.raises(ValueError, match="recognized regulator"):
        bridge.add_official_source(
            task.id,
            run_id=run.id,
            url="https://news.example.net/story",
            title="Secondary report",
            kind=EvidenceKind.NEWS,
            confirmed=True,
        )

    task = bridge.add_official_source(
        task.id,
        run_id=run.id,
        url="https://investor.example.com/official-capex.html",
        title="Issuer official capacity update",
        kind=EvidenceKind.COMPANY_DISCLOSURE,
        publisher="Example Memory",
        issuer_domains=("example.com",),
        confirmed=True,
    )
    assert task.status == LiveVerificationTaskStatus.SOURCE_SUGGESTED

    task = bridge.capture_task_source(task.id, confirmed=True)
    assert task.status == LiveVerificationTaskStatus.CAPTURED
    assert task.evidence_id
    captured_run = load_run(run.id)
    assert captured_run is not None
    evidence = next(item for item in captured_run.evidence if item.id == task.evidence_id)
    assert evidence.status == EvidenceStatus.CAPTURED

    with pytest.raises(ValueError, match="human-reviewed"):
        bridge.attach_reviewed_evidence(task.id, confirmed=True)

    task = bridge.review_task_evidence(task.id, approved=True, confirmed=True)
    assert task.status == LiveVerificationTaskStatus.EVIDENCE_LINKED
    assert task.evidence_link_id
    linked = store.get_evidence_link(task.evidence_link_id)
    assert linked is not None
    assert linked.source_hash == evidence.source_hash
    assert store.latest_signal(signal.signal_key).verification_state == (
        LiveVerificationState.EVIDENCE_LINKED
    )
    assert store.latest_signal(signal.signal_key).version > signal.version

    parent_before = load_run(run.id)
    assert parent_before is not None
    parent_payload = parent_before.model_dump_json()
    child, context_link = bridge.create_linked_run(
        signal.signal_key,
        parent_run_id=run.id,
        note="Re-evaluate with the reviewed official source.",
        confirmed=True,
    )
    assert child.id != run.id
    assert context_link.parent_run_id == run.id
    assert load_run(run.id).model_dump_json() == parent_payload
    child_context = build_research_context(load_run(child.id))
    assert child_context["immutable_live_context"][0]["integrity"] == "verified"
    assert (
        child_context["immutable_live_context"][0]["context"]["trust"]["class"]
        == "secondary_live_signal"
    )
    assert child_context["immutable_live_context"][0]["context"][
        "reviewed_evidence_links"
    ]
    evidence_path = Path(evidence.local_path or "")
    if not evidence_path.is_absolute():
        evidence_path = tmp_path / "runs" / run.id / evidence_path
    evidence_path.write_text("tampered after review", encoding="utf-8")
    tampered_child, _ = bridge.create_linked_run(
        signal.signal_key,
        parent_run_id=run.id,
        note="Re-evaluate after the reviewed capture was changed.",
        confirmed=True,
    )
    tampered_context = build_research_context(load_run(tampered_child.id))[
        "immutable_live_context"
    ][0]["context"]
    assert tampered_context["reviewed_evidence_links"] == []
    assert tampered_context["excluded_evidence_link_ids"] == [linked.id]

    timeline = bridge.audit_timeline(signal.signal_key)
    event_types = {item.event_type for item in timeline}
    assert {
        "verification_task.created",
        "verification_task.source_suggested",
        "verification_task.source_captured",
        "verification_task.evidence_linked",
        "run.linked_reevaluation_created",
    } <= event_types


def test_rejected_capture_does_not_become_evidence_link(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, run, signal = _live_state(tmp_path, monkeypatch)
    bridge = LiveResearchBridge(store, evidence_collector=_official_collector())
    task = bridge.create_verification_task(
        signal.signal_key,
        run_id=run.id,
        confirmed=True,
    )
    task = bridge.add_official_source(
        task.id,
        run_id=run.id,
        url="https://investor.example.com/rejected.html",
        title="Issuer source requiring review",
        kind=EvidenceKind.COMPANY_DISCLOSURE,
        issuer_domains=("example.com",),
        confirmed=True,
    )
    task = bridge.capture_task_source(task.id, confirmed=True)
    rejected = bridge.review_task_evidence(task.id, approved=False, confirmed=True)

    assert rejected.status == LiveVerificationTaskStatus.REJECTED
    assert store.list_evidence_links(signal_key=signal.signal_key) == []
    assert store.latest_signal(signal.signal_key).verification_state == (
        LiveVerificationState.SIGNAL_ONLY
    )
    refreshed = load_run(run.id)
    assert refreshed is not None
    evidence = next(item for item in refreshed.evidence if item.id == task.evidence_id)
    assert evidence.status == EvidenceStatus.REJECTED


@pytest.mark.anyio
async def test_m7_api_requires_confirmation_and_exposes_linked_run_audit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(db_path))
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    parent = create_run(RunMode.ANCHOR, "Synthetic memory anchor", "CN")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        assert (await client.post("/api/v1/live/demo")).status_code == 200
        events = (await client.get("/api/v1/live/events")).json()
        signal_id = events[0]["signal"]["id"]

        blocked = await client.post(
            f"/api/v1/live/events/{signal_id}/verify",
            json={"run_id": parent.id},
        )
        assert blocked.status_code == 409
        assert "explicit human confirmation" in blocked.json()["detail"]

        opened = await client.post(
            f"/api/v1/live/events/{signal_id}/verify",
            json={"run_id": parent.id, "confirmed": True},
        )
        assert opened.status_code == 200
        assert opened.json()["task"]["status"] == "pending"

        linked = await client.post(
            f"/api/v1/live/events/{signal_id}/reevaluate",
            json={"parent_run_id": parent.id, "confirmed": True},
        )
        assert linked.status_code == 200
        assert linked.json()["link"]["parent_run_id"] == parent.id

        audit = await client.get(f"/api/v1/live/events/{signal_id}/audit")
        assert audit.status_code == 200
        assert any(
            item["event_type"] == "run.linked_reevaluation_created"
            for item in audit.json()
        )

        contexts = await client.get(
            f"/api/v1/runs/{linked.json()['run']['id']}/live-context"
        )
        assert contexts.status_code == 200
        assert contexts.json()[0]["context_hash"] == linked.json()["link"]["context_hash"]


def test_fixture_soak_exercises_replay_failure_isolation_and_recovery(
    tmp_path: Path,
) -> None:
    path = tmp_path / "soak.db"
    store = LiveSignalStore(path)
    report = LiveSoakRunner(path).run_fixture(cycles=4, failure_every=2)

    assert report.passed is True
    assert report.injected_failures == report.observed_failures == 1
    assert report.checkpoint_isolation_ok is True
    assert report.duplicates > 0
    assert "recovered=true" in report.notes
    assert store.list_signals() == []
    assert store.list_observations() == []
    assert store.list_soak_reports(limit=1)[0].id == report.id


def test_live_soak_cli_and_doctor_work_without_provider_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("JIN10_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("JIN10_WEBSOCKET_SECRET_KEY", raising=False)
    path = tmp_path / "soak-cli.db"
    runner = CliRunner()

    soak = runner.invoke(
        cli_app,
        [
            "live",
            "soak",
            "--cycles",
            "4",
            "--failure-every",
            "2",
            "--path",
            str(path),
        ],
    )
    doctor = runner.invoke(cli_app, ["live", "doctor", "--path", str(path)])
    providers = runner.invoke(
        cli_app,
        [
            "live",
            "soak",
            "--mode",
            "providers",
            "--cycles",
            "1",
            "--interval",
            "0",
            "--path",
            str(path),
        ],
    )

    assert soak.exit_code == 0
    assert '"passed": true' in soak.stdout
    assert doctor.exit_code == 0
    assert '"ready": true' in doctor.stdout
    assert "MCP live polling is not configured" in doctor.stdout
    assert providers.exit_code == 1
    assert "requires both equal-priority channels" in providers.stdout


@pytest.mark.anyio
async def test_live_diagnostics_and_soak_report_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "soak-api.db"
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(path))
    monkeypatch.delenv("JIN10_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("JIN10_WEBSOCKET_SECRET_KEY", raising=False)
    report = LiveSoakRunner(path).run_fixture(cycles=4, failure_every=2)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        diagnostics = await client.get("/api/v1/live/doctor")
        reports = await client.get("/api/v1/live/soak-reports")
        status = await client.get("/api/v1/live/status")

    assert diagnostics.status_code == 200
    assert diagnostics.json()["ready"] is True
    assert diagnostics.json()["configuration"]["websocket"]["configured"] is False
    assert reports.status_code == 200
    assert reports.json()[0]["id"] == report.id
    assert status.status_code == 200
    assert status.json()["latest_soak"]["passed"] is True
