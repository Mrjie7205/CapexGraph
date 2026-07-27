from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from capexgraph.domain import EvidenceMode, EvidenceStatus, RunMode, RunStatus
from capexgraph.providers import EvidencePolicy
from capexgraph.providers.fixture import FixtureResearchModel
from capexgraph.research import build_theme_handlers
from capexgraph.research.context import (
    apply_relationship_confidence_gate,
    evaluate_evidence_coverage,
    evidence_is_reviewed_and_unchanged,
)
from capexgraph.runtime import WorkflowExecutor
from capexgraph.tools.evidence import (
    EvidenceCollector,
    EvidencePack,
    collect_evidence_pack,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metrics
from capexgraph.workflows import create_run, load_run

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "alphabet_q2_2026"
SUBJECT = "Alphabet 2026年Q2 AI资本开支传导"


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def frozen_source_handler(request: httpx.Request) -> httpx.Response:
    if "earnings-release.pdf" in request.url.path:
        text = """
        <html><body>
        <h1>Alphabet Announces Second Quarter 2026 Results</h1>
        <p>Revenues were $119,796 million and capital expenditures were $44,924 million.</p>
        </body></html>
        """
    else:
        text = """
        <html><body>
        <h1>Q2 2026 CEO remarks</h1>
        <p>Cloud backlog reached $514 billion and demand remains supply constrained.</p>
        </body></html>
        """
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=text,
        request=request,
    )


class RecordingLiveModel:
    provider_name = "frozen-live"
    provider_version = "1"
    model_name = "frozen-live-alphabet-v1"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    def __init__(self) -> None:
        self.fixture = FixtureResearchModel(SUBJECT)
        self.prompts: list[str] = []

    def generate(self, output_model, *, system_prompt: str, user_prompt: str):
        del system_prompt
        self.prompts.append(user_prompt)
        return self.fixture.generate(
            output_model,
            system_prompt="",
            user_prompt="",
        )


def _capture_review_and_attach_financials(run_id: str) -> None:
    pack = EvidencePack.model_validate_json(
        (CASE_DIR / "evidence_pack.json").read_text(encoding="utf-8")
    )
    collector = EvidenceCollector(
        client=httpx.Client(transport=httpx.MockTransport(frozen_source_handler)),
        resolver=public_resolver,
    )
    for document in collect_evidence_pack(run_id, pack, collector=collector):
        review_run_evidence(run_id, document.evidence.id, approved=True)
    attach_financial_metrics(run_id, CASE_DIR / "financial_metrics.csv")


def test_live_model_receives_reviewed_source_text_and_financial_context(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, SUBJECT, "US", "2026-07-22")
    _capture_review_and_attach_financials(run.id)
    model = RecordingLiveModel()

    completed = WorkflowExecutor(handlers=build_theme_handlers(model)).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert completed.manifest["model_provider_details"] == {
        "name": "frozen-live",
        "version": "1",
        "model": "frozen-live-alphabet-v1",
    }
    assert completed.manifest["evidence_coverage"]["reviewed"] == 2
    assert completed.manifest["evidence_coverage"]["strict_ready"] is True
    assert all(item.status == EvidenceStatus.REVIEWED for item in completed.evidence)
    assert all(edge.metadata["reviewed_sources"] is True for edge in completed.edges)
    combined_prompts = "\n".join(model.prompts)
    assert "Revenues were $119,796 million" in combined_prompts
    assert '"metric": "capital_expenditures"' in combined_prompts
    assert '"reviewed_and_captured_sources"' in combined_prompts
    assert (tmp_path / run.id / "coverage.json").is_file()


def test_strict_evidence_failure_checkpoints_then_resumes_after_review(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(
        RunMode.THEME,
        SUBJECT,
        "US",
        "2026-07-22",
        EvidenceMode.STRICT,
    )
    model = RecordingLiveModel()
    executor = WorkflowExecutor(handlers=build_theme_handlers(model), max_attempts=1)

    failed = executor.execute(run.id)

    assert failed.status == RunStatus.FAILED
    assert failed.pipeline[0].status.value == "failed"
    assert "Strict evidence mode requires" in failed.pipeline[0].error

    _capture_review_and_attach_financials(run.id)
    resumed = WorkflowExecutor(
        handlers=build_theme_handlers(model),
        max_attempts=1,
    ).execute(run.id, retry_failed=True)

    assert resumed.status == RunStatus.NEEDS_REVIEW
    assert all(edge.confidence.value == "high" for edge in resumed.edges)
    assert load_run(run.id).manifest["evidence_coverage"]["status"] == "reviewed"


def test_changed_reviewed_capture_cannot_ground_a_strict_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(
        RunMode.THEME,
        SUBJECT,
        "US",
        "2026-07-22",
        EvidenceMode.STRICT,
    )
    _capture_review_and_attach_financials(run.id)
    current = load_run(run.id)
    assert current is not None
    changed = current.evidence[0]
    (tmp_path / run.id / str(changed.local_path)).write_text("changed", encoding="utf-8")

    assert evidence_is_reviewed_and_unchanged(current, changed) is False
    assert evaluate_evidence_coverage(current).hash_mismatches == 1
    with pytest.raises(ValueError, match="requires reviewed evidence"):
        apply_relationship_confidence_gate(
            current,
            requested_confidence="high",
            reviewed_sources=False,
            curated=False,
            claim_label="changed-source relationship",
        )
