from __future__ import annotations

from typing import Any

from capexgraph.domain import (
    Candidate,
    Confidence,
    Evidence,
    PipelineStep,
    ResearchRun,
    SupplyChainEdge,
    Trigger,
)
from capexgraph.providers import EvidencePolicy, ResearchModel, create_research_model
from capexgraph.research.anchor_schemas import (
    AnchorGraphOutput,
    AnchorIdentityOutput,
    NeighbourComparisonOutput,
    RepricingCauseOutput,
)
from capexgraph.research.context import (
    apply_relationship_confidence_gate,
    enforce_evidence_preflight,
    evidence_is_reviewed_and_unchanged,
    refresh_evidence_coverage,
)
from capexgraph.research.model_runtime import (
    bind_model_identity,
    provider_setup_error,
    select_run_provider,
)
from capexgraph.research.theme import (
    SYSTEM_PROMPT,
    ThemeHandler,
    _evidence_identity_matches,
    _generate_model,
    _merge_nodes,
    _prompt,
    _record_output,
    _validate_graph,
    _write_run_artifact,
)
from capexgraph.research.theme_schemas import (
    DebateOutput,
    DecisionOutput,
    EvidenceAuditOutput,
)
from capexgraph.runtime import WorkflowExecutor


def _merge_evidence(run: ResearchRun, proposals: list[Any]) -> None:
    evidence = {item.id: item for item in run.evidence}
    for proposal in proposals:
        item = Evidence(**proposal.model_dump())
        existing = evidence.get(item.id)
        if existing is not None and not _evidence_identity_matches(existing, proposal):
            raise ValueError(f"Conflicting evidence definition: {item.id}")
        if existing is None:
            evidence[item.id] = item
    run.evidence = list(evidence.values())


def build_anchor_handlers(model: ResearchModel) -> dict[str, ThemeHandler]:
    def intake(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        bind_model_identity(run, model)
        enforce_evidence_preflight(
            run,
            curated=model.evidence_policy == EvidencePolicy.CURATED,
        )
        output = _generate_model(
            model,
            run,
            AnchorIdentityOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Resolve the anchor identity, product scope, and role without inventing aliases.",
                {},
            ),
        )
        _merge_nodes(run, [output.anchor])
        _merge_evidence(run, output.evidence)
        run.manifest["anchor_node_id"] = output.anchor.id
        _record_output(run, "intake", output)
        return {"message": "Anchor identity resolved", "anchor_node_id": output.anchor.id}

    def cause(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            RepricingCauseOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Explain disclosed repricing drivers. Separate operating facts "
                "from market inference.",
                {
                    "anchor": run.manifest["agent_outputs"]["intake"],
                    "captured_evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        _merge_evidence(run, output.evidence)
        evidence_ids = {item.id for item in run.evidence}
        for driver in output.drivers:
            missing = set(driver.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"Repricing driver references missing evidence: {sorted(missing)}")
        _record_output(run, "cause", output)
        return {
            "message": "Repricing causes separated from inference",
            "driver_count": len(output.drivers),
        }

    def graph(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            AnchorGraphOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Map direct neighbours and peers. Never convert product overlap "
                "into a customer claim.",
                {
                    "anchor": run.manifest["agent_outputs"]["intake"],
                    "cause": run.manifest["agent_outputs"]["cause"],
                    "captured_evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        _merge_nodes(run, output.neighbours)
        _merge_evidence(run, output.evidence)
        evidence_by_id = {item.id: item for item in run.evidence}
        edges: list[SupplyChainEdge] = []
        for proposal in output.edges:
            payload = proposal.model_dump()
            payload["as_of_date"] = run.as_of_date
            reviewed = bool(proposal.evidence_ids) and all(
                evidence_is_reviewed_and_unchanged(
                    run,
                    evidence_by_id.get(item_id),
                )
                for item_id in proposal.evidence_ids
            )
            gated_confidence, grounded = apply_relationship_confidence_gate(
                run,
                requested_confidence=proposal.confidence.value,
                reviewed_sources=reviewed,
                curated=model.evidence_policy == EvidencePolicy.CURATED,
                claim_label=f"relationship {proposal.id}",
            )
            payload["confidence"] = gated_confidence
            payload["metadata"] = {
                "evidence_policy": model.evidence_policy.value,
                "verification_required": not grounded,
                "reviewed_sources": reviewed,
            }
            edges.append(SupplyChainEdge(**payload))
        run.edges = edges
        _validate_graph(run)
        _record_output(run, "graph", output)
        _write_run_artifact(
            run,
            "graph.json",
            {
                "nodes": [item.model_dump(mode="json") for item in run.nodes],
                "edges": [item.model_dump(mode="json") for item in run.edges],
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
        return {"message": "Anchor neighbour graph drafted", "edge_count": len(run.edges)}

    def audit(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            EvidenceAuditOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Audit every relationship. Reject customer or supplier implications "
                "not directly disclosed.",
                {
                    "edges": [item.model_dump(mode="json") for item in run.edges],
                    "evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        findings = {item.edge_id: item for item in output.findings}
        if set(findings) != {item.id for item in run.edges}:
            raise ValueError("Audit must cover every edge exactly once")
        accepted: list[SupplyChainEdge] = []
        for edge in run.edges:
            finding = findings[edge.id]
            if finding.verdict == "reject":
                continue
            if finding.verdict == "downgrade":
                edge.confidence = Confidence.LOW
            edge.metadata.update(
                {"audit_verdict": finding.verdict, "audit_rationale": finding.rationale}
            )
            accepted.append(edge)
        run.edges = accepted
        _validate_graph(run)
        _record_output(run, "audit", output)
        _write_run_artifact(
            run,
            "graph.json",
            {
                "nodes": [item.model_dump(mode="json") for item in run.nodes],
                "edges": [item.model_dump(mode="json") for item in run.edges],
                "audit": output.model_dump(mode="json"),
                "gaps": run.manifest["agent_outputs"]["graph"].get("graph_gaps", []),
            },
        )
        return {"message": "Anchor relationship audit completed", "accepted_edges": len(run.edges)}

    def compare(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            NeighbourComparisonOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Compare neighbours on source-linked fundamentals and preserve "
                "every missing metric.",
                {
                    "nodes": [item.model_dump(mode="json") for item in run.nodes],
                    "edges": [item.model_dump(mode="json") for item in run.edges],
                    "evidence": [item.model_dump(mode="json") for item in run.evidence],
                },
            ),
        )
        node_ids = {item.id for item in run.nodes}
        evidence_ids = {item.id for item in run.evidence}
        for comparison in output.comparisons:
            if comparison.node_id not in node_ids:
                raise ValueError(
                    f"Financial comparison references unknown node: {comparison.node_id}"
                )
            if set(comparison.source_evidence_ids) - evidence_ids:
                raise ValueError(f"Financial comparison for {comparison.node_id} lacks evidence")
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
        _record_output(run, "compare", output)
        _write_run_artifact(run, "financials.json", output.model_dump(mode="json"))
        _write_run_artifact(
            run,
            "candidates.json",
            {
                "ranking_method": output.ranking_method,
                "data_gaps": output.data_gaps,
                "items": [item.model_dump(mode="json") for item in run.candidates],
            },
        )
        return {"message": "Neighbour fundamentals compared", "candidate_count": len(candidates)}

    def debate(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            DebateOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Stress-test every neighbour candidate with symmetric bull and bear cases.",
                {"candidates": [item.model_dump(mode="json") for item in run.candidates]},
            ),
        )
        if {item.node_id for item in output.reviews} != {item.node_id for item in run.candidates}:
            raise ValueError("Debate must cover every candidate exactly once")
        _record_output(run, "debate", output)
        return {"message": "Anchor candidate debate completed", "review_count": len(output.reviews)}

    def decision(run: ResearchRun, _step: PipelineStep) -> dict[str, Any]:
        output = _generate_model(
            model,
            run,
            DecisionOutput,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_prompt(
                run,
                "Issue a research-priority decision, not a buy or sell recommendation.",
                {
                    "cause": run.manifest["agent_outputs"]["cause"],
                    "financials": run.manifest["agent_outputs"]["compare"],
                    "debate": run.manifest["agent_outputs"]["debate"],
                },
            ),
        )
        candidate_ids = {item.node_id for item in run.candidates}
        if set(output.ranked_node_ids) - candidate_ids:
            raise ValueError("Decision ranks unknown candidates")
        if len(output.ranked_node_ids) != len(set(output.ranked_node_ids)):
            raise ValueError("Decision ranking contains duplicates")
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
                "disclaimer": "Research and education only; not investment advice.",
            },
        )
        return {"message": "Anchor research decision issued", "status": output.research_status}

    return {
        "intake": intake,
        "cause": cause,
        "graph": graph,
        "audit": audit,
        "compare": compare,
        "debate": debate,
        "decision": decision,
    }


def build_anchor_executor(
    run: ResearchRun,
    *,
    provider: str | None,
    max_attempts: int = 2,
) -> WorkflowExecutor:
    selected = select_run_provider(run, provider)
    try:
        model = create_research_model(
            selected,
            subject=run.subject,
            mode="anchor",
        )
        bind_model_identity(run, model)
    except Exception as error:  # noqa: BLE001 - setup failures become durable checkpoints
        setup_error = provider_setup_error(error, provider=selected)

        def fail_setup(
            _run: ResearchRun,
            _step: PipelineStep,
            *,
            detail: Exception = setup_error,
        ) -> dict[str, Any]:
            raise detail

        return WorkflowExecutor(
            handlers={step.key: fail_setup for step in run.pipeline},
            max_attempts=max_attempts,
        )
    return WorkflowExecutor(handlers=build_anchor_handlers(model), max_attempts=max_attempts)
