from __future__ import annotations

import json
from importlib.resources import files

from capexgraph.providers.base import EvidencePolicy, StructuredOutput

SUPPORTED_SUBJECTS = {
    "a股半导体硅片",
    "a股半导体硅片板块",
    "半导体硅片",
}


class FixtureResearchModel:
    """Deterministic provider backed by a frozen, inspectable evidence pack."""

    provider_name = "fixture"
    model_name = "golden-a-share-semiconductor-wafers-v1"
    evidence_policy = EvidencePolicy.CURATED

    def __init__(self, subject: str) -> None:
        normalized = subject.strip().lower()
        if normalized not in SUPPORTED_SUBJECTS:
            supported = "、".join(sorted(SUPPORTED_SUBJECTS))
            raise ValueError(f"Fixture provider only supports: {supported}")
        fixture_path = files("capexgraph.fixtures").joinpath("theme_semiconductor_wafers_cn.json")
        self._payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    def generate(
        self,
        output_model: type[StructuredOutput],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> StructuredOutput:
        del system_prompt, user_prompt
        raw_output = self._payload["outputs"].get(output_model.__name__)
        if raw_output is None:
            raise KeyError(f"Fixture has no output for {output_model.__name__}")
        return output_model.model_validate(raw_output)
