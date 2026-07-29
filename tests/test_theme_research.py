from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from capexgraph.domain import Confidence, RunMode, RunStatus
from capexgraph.providers import EvidencePolicy, ProviderName
from capexgraph.providers.fixture import FixtureResearchModel
from capexgraph.providers.openai import OpenAIResearchModel
from capexgraph.research import build_executor_for_run, build_theme_handlers
from capexgraph.research.theme_schemas import ThemeBoundaryOutput
from capexgraph.runtime import WorkflowExecutor
from capexgraph.workflows import create_run


def test_golden_theme_scan_produces_auditable_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "A股半导体硅片", "CN")

    completed = build_executor_for_run(run, provider=ProviderName.FIXTURE).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert completed.manifest["model_provider"] == "fixture"
    assert completed.manifest["evidence_policy"] == "curated"
    assert completed.manifest["model_provider_locked"] is True
    assert completed.manifest["model_usage"]["calls"] == 7
    assert completed.manifest["model_provider_details"]["transport"] == "bundled_fixture"
    assert completed.manifest["model_provider_details"]["billing_mode"] == "none"
    assert len(completed.nodes) == 6
    assert len(completed.edges) == 4
    assert len(completed.evidence) == 4
    assert len(completed.candidates) == 4

    evidence_ids = {item.id for item in completed.evidence}
    assert all(set(edge.evidence_ids) <= evidence_ids for edge in completed.edges)
    assert all(edge.confidence == Confidence.HIGH for edge in completed.edges)

    for filename in ("graph.json", "evidence.json", "candidates.json", "decision.json"):
        artifact = tmp_path / completed.id / filename
        assert artifact.is_file()
        json.loads(artifact.read_text(encoding="utf-8"))

    decision = json.loads((tmp_path / completed.id / "decision.json").read_text("utf-8"))
    assert decision["research_status"] == "needs_review"
    assert decision["disclaimer"] == "仅供研究和教育，不构成投资建议。"
    manifest = json.loads((tmp_path / completed.id / "manifest.json").read_text("utf-8"))
    assert manifest["manifest"]["model"] == "golden-a-share-semiconductor-wafers-v1"


def test_fixture_provider_rejects_arbitrary_themes() -> None:
    with pytest.raises(ValueError, match="only supports"):
        FixtureResearchModel("人形机器人")


def test_theme_execution_requires_an_explicit_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "AI数据中心电力", "CN")

    with pytest.raises(ValueError, match="requires --provider"):
        build_executor_for_run(run)


def test_provider_setup_failure_is_checkpointed_for_retry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Unconfigured live subject", "US")

    failed = build_executor_for_run(
        run,
        provider=ProviderName.FIXTURE,
        max_attempts=1,
    ).execute(run.id)

    assert failed.status == RunStatus.FAILED
    assert failed.pipeline[0].status.value == "failed"
    assert "Provider setup failed" in failed.pipeline[0].error
    assert failed.pipeline[0].attempts == 1


def test_unverified_model_edges_and_candidates_are_downgraded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "A股半导体硅片", "CN")
    model = FixtureResearchModel(run.subject)
    model.provider_name = "test-model"
    model.model_name = "test-model-v1"
    model.evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    completed = WorkflowExecutor(handlers=build_theme_handlers(model)).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert all(edge.confidence == Confidence.LOW for edge in completed.edges)
    assert all(edge.metadata["verification_required"] is True for edge in completed.edges)
    assert all(candidate.confidence == Confidence.LOW for candidate in completed.candidates)


def test_openai_provider_uses_responses_parse_with_pydantic() -> None:
    expected = ThemeBoundaryOutput(
        scope="scope",
        investment_question="question",
        included_layers=[],
        excluded_topics=[],
        capex_drivers=[],
        research_questions=[],
    )

    class FakeResponses:
        def __init__(self) -> None:
            self.kwargs = None

        def parse(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_parsed=expected)

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    provider = OpenAIResearchModel(model="test-model", client=client)

    actual = provider.generate(
        ThemeBoundaryOutput,
        system_prompt="system",
        user_prompt="user",
    )

    assert actual == expected
    assert responses.kwargs["model"] == "test-model"
    assert responses.kwargs["text_format"] is ThemeBoundaryOutput
    assert responses.kwargs["input"][0]["role"] == "system"
