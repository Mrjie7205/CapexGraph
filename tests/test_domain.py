from datetime import date

import pytest
from pydantic import ValidationError

from capexgraph.domain import Confidence, RelationshipType, SupplyChainEdge


def test_high_confidence_edge_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        SupplyChainEdge(
            id="edge-1",
            source="supplier",
            target="customer",
            relationship=RelationshipType.SUPPLIES,
            product="CMP slurry",
            basis="claimed direct supply relationship",
            confidence=Confidence.HIGH,
            as_of_date=date(2026, 7, 17),
        )


def test_low_confidence_inference_can_be_recorded_without_evidence() -> None:
    edge = SupplyChainEdge(
        id="edge-2",
        source="supplier",
        target="customer",
        relationship=RelationshipType.TWO_HOP,
        product="semiconductor equipment",
        basis="industry structure inference",
        confidence=Confidence.LOW,
        as_of_date=date(2026, 7, 17),
    )
    assert edge.evidence_ids == []
