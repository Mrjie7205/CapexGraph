from __future__ import annotations

from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class ProviderName(StrEnum):
    FIXTURE = "fixture"
    OPENAI = "openai"


class EvidencePolicy(StrEnum):
    CURATED = "curated"
    UNVERIFIED_MODEL = "unverified_model"


class ResearchModel(Protocol):
    provider_name: str
    provider_version: str
    model_name: str
    evidence_policy: EvidencePolicy

    def generate(
        self,
        output_model: type[StructuredOutput],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> StructuredOutput:
        """Return one schema-validated agent output."""
        ...
