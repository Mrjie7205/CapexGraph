from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from capexgraph.domain import Confidence, EvidenceMode, RunMode, RunStatus, StepStatus
from capexgraph.providers import EvidencePolicy, ProviderName
from capexgraph.providers.fixture import FixtureResearchModel
from capexgraph.providers.openai import OpenAIResearchModel
from capexgraph.research import build_executor_for_run, build_theme_handlers
from capexgraph.research.context import apply_relationship_confidence_gate
from capexgraph.research.theme_schemas import ThemeBoundaryOutput
from capexgraph.runtime import WorkflowExecutor
from capexgraph.workflows import create_run, load_run, save_run


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


def test_agent_reviewed_sources_cap_high_relationships_at_medium(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Enterprise AI", "CN")

    confidence, grounded = apply_relationship_confidence_gate(
        run,
        requested_confidence="high",
        human_reviewed_sources=False,
        agent_reviewed_sources=True,
        curated=False,
        claim_label="relationship edge-company-demand",
    )

    assert confidence == "medium"
    assert grounded is True


def test_live_theme_graph_runs_evidence_bootstrap_before_graph_model(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(
        RunMode.THEME,
        "Alphabet Q2 2026 AI capex transmission",
        "US",
    )

    class BootstrapAwareModel(FixtureResearchModel):
        provider_name = "test-live-model"
        model_name = "test-live-model-v1"
        evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

        def generate(self, output_model, *, system_prompt: str, user_prompt: str):
            if output_model.__name__ == "ThemeGraphOutput":
                current = load_run(run.id)
                assert current is not None
                assert current.manifest["evidence_bootstrap"]["status"] == "completed"
            return super().generate(
                output_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

    class RecordingBootstrap:
        def run(self, run_id: str):
            current = load_run(run_id)
            assert current is not None
            current.manifest["evidence_bootstrap"] = {
                "status": "completed",
                "phase": "completed",
                "attempt": 1,
                "accepted_sources": 1,
            }
            save_run(current)
            return SimpleNamespace(status="completed")

    model = BootstrapAwareModel(run.subject)
    executor = WorkflowExecutor(
        handlers=build_theme_handlers(
            model,
            evidence_bootstrap_factory=lambda _model: RecordingBootstrap(),
        )
    )

    paused = executor.execute(run.id, until="census")
    assert paused.pipeline[1].status == StepStatus.COMPLETED
    completed = executor.execute(run.id, until="graph")

    assert completed.pipeline[2].status == StepStatus.COMPLETED
    assert completed.manifest["evidence_bootstrap"]["status"] == "completed"


def test_live_theme_graph_preserves_durable_bootstrap_failure_state(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(
        RunMode.THEME,
        "Alphabet Q2 2026 AI capex transmission",
        "US",
    )
    model = FixtureResearchModel(run.subject)
    model.provider_name = "test-live-model"
    model.model_name = "test-live-model-v1"
    model.evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    class FailingBootstrap:
        def run(self, run_id: str):
            current = load_run(run_id)
            assert current is not None
            current.manifest["evidence_bootstrap"] = {
                "status": "failed",
                "phase": "reviewing_evidence",
                "attempt": 1,
                "accepted_sources": 0,
                "error": "No captured source passed independent Agent review.",
            }
            current.manifest["bootstrap_failure_marker"] = "durable"
            save_run(current)
            raise RuntimeError("bootstrap failed")

    executor = WorkflowExecutor(
        handlers=build_theme_handlers(
            model,
            evidence_bootstrap_factory=lambda _model: FailingBootstrap(),
        ),
        max_attempts=1,
    )

    executor.execute(run.id, until="census")
    failed = executor.execute(run.id, until="graph")

    assert failed.status == RunStatus.FAILED
    assert failed.pipeline[2].status == StepStatus.FAILED
    assert failed.manifest["evidence_bootstrap"]["status"] == "failed"
    assert failed.manifest["evidence_bootstrap"]["accepted_sources"] == 0
    assert failed.manifest["bootstrap_failure_marker"] == "durable"


def test_strict_live_theme_defers_initial_evidence_gate_to_automatic_graph_bootstrap(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(
        RunMode.THEME,
        "Alphabet Q2 2026 AI capex transmission",
        "US",
        evidence_mode=EvidenceMode.STRICT,
    )
    model = FixtureResearchModel(run.subject)
    model.provider_name = "openai"
    model.model_name = "test-openai-model"
    model.evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    paused = WorkflowExecutor(
        handlers=build_theme_handlers(
            model,
            evidence_bootstrap_factory=lambda _model: SimpleNamespace(),
        ),
        max_attempts=1,
    ).execute(run.id, until="census")

    assert paused.status == RunStatus.NEEDS_REVIEW
    assert paused.pipeline[0].status == StepStatus.COMPLETED
    assert paused.pipeline[1].status == StepStatus.COMPLETED
    assert paused.manifest["evidence_coverage"]["strict_ready"] is False


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
