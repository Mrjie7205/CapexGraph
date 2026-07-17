from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from capexgraph.domain import (
    Confidence,
    EvidenceKind,
    RelationshipType,
    Verdict,
)


class ThemeBoundaryOutput(BaseModel):
    scope: str = Field(min_length=1)
    investment_question: str = Field(min_length=1)
    included_layers: list[str]
    excluded_topics: list[str]
    capex_drivers: list[str]
    research_questions: list[str]


class NodeProposal(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    ticker: str | None = None
    market: str | None = None
    layer: str | None = None


class PlayerCensusOutput(BaseModel):
    nodes: list[NodeProposal] = Field(min_length=1)
    coverage_notes: list[str]
    unresolved_entities: list[str]


class EvidenceProposal(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: EvidenceKind
    source_url: str | None = None
    published_at: date | None = None
    excerpt: str


class EdgeProposal(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relationship: RelationshipType
    product: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    confidence: Confidence
    evidence_ids: list[str]


class ThemeGraphOutput(BaseModel):
    additional_nodes: list[NodeProposal]
    evidence: list[EvidenceProposal]
    edges: list[EdgeProposal]
    graph_gaps: list[str]


class EdgeAuditFinding(BaseModel):
    edge_id: str = Field(min_length=1)
    verdict: Literal["accept", "downgrade", "reject"]
    rationale: str = Field(min_length=1)


class EvidenceAuditOutput(BaseModel):
    findings: list[EdgeAuditFinding]
    source_warnings: list[str]
    audit_summary: str = Field(min_length=1)


class TriggerProposal(BaseModel):
    metric: str = Field(min_length=1)
    operator: Literal[">", ">=", "<", "<=", "=="]
    value: float
    note: str


class CandidateProposal(BaseModel):
    node_id: str = Field(min_length=1)
    verdict: Verdict
    thesis: str = Field(min_length=1)
    archetypes: list[str]
    risks: list[str]
    invalidation: list[str]
    triggers: list[TriggerProposal]
    confidence: Confidence


class BottleneckScoreOutput(BaseModel):
    candidates: list[CandidateProposal]
    ranking_method: str = Field(min_length=1)
    data_gaps: list[str]


class CandidateDebate(BaseModel):
    node_id: str = Field(min_length=1)
    bull_case: list[str]
    bear_case: list[str]
    unresolved_questions: list[str]


class DebateOutput(BaseModel):
    reviews: list[CandidateDebate]
    cross_candidate_observations: list[str]


class DecisionOutput(BaseModel):
    research_status: Literal["needs_review", "blocked"]
    summary: str = Field(min_length=1)
    ranked_node_ids: list[str]
    limitations: list[str]
    next_actions: list[str]
