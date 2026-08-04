from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from capexgraph.domain import (
    EvidenceReviewActor,
    EvidenceReviewRecord,
    ResearchRun,
    RunMode,
    SourceAuthority,
    SourceSuggestion,
    SourceSuggestionStatus,
    SupplyChainNode,
)
from capexgraph.providers import ResearchModel, redact_provider_secrets
from capexgraph.providers.sources import SourceDiscoveryProvider, build_source_provider
from capexgraph.research.context import (
    evidence_is_agent_reviewed_and_unchanged,
    refresh_evidence_coverage,
)
from capexgraph.research.model_runtime import record_model_call
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
from capexgraph.tools.evidence import (
    EvidenceCollector,
    read_run_evidence_text,
    review_run_evidence,
)
from capexgraph.tools.identity import canonical_ticker
from capexgraph.workflows import load_run, save_run

MAX_BOOTSTRAP_COMPANIES = 4
MAX_BOOTSTRAP_SOURCES = 4
MAX_REVIEW_TEXT_CHARACTERS = 6_000

BOOTSTRAP_SYSTEM_PROMPT = """You are an autonomous research worker inside CapexGraph.
Return only the requested structured output. Company names and tickers are discovery hypotheses
until deterministic official-source metadata verifies them. Prefer primary regulator or issuer
sources, expose uncertainty, and never invent a quotation. This is research, not investment
advice."""

REVIEW_SYSTEM_PROMPT = """You are the independent Evidence Review Agent inside CapexGraph.
Review captured official text independently from the discovery worker. Accept a source only when
the supplied text directly supports a company identity and a decision-useful product, deployment,
customer, order, revenue, or operating claim. Every supporting quote must be copied exactly from
the supplied text. Reject slogans, unrelated documents, and unsupported inference."""


class CompanyDiscoveryCandidate(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    market: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_keywords: list[str] = Field(min_length=1, max_length=8)


class CompanyDiscoveryPlan(BaseModel):
    companies: list[CompanyDiscoveryCandidate] = Field(
        min_length=1,
        max_length=MAX_BOOTSTRAP_COMPANIES,
    )
    selection_method: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class SelectedOfficialSource(BaseModel):
    suggestion_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class OfficialSourceSelection(BaseModel):
    sources: list[SelectedOfficialSource] = Field(
        min_length=1,
        max_length=MAX_BOOTSTRAP_SOURCES,
    )
    limitations: list[str] = Field(default_factory=list)


class AgentEvidenceReview(BaseModel):
    evidence_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    verdict: Literal["accept", "reject", "insufficient"]
    rationale: str = Field(min_length=1)
    supporting_quotes: list[str] = Field(default_factory=list, max_length=6)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_supporting_quotes(self) -> AgentEvidenceReview:
        if any(not quote.strip() for quote in self.supporting_quotes):
            raise ValueError("Agent supporting quotes cannot be blank")
        return self


class EvidenceReviewBatch(BaseModel):
    reviews: list[AgentEvidenceReview] = Field(min_length=1, max_length=MAX_BOOTSTRAP_SOURCES)
    review_summary: str = Field(min_length=1)


class EvidenceBootstrapState(BaseModel):
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    phase: str = "idle"
    attempt: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    provider: str | None = None
    model: str | None = None
    transport: str | None = None
    proposed_companies: int = 0
    discovered_sources: int = 0
    selected_sources: int = 0
    captured_sources: int = 0
    accepted_sources: int = 0
    rejected_sources: int = 0
    accepted_companies: list[dict[str, Any]] = Field(default_factory=list)
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str = ""


class EvidenceBootstrapError(RuntimeError):
    """The autonomous source bootstrap failed after durable state was written."""


def _prompt(run: ResearchRun, task: str, context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": task,
            "run": {
                "id": run.id,
                "subject": run.subject,
                "market": run.market,
                "as_of_date": run.as_of_date.isoformat(),
            },
            "context": context,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _provider_for_market(market: str) -> str:
    normalized = market.upper()
    if normalized == "CN":
        return "cninfo"
    if normalized == "US":
        return "sec"
    if normalized == "KR":
        return "kind"
    raise ValueError(f"Autonomous official-source discovery does not support market {market}")


def _review_text(text: str, keywords: list[str]) -> str:
    if len(text) <= MAX_REVIEW_TEXT_CHARACTERS:
        return text
    lowered = text.casefold()
    windows: list[str] = []
    seen: set[tuple[int, int]] = set()
    for keyword in keywords:
        needle = keyword.strip().casefold()
        if not needle:
            continue
        start = 0
        while len("\n\n".join(windows)) < MAX_REVIEW_TEXT_CHARACTERS:
            index = lowered.find(needle, start)
            if index < 0:
                break
            left = max(0, index - 500)
            right = min(len(text), index + len(needle) + 900)
            marker = (left, right)
            if marker not in seen:
                windows.append(text[left:right])
                seen.add(marker)
            start = index + len(needle)
    selected = "\n\n".join(windows)
    return (selected or text)[:MAX_REVIEW_TEXT_CHARACTERS]


class AutonomousEvidenceBootstrapService:
    def __init__(
        self,
        *,
        model: ResearchModel,
        source_service: SourceDiscoveryService | None = None,
        provider_factory: Callable[[str], SourceDiscoveryProvider] | None = None,
        collector: EvidenceCollector | None = None,
    ) -> None:
        self.model = model
        self.source_service = source_service or SourceDiscoveryService()
        self.provider_factory = provider_factory or build_source_provider
        self.collector = collector

    def _persist(self, run_id: str, state: EvidenceBootstrapState) -> ResearchRun:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        run.manifest["evidence_bootstrap"] = state.model_dump(mode="json")
        save_run(run)
        atomic_write_json(
            runs_dir() / run_id / "evidence-bootstrap.json",
            state.model_dump(mode="json"),
        )
        return run

    def _generate(
        self,
        run: ResearchRun,
        output_model: type[BaseModel],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> BaseModel:
        try:
            return self.model.generate(
                output_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        finally:
            current = load_run(run.id)
            if current is not None:
                record_model_call(current, self.model)
                save_run(current)

    @staticmethod
    def _candidate_ticker(candidate: CompanyDiscoveryCandidate, run: ResearchRun) -> str:
        if candidate.market.upper() != run.market.upper():
            raise ValueError(
                f"Candidate {candidate.id} market {candidate.market} does not match {run.market}"
            )
        ticker = canonical_ticker(candidate.ticker)
        if run.market == "CN" and not ticker.endswith((".SH", ".SZ", ".BJ")):
            raise ValueError(f"Candidate {candidate.id} has an invalid A-share ticker")
        return ticker

    @staticmethod
    def _suggestion_payload(
        suggestion: SourceSuggestion,
        *,
        company_id: str,
    ) -> dict[str, Any]:
        return {
            "id": suggestion.id,
            "company_id": company_id,
            "title": suggestion.title,
            "url": str(suggestion.url),
            "publisher": suggestion.publisher,
            "authority": suggestion.authority.value,
            "published_at": suggestion.published_at,
            "metadata": suggestion.metadata,
        }

    def run(self, run_id: str) -> EvidenceBootstrapState:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        if run.mode != RunMode.THEME:
            raise ValueError("Autonomous evidence bootstrap currently supports Theme Scan only")
        existing_payload = run.manifest.get("evidence_bootstrap")
        if isinstance(existing_payload, dict):
            existing = EvidenceBootstrapState.model_validate(existing_payload)
            if existing.status == "completed" and existing.accepted_sources > 0:
                accepted_ids = {
                    str(review.get("evidence_id"))
                    for review in existing.reviews
                    if review.get("accepted") and review.get("evidence_id")
                }
                accepted_evidence = [
                    item for item in run.evidence if item.id in accepted_ids
                ]
                if (
                    len(accepted_evidence) == existing.accepted_sources
                    and all(
                        evidence_is_agent_reviewed_and_unchanged(run, item)
                        for item in accepted_evidence
                    )
                ):
                    return existing
            attempt = existing.attempt + 1
        else:
            attempt = 1

        context = dict(getattr(self.model, "execution_context", {}) or {})
        state = EvidenceBootstrapState(
            status="running",
            phase="planning_companies",
            attempt=attempt,
            started_at=datetime.now(UTC),
            provider=self.model.provider_name,
            model=self.model.model_name,
            transport=str(context.get("transport") or "unknown"),
        )
        self._persist(run_id, state)

        try:
            plan_prompt = _prompt(
                run,
                "Propose a compact set of listed-company discovery hypotheses for "
                "official-source verification.",
                {
                    "boundary": run.manifest.get("agent_outputs", {}).get("intake", {}),
                    "census": run.manifest.get("agent_outputs", {}).get("census", {}),
                    "rules": {
                        "maximum_companies": MAX_BOOTSTRAP_COMPANIES,
                        "ticker_required": True,
                        "official_verification_required": True,
                    },
                },
            )
            plan = self._generate(
                run,
                CompanyDiscoveryPlan,
                system_prompt=BOOTSTRAP_SYSTEM_PROMPT,
                user_prompt=plan_prompt,
            )
            assert isinstance(plan, CompanyDiscoveryPlan)
            candidates = {item.id: item for item in plan.companies[:MAX_BOOTSTRAP_COMPANIES]}
            state.proposed_companies = len(candidates)
            state.warnings.extend(plan.limitations)
            state.phase = "discovering_official_sources"
            self._persist(run_id, state)

            provider_name = _provider_for_market(run.market)
            suggestions: dict[str, tuple[SourceSuggestion, CompanyDiscoveryCandidate]] = {}
            for candidate in candidates.values():
                ticker = self._candidate_ticker(candidate, run)
                provider = self.provider_factory(provider_name)
                try:
                    discovered = self.source_service.discover(
                        run_id,
                        provider=provider,
                        identifier=ticker,
                        limit=10,
                    )
                except Exception as error:  # noqa: BLE001 - continue with other hypotheses
                    state.warnings.append(
                        f"{candidate.id}: {type(error).__name__}: "
                        f"{redact_provider_secrets(error)}"
                    )
                    continue
                for suggestion in discovered:
                    official_ticker = canonical_ticker(
                        str(suggestion.metadata.get("ticker") or "")
                    )
                    if official_ticker != ticker:
                        state.warnings.append(
                            f"{candidate.id}: official ticker mismatch for {suggestion.id}"
                        )
                        continue
                    official_name = str(
                        suggestion.metadata.get("company_name") or ""
                    ).strip()
                    if not official_name:
                        state.warnings.append(
                            f"{candidate.id}: official company name missing for {suggestion.id}"
                        )
                        continue
                    if suggestion.authority not in {
                        SourceAuthority.REGULATOR,
                        SourceAuthority.ISSUER,
                    }:
                        continue
                    suggestions.setdefault(suggestion.id, (suggestion, candidate))

            state.discovered_sources = len(suggestions)
            if not suggestions:
                raise EvidenceBootstrapError(
                    "No ticker-matched, identity-complete official disclosures were discovered."
                )

            selection_prompt = _prompt(
                run,
                "Select the most decision-useful official disclosures for capture and "
                "independent review.",
                {
                    "source_suggestions": [
                        self._suggestion_payload(item, company_id=candidate.id)
                        for item, candidate in suggestions.values()
                    ],
                    "maximum_sources": MAX_BOOTSTRAP_SOURCES,
                },
            )
            selection = self._generate(
                run,
                OfficialSourceSelection,
                system_prompt=BOOTSTRAP_SYSTEM_PROMPT,
                user_prompt=selection_prompt,
            )
            assert isinstance(selection, OfficialSourceSelection)
            state.warnings.extend(selection.limitations)
            selected: list[tuple[SourceSuggestion, CompanyDiscoveryCandidate]] = []
            for item in selection.sources[:MAX_BOOTSTRAP_SOURCES]:
                matched = suggestions.get(item.suggestion_id)
                if matched is None or matched[1].id != item.company_id:
                    state.warnings.append(
                        f"Ignored invalid source selection {item.suggestion_id}."
                    )
                    continue
                if all(existing[0].id != matched[0].id for existing in selected):
                    selected.append(matched)
            state.selected_sources = len(selected)
            if not selected:
                raise EvidenceBootstrapError("The Agent selected no valid official sources.")

            state.phase = "capturing_sources"
            self._persist(run_id, state)
            captured: list[dict[str, Any]] = []
            source_by_evidence: dict[
                str,
                tuple[SourceSuggestion, CompanyDiscoveryCandidate, str],
            ] = {}
            for suggestion, candidate in selected:
                try:
                    saved = self.source_service.capture(
                        run_id,
                        suggestion.id,
                        collector=self.collector,
                        retry=suggestion.status
                        in {
                            SourceSuggestionStatus.CAPTURED,
                            SourceSuggestionStatus.DUPLICATE,
                        },
                    )
                except (SourceCaptureError, ValueError) as error:
                    state.warnings.append(
                        f"{suggestion.id}: {redact_provider_secrets(error)}"
                    )
                    continue
                if not saved.evidence_id:
                    continue
                text = read_run_evidence_text(run_id, saved.evidence_id)
                bounded_text = _review_text(text, candidate.evidence_keywords)
                captured.append(
                    {
                        "evidence_id": saved.evidence_id,
                        "company_id": candidate.id,
                        "company_ticker": canonical_ticker(candidate.ticker),
                        "title": saved.title,
                        "authority": saved.authority.value,
                        "published_at": saved.published_at,
                        "text": bounded_text,
                    }
                )
                source_by_evidence[saved.evidence_id] = (
                    saved,
                    candidate,
                    bounded_text,
                )
            state.captured_sources = len(captured)
            if not captured:
                raise EvidenceBootstrapError("No selected official source could be captured.")

            state.phase = "reviewing_evidence"
            self._persist(run_id, state)
            review_prompt = _prompt(
                run,
                "Independently review every captured source using exact quotations.",
                {"captured_sources": captured},
            )
            prompt_hash = hashlib.sha256(
                f"{REVIEW_SYSTEM_PROMPT}\n{review_prompt}".encode()
            ).hexdigest()
            batch = self._generate(
                run,
                EvidenceReviewBatch,
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=review_prompt,
            )
            assert isinstance(batch, EvidenceReviewBatch)

            accepted_company_ids: set[str] = set()
            state.reviews = []
            reviews_to_apply: list[AgentEvidenceReview] = []
            reviewed_evidence_ids: set[str] = set()
            for review in batch.reviews:
                matched = source_by_evidence.get(review.evidence_id)
                if matched is None or matched[1].id != review.company_id:
                    state.warnings.append(
                        f"Ignored review for unknown evidence {review.evidence_id}."
                    )
                    continue
                if review.evidence_id in reviewed_evidence_ids:
                    state.warnings.append(
                        f"Ignored duplicate review for evidence {review.evidence_id}."
                    )
                    continue
                reviewed_evidence_ids.add(review.evidence_id)
                reviews_to_apply.append(review)
            for evidence_id, (_suggestion, candidate, _text) in source_by_evidence.items():
                if evidence_id in reviewed_evidence_ids:
                    continue
                reviews_to_apply.append(
                    AgentEvidenceReview(
                        evidence_id=evidence_id,
                        company_id=candidate.id,
                        verdict="insufficient",
                        rationale=(
                            "The Evidence Review Agent omitted this captured source, "
                            "so deterministic completeness checks rejected it."
                        ),
                        warnings=["No Agent review was returned for this captured source."],
                    )
                )
                state.warnings.append(
                    f"{evidence_id}: missing Agent review was marked insufficient."
                )

            for review in reviews_to_apply:
                matched = source_by_evidence[review.evidence_id]
                suggestion, candidate, bounded_text = matched
                exact_quotes = bool(review.supporting_quotes) and all(
                    bool(quote.strip()) and quote in bounded_text
                    for quote in review.supporting_quotes
                )
                accepted = review.verdict == "accept" and exact_quotes
                if review.verdict == "accept" and not exact_quotes:
                    state.warnings.append(
                        f"{review.evidence_id}: Agent supplied an inexact quotation."
                    )
                current = load_run(run_id)
                if current is None:
                    raise KeyError(f"Research run not found: {run_id}")
                evidence = next(
                    item for item in current.evidence if item.id == review.evidence_id
                )
                if not evidence.source_hash:
                    raise EvidenceBootstrapError(
                        f"Captured evidence {evidence.id} has no source hash."
                    )
                record = EvidenceReviewRecord(
                    actor=EvidenceReviewActor.AGENT,
                    decision=(
                        "approved"
                        if accepted
                        else "rejected"
                        if review.verdict == "reject"
                        else "insufficient"
                    ),
                    reviewer="Evidence Review Agent",
                    provider=self.model.provider_name,
                    model=self.model.model_name,
                    transport=str(context.get("transport") or "unknown"),
                    source_hash=evidence.source_hash,
                    prompt_hash=prompt_hash,
                    rationale=review.rationale,
                    supporting_quotes=review.supporting_quotes if exact_quotes else [],
                    warnings=review.warnings,
                )
                review_run_evidence(
                    run_id,
                    review.evidence_id,
                    approved=accepted,
                    review=record,
                )
                state.reviews.append(
                    {
                        **review.model_dump(mode="json"),
                        "accepted": accepted,
                        "source_authority": suggestion.authority.value,
                    }
                )
                if accepted:
                    state.accepted_sources += 1
                    accepted_company_ids.add(candidate.id)
                else:
                    state.rejected_sources += 1

            if not state.accepted_sources:
                raise EvidenceBootstrapError(
                    "No captured source passed independent Agent review."
                )

            current = load_run(run_id)
            if current is None:
                raise KeyError(f"Research run not found: {run_id}")
            nodes = {node.id: node for node in current.nodes}
            accepted_companies: list[dict[str, Any]] = []
            for company_id in sorted(accepted_company_ids):
                candidate = candidates[company_id]
                company_sources = [
                    (suggestion, item)
                    for evidence_id, (suggestion, item, _text) in source_by_evidence.items()
                    if item.id == company_id
                    and any(
                        review["evidence_id"] == evidence_id and review["accepted"]
                        for review in state.reviews
                    )
                ]
                if not company_sources:
                    continue
                official = company_sources[0][0]
                ticker = canonical_ticker(str(official.metadata.get("ticker") or ""))
                label = str(official.metadata["company_name"]).strip()
                evidence_ids = [item[0].evidence_id for item in company_sources]
                node = SupplyChainNode(
                    id=f"company-{ticker.casefold().replace('.', '-')}",
                    label=label,
                    node_type="company",
                    ticker=ticker,
                    market=current.market,
                    layer=candidate.layer,
                    metadata={
                        "identity_source": official.provider,
                        "review_actor": "agent",
                        "supporting_evidence_ids": evidence_ids,
                        "selection_rationale": candidate.rationale,
                    },
                )
                nodes[node.id] = node
                accepted_companies.append(node.model_dump(mode="json"))
            current.nodes = list(nodes.values())
            state.accepted_companies = accepted_companies
            state.status = "completed"
            state.phase = "completed"
            state.completed_at = datetime.now(UTC)
            state.warnings.append(batch.review_summary)
            current.manifest["evidence_bootstrap"] = state.model_dump(mode="json")
            refresh_evidence_coverage(current)
            save_run(current)
            atomic_write_json(
                runs_dir() / run_id / "evidence-bootstrap.json",
                state.model_dump(mode="json"),
            )
            return state
        except Exception as error:
            state.status = "failed"
            state.completed_at = datetime.now(UTC)
            state.error = f"{type(error).__name__}: {redact_provider_secrets(error)}"
            self._persist(run_id, state)
            if isinstance(error, EvidenceBootstrapError):
                raise
            raise EvidenceBootstrapError(state.error) from error
