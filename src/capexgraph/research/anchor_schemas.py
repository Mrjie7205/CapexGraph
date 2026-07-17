from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from capexgraph.domain import Confidence
from capexgraph.research.theme_schemas import (
    CandidateProposal,
    EdgeProposal,
    EvidenceProposal,
    NodeProposal,
)


class AnchorIdentityOutput(BaseModel):
    anchor: NodeProposal
    products: list[str] = Field(min_length=1)
    role: str = Field(min_length=1)
    evidence: list[EvidenceProposal] = Field(min_length=1)
    unresolved_questions: list[str]


class RepricingDriver(BaseModel):
    title: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    evidence_ids: list[str]
    confidence: Confidence
    priced_in_risk: str = Field(min_length=1)


class RepricingCauseOutput(BaseModel):
    drivers: list[RepricingDriver] = Field(min_length=1)
    evidence: list[EvidenceProposal]
    market_context: str = Field(min_length=1)
    data_gaps: list[str]


class AnchorGraphOutput(BaseModel):
    neighbours: list[NodeProposal] = Field(min_length=1)
    evidence: list[EvidenceProposal]
    edges: list[EdgeProposal] = Field(min_length=1)
    graph_gaps: list[str]


class NeighbourFinancial(BaseModel):
    node_id: str = Field(min_length=1)
    period_end: date
    revenue_growth_pct: float | None = None
    gross_margin_pct: float | None = None
    rd_ratio_pct: float | None = None
    operating_cashflow_cny_mn: float | None = None
    profit_signal: str = Field(min_length=1)
    source_evidence_ids: list[str]
    missing_metrics: list[str]


class NeighbourComparisonOutput(BaseModel):
    comparisons: list[NeighbourFinancial] = Field(min_length=1)
    candidates: list[CandidateProposal] = Field(min_length=1)
    ranking_method: str = Field(min_length=1)
    data_gaps: list[str]
