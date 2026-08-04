from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from capexgraph.domain import (
    EvidenceStatus,
    RunMode,
    SourceAuthority,
    SourceSuggestion,
    SourceSuggestionStatus,
)
from capexgraph.providers import EvidencePolicy
from capexgraph.research.evidence_bootstrap import (
    AgentEvidenceReview,
    AutonomousEvidenceBootstrapService,
    EvidenceBootstrapError,
)
from capexgraph.sources import SourceDiscoveryService
from capexgraph.tools.evidence import EvidenceCollector
from capexgraph.workflows import create_run, load_run, save_run


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class FakeBootstrapModel:
    provider_name = "test-model"
    provider_version = "1"
    model_name = "test-model-v1"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL
    execution_context = {
        "transport": "test_transport",
        "billing_mode": "none",
    }

    def __init__(self, *, fabricated_quote: bool = False) -> None:
        self.call_count = 0
        self.fabricated_quote = fabricated_quote

    def generate(self, output_model, *, system_prompt: str, user_prompt: str):
        del system_prompt
        self.call_count += 1
        payload = json.loads(user_prompt)
        if output_model.__name__ == "CompanyDiscoveryPlan":
            return output_model.model_validate(
                {
                    "companies": [
                        {
                            "id": "candidate-company-a",
                            "name": "Company A",
                            "ticker": "000001",
                            "market": "CN",
                            "layer": "enterprise_ai",
                            "rationale": "Official product evidence should be discoverable.",
                            "evidence_keywords": ["enterprise AI", "commercially deployed"],
                        }
                    ],
                    "selection_method": "Decision-useful company with a testable product claim.",
                    "limitations": [],
                }
            )
        if output_model.__name__ == "OfficialSourceSelection":
            suggestion = payload["context"]["source_suggestions"][0]
            return output_model.model_validate(
                {
                    "sources": [
                        {
                            "suggestion_id": suggestion["id"],
                            "company_id": suggestion["company_id"],
                            "rationale": "The official disclosure directly names the AI product.",
                        }
                    ],
                    "limitations": [],
                }
            )
        if output_model.__name__ == "EvidenceReviewBatch":
            evidence = payload["context"]["captured_sources"][0]
            quote = (
                "A fabricated quote"
                if self.fabricated_quote
                else "Company A commercially deployed its enterprise AI platform."
            )
            return output_model.model_validate(
                {
                    "reviews": [
                        {
                            "evidence_id": evidence["evidence_id"],
                            "company_id": evidence["company_id"],
                            "verdict": "accept",
                            "rationale": (
                                "The official disclosure supports product existence "
                                "and deployment."
                            ),
                            "supporting_quotes": [quote],
                            "warnings": ["Revenue contribution is not disclosed."],
                        }
                    ],
                    "review_summary": "One official source passed review.",
                }
            )
        raise AssertionError(f"Unexpected schema: {output_model.__name__}")


class FakeOfficialProvider:
    provider_name = "fake-cn-official"
    provider_version = "1"

    def discover(self, run, *, identifier=None, forms=(), limit=10):
        del forms, limit
        assert identifier == "000001.SZ"
        return [
            SourceSuggestion(
                id="source-company-a",
                run_id=run.id,
                title="Company A enterprise AI product deployment",
                url="https://official.example/company-a-ai",
                canonical_url="https://official.example/company-a-ai",
                kind="company_disclosure",
                publisher="Official exchange",
                authority=SourceAuthority.REGULATOR,
                reason="Official disclosure for 000001.SZ.",
                provider=self.provider_name,
                provider_version=self.provider_version,
                status=SourceSuggestionStatus.SUGGESTED,
                published_at="2026-07-31",
                discovered_at=datetime.now(UTC),
                metadata={
                    "ticker": "000001.SZ",
                    "company_name": "Company A",
                    "exchange": "SZSE",
                },
            )
        ]


class TwoSourceOfficialProvider(FakeOfficialProvider):
    def discover(self, run, *, identifier=None, forms=(), limit=10):
        first = super().discover(
            run,
            identifier=identifier,
            forms=forms,
            limit=limit,
        )[0]
        second = SourceSuggestion(
            id="source-company-a-orders",
            run_id=run.id,
            title="Company A enterprise AI orders",
            url="https://official.example/company-a-ai-orders",
            canonical_url="https://official.example/company-a-ai-orders",
            kind="company_disclosure",
            publisher="Official exchange",
            authority=SourceAuthority.REGULATOR,
            reason="Second official disclosure for 000001.SZ.",
            provider=self.provider_name,
            provider_version=self.provider_version,
            status=SourceSuggestionStatus.SUGGESTED,
            published_at="2026-08-01",
            discovered_at=datetime.now(UTC),
            metadata=dict(first.metadata),
        )
        return [first, second]


class IncompleteReviewModel(FakeBootstrapModel):
    def generate(self, output_model, *, system_prompt: str, user_prompt: str):
        if output_model.__name__ == "OfficialSourceSelection":
            self.call_count += 1
            payload = json.loads(user_prompt)
            return output_model.model_validate(
                {
                    "sources": [
                        {
                            "suggestion_id": suggestion["id"],
                            "company_id": suggestion["company_id"],
                            "rationale": "Capture every official source for review.",
                        }
                        for suggestion in payload["context"]["source_suggestions"]
                    ],
                    "limitations": [],
                }
            )
        return super().generate(
            output_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


def official_collector() -> EvidenceCollector:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><body><h1>Company A enterprise AI platform</h1>"
                "<p>Company A commercially deployed its enterprise AI platform.</p>"
                f"<p>Official source path: {request.url.path}</p>"
                "</body></html>"
            ),
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(respond)
    )
    return EvidenceCollector(client=client, resolver=public_resolver)


def prepared_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Enterprise AI", "CN")
    run.manifest["model_provider"] = "test-model"
    run.manifest["model"] = "test-model-v1"
    run.manifest["agent_outputs"] = {
        "intake": {
            "scope": "Enterprise AI software",
            "investment_question": "Which companies have commercial deployments?",
        },
        "census": {
            "nodes": [],
            "coverage_notes": ["No official evidence yet."],
            "unresolved_entities": ["Listed companies"],
        },
    }
    return save_run(run)


def test_bootstrap_discovers_captures_agent_reviews_and_adds_verified_company(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)
    result = AutonomousEvidenceBootstrapService(
        model=FakeBootstrapModel(),
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: FakeOfficialProvider(),
        collector=official_collector(),
    ).run(run.id)

    assert result.status == "completed"
    assert result.accepted_sources == 1
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert refreshed.evidence[0].status == EvidenceStatus.AGENT_REVIEWED
    assert refreshed.evidence[0].review is not None
    assert refreshed.evidence[0].review.supporting_quotes == [
        "Company A commercially deployed its enterprise AI platform."
    ]
    assert any(node.ticker == "000001.SZ" for node in refreshed.nodes)
    assert (tmp_path / run.id / "evidence-bootstrap.json").is_file()


def test_completed_bootstrap_recaptures_and_rereviews_tampered_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)
    model = FakeBootstrapModel()
    service = AutonomousEvidenceBootstrapService(
        model=model,
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: FakeOfficialProvider(),
        collector=official_collector(),
    )

    first = service.run(run.id)
    refreshed = load_run(run.id)
    assert refreshed is not None
    evidence = refreshed.evidence[0]
    assert evidence.local_path is not None
    (tmp_path / run.id / evidence.local_path).write_text(
        "tampered after review",
        encoding="utf-8",
    )

    second = service.run(run.id)

    assert second.status == "completed"
    assert second.attempt == first.attempt + 1
    assert model.call_count == 6
    repaired = load_run(run.id)
    assert repaired is not None
    assert len(repaired.evidence) == 1
    assert repaired.evidence[0].status == EvidenceStatus.AGENT_REVIEWED


def test_completed_bootstrap_recaptures_and_rereviews_tampered_extracted_text(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)
    model = FakeBootstrapModel()
    service = AutonomousEvidenceBootstrapService(
        model=model,
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: FakeOfficialProvider(),
        collector=official_collector(),
    )

    first = service.run(run.id)
    (tmp_path / run.id / "sources" / "source-company-a.txt").write_text(
        "fabricated extracted text",
        encoding="utf-8",
    )

    second = service.run(run.id)

    assert second.status == "completed"
    assert second.attempt == first.attempt + 1
    assert model.call_count == 6
    repaired_text = (
        tmp_path / run.id / "sources" / "source-company-a.txt"
    ).read_text(encoding="utf-8")
    assert "commercially deployed" in repaired_text


def test_bootstrap_marks_every_omitted_agent_review_as_insufficient(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)

    result = AutonomousEvidenceBootstrapService(
        model=IncompleteReviewModel(),
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: TwoSourceOfficialProvider(),
        collector=official_collector(),
    ).run(run.id)

    assert result.status == "completed"
    assert result.captured_sources == 2
    assert result.accepted_sources == 1
    assert result.rejected_sources == 1
    refreshed = load_run(run.id)
    assert refreshed is not None
    statuses = {item.id: item.status for item in refreshed.evidence}
    assert statuses["source-company-a"] == EvidenceStatus.AGENT_REVIEWED
    assert statuses["source-company-a-orders"] == EvidenceStatus.REJECTED
    assert any(
        review["evidence_id"] == "source-company-a-orders"
        and review["verdict"] == "insufficient"
        for review in result.reviews
    )


def test_bootstrap_rejects_fabricated_quote_and_persists_failure(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)

    with pytest.raises(EvidenceBootstrapError, match="No captured source passed"):
        AutonomousEvidenceBootstrapService(
            model=FakeBootstrapModel(fabricated_quote=True),
            source_service=SourceDiscoveryService(),
            provider_factory=lambda _name: FakeOfficialProvider(),
            collector=official_collector(),
        ).run(run.id)

    failed = load_run(run.id)
    assert failed is not None
    assert failed.manifest["evidence_bootstrap"]["status"] == "failed"
    assert failed.evidence[0].status == EvidenceStatus.REJECTED
    assert failed.evidence[0].review is not None
    assert failed.evidence[0].review.decision == "insufficient"
    assert failed.evidence[0].review.supporting_quotes == []


def test_completed_bootstrap_is_idempotent_while_hashes_match(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)
    model = FakeBootstrapModel()
    service = AutonomousEvidenceBootstrapService(
        model=model,
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: FakeOfficialProvider(),
        collector=official_collector(),
    )

    first = service.run(run.id)
    second = service.run(run.id)

    assert second == first
    assert model.call_count == 3
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert len(refreshed.evidence) == 1
    assert len([node for node in refreshed.nodes if node.ticker == "000001.SZ"]) == 1


def test_bootstrap_rejects_official_ticker_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)

    class MismatchedProvider(FakeOfficialProvider):
        def discover(self, run, *, identifier=None, forms=(), limit=10):
            suggestion = super().discover(
                run,
                identifier=identifier,
                forms=forms,
                limit=limit,
            )[0]
            suggestion.metadata["ticker"] = "000002.SZ"
            return [suggestion]

    with pytest.raises(EvidenceBootstrapError, match="No ticker-matched"):
        AutonomousEvidenceBootstrapService(
            model=FakeBootstrapModel(),
            source_service=SourceDiscoveryService(),
            provider_factory=lambda _name: MismatchedProvider(),
            collector=official_collector(),
        ).run(run.id)

    failed = load_run(run.id)
    assert failed is not None
    state = failed.manifest["evidence_bootstrap"]
    assert state["status"] == "failed"
    assert state["discovered_sources"] == 0


def test_bootstrap_rejects_official_identity_without_company_name(
    tmp_path,
    monkeypatch,
) -> None:
    run = prepared_run(tmp_path, monkeypatch)

    class MissingNameProvider(FakeOfficialProvider):
        def discover(self, run, *, identifier=None, forms=(), limit=10):
            suggestion = super().discover(
                run,
                identifier=identifier,
                forms=forms,
                limit=limit,
            )[0]
            suggestion.metadata.pop("company_name")
            return [suggestion]

    with pytest.raises(EvidenceBootstrapError, match="identity-complete"):
        AutonomousEvidenceBootstrapService(
            model=FakeBootstrapModel(),
            source_service=SourceDiscoveryService(),
            provider_factory=lambda _name: MissingNameProvider(),
            collector=official_collector(),
        ).run(run.id)

    failed = load_run(run.id)
    assert failed is not None
    assert failed.manifest["evidence_bootstrap"]["status"] == "failed"
    assert not any(node.ticker == "000001.SZ" for node in failed.nodes)


def test_agent_evidence_review_rejects_blank_supporting_quotes() -> None:
    with pytest.raises(ValueError, match="blank"):
        AgentEvidenceReview(
            evidence_id="source-company-a",
            company_id="candidate-company-a",
            verdict="accept",
            rationale="The source is relevant.",
            supporting_quotes=["   "],
        )
