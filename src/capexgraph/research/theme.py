from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from capexgraph.domain import (
    Candidate,
    Confidence,
    Evidence,
    PipelineStep,
    ResearchRun,
    RunMode,
    SupplyChainEdge,
    SupplyChainNode,
    Trigger,
)
from capexgraph.providers import EvidencePolicy, ProviderName, ResearchModel, create_research_model
from capexgraph.research.context import (
    apply_relationship_confidence_gate,
    build_research_context,
    enforce_evidence_preflight,
    evidence_is_reviewed_and_unchanged,
    refresh_evidence_coverage,
)
from capexgraph.research.theme_schemas import (
    BottleneckScoreOutput,
    DebateOutput,
    DecisionOutput,
    EvidenceAuditOutput,
    PlayerCensusOutput,
    ThemeBoundaryOutput,
    ThemeGraphOutput,
)
from capexgraph.runtime import WorkflowExecutor
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir

SYSTEM_PROMPT = """You are a specialist agent inside CapexGraph, an evidence-first
supply-chain research system. Return only the requested structured output. Separate facts from
inference, do not invent tickers, relationships, customers, dates, or sources, and expose missing
evidence. This is research for human review, not investment advice."""

ThemeHandler = Callable[[ResearchRun, PipelineStep], dict[str, Any]]


def _prompt(run: ResearchRun, task: str, context: dict[str, Any]) -> str:
    payload = {
        "task": task,
        "run": {
            "subject": run.subject,
            "market": run.market,
            "as_of_date": run.as_of_date.isoformat(),
        },
        "context": {
            **context,
            **build_research_context(run),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _record_output(run: ResearchRun, key: str, output: Any) -> None:
    outputs = run.manifest.setdefault("agent_outputs", {})
    outputs[key] = output.model_dump(mode="json")


def _write_run_artifact(run: ResearchRun, filename: str, payload: Any) -> None:
    atomic_write_json(runs_dir() / run.id / filename, payload)


def _merge_nodes(run: ResearchRun, proposals: list[Any]) -> None:
    nodes = {node.id: node for node in run.nodes}
    for proposal in proposals:
        node = SupplyChainNode(**proposal.model_dump())
        existing = nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"Conflicting node definition: {node.id}")
        nodes[node.id] = node
    run.nodes = list(nodes.values())


def _evidence_identity_matches(existing: Evidence, proposal: Any) -> bool:
    existing_url = str(existing.source_url).rstrip("/") if existing.source_url else None
    proposal_url = str(proposal.source_url).rstrip("/") if proposal.source_url else None
    return (
        existing.title == proposal.title
        and existing.kind == proposal.kind
        and existing_url == proposal_url
        and existing.published_at == proposal.published_at
    )


def _validate_graph(run: ResearchRun) -> None:
    node_ids = {node.id for node in run.nodes}
    evidence_ids = {item.id for item in run.evidence}
    if len(node_ids) != len(run.nodes):
        raise ValueError("Duplicate node IDs are not allowed")
    if len(evidence_ids) != len(run.evidence):
        raise ValueError("Duplicate evidence IDs are not allowed")

    edge_ids: set[str] = set()
    for edge in run.edges:
        if edge.id in edge_ids:
            raise ValueError(f"Duplicate edge ID: {edge.id}")
        edge_ids.add(edge.id)
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError(f"Edge {edge.id} references an unknown node")
        missing_evidence = set(edge.evidence_ids) - evidence_ids
        if missing_evidence:
            missing = ", ".join(sorted(missing_evidence))
            raise ValueError(f"Edge {edge.id} references missing evidence: {missing}")


def build_theme_handlers(model: ResearchModel) -> dict[str, ThemeHandler]:
    def intake(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        run.manifest.update(
            {
                "model_provider": model.provider_name,
                "model": model.model_name,
                "model_provider_details": {
                    "name": model.provider_name,
                    "version": getattr(model, "provider_version", "unknown"),
                    "model": model.model_name,
                },
                "evidence_policy": model.evidence_policy.value,
                "as_of_date": run.as_of_date.isoformat(),
                "report_language": (
                    "zh-CN"
                    if any("\u4e00" <= character <= "\u9fff" for character in run.subject)
                    else "en"
                ),
            }
        )
        enforce_evidence_preflight(
            run,
            curated=model.evidence_policy == EvidencePolicy.CURATED,
        )
        output = model.generate(
            ThemeBoundaryOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Define the research boundary and the decision-relevant questions.",
                {},
            ),
        )
        _record_output(run, "intake", output)
        return {"message": "Theme boundary defined", "scope": output.scope}

    def census(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            PlayerCensusOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Build a compact but decision-useful census of companies and industry segments.",
                {"boundary": run.manifest["agent_outputs"]["intake"]},
            ),
        )
        _merge_nodes(run, output.nodes)
        _record_output(run, "census", output)
        return {"message": "Player census built", "node_count": len(run.nodes)}

    def graph(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            ThemeGraphOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Map only supply-chain relationships supported by cited evidence. Unverified "
                "source suggestions are not proof and must remain low confidence. Reuse IDs from "
                "captured_evidence instead of redefining those evidence items.",
                {
                    "census": run.manifest["agent_outputs"]["census"],
                    "captured_evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        _merge_nodes(run, output.additional_nodes)

        evidence = {item.id: item for item in run.evidence}
        for proposal in output.evidence:
            item = Evidence(**proposal.model_dump())
            existing = evidence.get(item.id)
            if existing is not None and not _evidence_identity_matches(existing, proposal):
                raise ValueError(f"Conflicting evidence definition: {item.id}")
            if existing is None:
                evidence[item.id] = item
        run.evidence = list(evidence.values())

        edges: list[SupplyChainEdge] = []
        evidence_by_id = {item.id: item for item in run.evidence}
        for proposal in output.edges:
            payload = proposal.model_dump()
            payload["as_of_date"] = run.as_of_date
            reviewed_sources = bool(proposal.evidence_ids) and all(
                evidence_is_reviewed_and_unchanged(
                    run,
                    evidence_by_id.get(evidence_id),
                )
                for evidence_id in proposal.evidence_ids
            )
            gated_confidence, claim_is_grounded = apply_relationship_confidence_gate(
                run,
                requested_confidence=proposal.confidence.value,
                reviewed_sources=reviewed_sources,
                curated=model.evidence_policy == EvidencePolicy.CURATED,
                claim_label=f"relationship {proposal.id}",
            )
            payload["metadata"] = {
                "evidence_policy": model.evidence_policy.value,
                "verification_required": not claim_is_grounded,
                "reviewed_sources": reviewed_sources,
            }
            payload["confidence"] = gated_confidence
            edges.append(SupplyChainEdge(**payload))
        run.edges = edges
        _validate_graph(run)
        _record_output(run, "graph", output)
        _write_run_artifact(
            run,
            "graph.json",
            {
                "nodes": [node.model_dump(mode="json") for node in run.nodes],
                "edges": [edge.model_dump(mode="json") for edge in run.edges],
                "gaps": output.graph_gaps,
            },
        )
        _write_run_artifact(
            run,
            "evidence.json",
            {
                "policy": model.evidence_policy.value,
                "items": [item.model_dump(mode="json") for item in run.evidence],
            },
        )
        return {
            "message": "Grounded graph drafted",
            "edge_count": len(run.edges),
            "evidence_count": len(run.evidence),
        }

    def audit(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            EvidenceAuditOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Audit every graph edge. Reject unsupported claims and downgrade ambiguous claims.",
                {
                    "edges": [edge.model_dump(mode="json") for edge in run.edges],
                    "evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        findings = {finding.edge_id: finding for finding in output.findings}
        edge_ids = {edge.id for edge in run.edges}
        if set(findings) != edge_ids:
            missing = edge_ids - set(findings)
            unknown = set(findings) - edge_ids
            raise ValueError(
                "Audit must cover every edge "
                f"(missing={sorted(missing)}, unknown={sorted(unknown)})"
            )

        audited_edges: list[SupplyChainEdge] = []
        for edge in run.edges:
            finding = findings[edge.id]
            if finding.verdict == "reject":
                continue
            if finding.verdict == "downgrade":
                edge.confidence = Confidence.LOW
            edge.metadata["audit_verdict"] = finding.verdict
            edge.metadata["audit_rationale"] = finding.rationale
            audited_edges.append(edge)
        run.edges = audited_edges
        _validate_graph(run)
        _record_output(run, "audit", output)
        _write_run_artifact(
            run,
            "graph.json",
            {
                "nodes": [node.model_dump(mode="json") for node in run.nodes],
                "edges": [edge.model_dump(mode="json") for edge in run.edges],
                "audit": output.model_dump(mode="json"),
                "gaps": run.manifest["agent_outputs"]["graph"].get("graph_gaps", []),
            },
        )
        return {"message": "Evidence audit completed", "accepted_edges": len(run.edges)}

    def score(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            BottleneckScoreOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Identify bottleneck candidates. A candidate is a research priority, "
                "not a buy call.",
                {
                    "nodes": [node.model_dump(mode="json") for node in run.nodes],
                    "edges": [edge.model_dump(mode="json") for edge in run.edges],
                    "audit": run.manifest["agent_outputs"]["audit"],
                },
            ),
        )
        node_ids = {node.id for node in run.nodes}
        candidates: list[Candidate] = []
        for proposal in output.candidates:
            if proposal.node_id not in node_ids:
                raise ValueError(f"Candidate references unknown node: {proposal.node_id}")
            payload = proposal.model_dump(exclude={"triggers"})
            if model.evidence_policy != EvidencePolicy.CURATED:
                payload["confidence"] = Confidence.LOW
            payload["triggers"] = [Trigger(**item.model_dump()) for item in proposal.triggers]
            candidates.append(Candidate(**payload))
        run.candidates = candidates
        _record_output(run, "score", output)
        _write_run_artifact(
            run,
            "candidates.json",
            {
                "ranking_method": output.ranking_method,
                "data_gaps": output.data_gaps,
                "items": [item.model_dump(mode="json") for item in candidates],
            },
        )
        return {"message": "Bottleneck candidates scored", "candidate_count": len(candidates)}

    def debate(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            DebateOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Stress-test every candidate with a symmetric bull and bear review.",
                {"candidates": [item.model_dump(mode="json") for item in run.candidates]},
            ),
        )
        candidate_ids = {candidate.node_id for candidate in run.candidates}
        review_ids = {review.node_id for review in output.reviews}
        if review_ids != candidate_ids:
            raise ValueError("Debate must cover every candidate exactly once")
        _record_output(run, "debate", output)
        return {"message": "Bull / bear review completed", "review_count": len(output.reviews)}

    def decision(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = model.generate(
            DecisionOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Issue a research-manager decision for human review, preserving limitations.",
                {
                    "candidates": [item.model_dump(mode="json") for item in run.candidates],
                    "debate": run.manifest["agent_outputs"]["debate"],
                },
            ),
        )
        candidate_ids = {candidate.node_id for candidate in run.candidates}
        unknown = set(output.ranked_node_ids) - candidate_ids
        if unknown:
            raise ValueError(f"Decision ranks unknown candidates: {sorted(unknown)}")
        if len(output.ranked_node_ids) != len(set(output.ranked_node_ids)):
            raise ValueError("Decision ranking contains duplicate candidates")
        _record_output(run, "decision", output)
        refresh_evidence_coverage(run)
        _write_run_artifact(
            run,
            "decision.json",
            {
                **output.model_dump(mode="json"),
                "provider": model.provider_name,
                "model": model.model_name,
                "evidence_policy": model.evidence_policy.value,
                "disclaimer": (
                    "仅供研究和教育，不构成投资建议。"
                    if any("\u4e00" <= character <= "\u9fff" for character in run.subject)
                    else "Research and education only; not investment advice."
                ),
            },
        )
        return {"message": "Structured research decision issued", "status": output.research_status}

    return {
        "intake": intake,
        "census": census,
        "graph": graph,
        "audit": audit,
        "score": score,
        "debate": debate,
        "decision": decision,
    }


def build_executor_for_run(
    run: ResearchRun,
    *,
    provider: ProviderName | str | None = None,
    max_attempts: int = 2,
) -> WorkflowExecutor:
    """Rehydrate the correct agent handlers from the run manifest."""
    selected = provider or run.manifest.get("model_provider")
    if run.mode != RunMode.THEME:
        return WorkflowExecutor(max_attempts=max_attempts)
    if not selected:
        raise ValueError("Theme Scan execution requires --provider fixture or --provider openai")
    try:
        model = create_research_model(
            selected,
            subject=run.subject,
            mode="theme",
            model=os.getenv("CAPEXGRAPH_MODEL"),
        )
    except Exception as error:  # noqa: BLE001 - setup failures become durable checkpoints
        message = f"Provider setup failed: {type(error).__name__}: {error}"

        def fail_setup(
            _run: ResearchRun,
            _step: PipelineStep,
            *,
            detail: str = message,
        ) -> dict[str, Any]:
            raise RuntimeError(detail)

        return WorkflowExecutor(
            handlers={step.key: fail_setup for step in run.pipeline},
            max_attempts=max_attempts,
        )
    return WorkflowExecutor(
        handlers=build_theme_handlers(model),
        max_attempts=max_attempts,
    )
