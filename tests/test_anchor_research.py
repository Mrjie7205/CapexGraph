from __future__ import annotations

import json

import pytest

from capexgraph.domain import Confidence, RunMode, RunStatus
from capexgraph.providers import ProviderName
from capexgraph.research import build_executor_for_run
from capexgraph.workflows import create_run


def test_golden_anchor_scan_is_evidence_bound(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "兆易创新", "CN")

    completed = build_executor_for_run(run, provider=ProviderName.FIXTURE).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert completed.manifest["anchor_node_id"] == "company-gigadevice"
    assert completed.manifest["model_usage"]["calls"] == 7
    assert len(completed.nodes) == 4
    assert len(completed.edges) == 3
    assert len(completed.candidates) == 3
    assert any(edge.confidence == Confidence.LOW for edge in completed.edges)
    assert all(edge.relationship.value == "peer" for edge in completed.edges)

    for filename in (
        "graph.json",
        "evidence.json",
        "financials.json",
        "candidates.json",
        "decision.json",
    ):
        artifact = tmp_path / completed.id / filename
        assert artifact.is_file()
        json.loads(artifact.read_text(encoding="utf-8"))


def test_anchor_fixture_unknown_subject_is_checkpointed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "安集科技", "CN")
    failed = build_executor_for_run(
        run,
        provider=ProviderName.FIXTURE,
        max_attempts=1,
    ).execute(run.id)

    assert failed.status == RunStatus.FAILED
    assert "Provider setup failed" in failed.pipeline[0].error


def test_anchor_execution_requires_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "兆易创新", "CN")
    with pytest.raises(ValueError, match="requires --provider"):
        build_executor_for_run(run)
