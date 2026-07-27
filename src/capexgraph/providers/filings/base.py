from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from capexgraph.domain import Evidence, FinancialFact, ResearchRun


class FilingFactsResult(BaseModel):
    evidence: Evidence
    facts: list[FinancialFact]


class FilingFactsValidationError(ValueError):
    """A captured official response failed deterministic fact validation."""

    def __init__(self, message: str, *, evidence: Evidence) -> None:
        super().__init__(message)
        self.evidence = evidence


class FilingFactsProvider(Protocol):
    provider_name: str
    provider_version: str

    def extract(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
    ) -> FilingFactsResult:
        """Capture one official filing-data response and return validated facts."""
        ...
