from __future__ import annotations

import json
from importlib.resources import files

from capexgraph.providers.base import EvidencePolicy, StructuredOutput

THEME_SUBJECTS = {
    "a股半导体硅片",
    "a股半导体硅片板块",
    "半导体硅片",
    "alphabet q2 2026 ai capex transmission",
    "alphabet 2026年q2 ai资本开支传导",
}

ANCHOR_SUBJECTS = {"兆易创新", "603986", "603986.sh"}


class FixtureResearchModel:
    """Deterministic provider backed by a frozen, inspectable evidence pack."""

    provider_name = "fixture"
    provider_version = "1"
    model_name = "golden-a-share-semiconductor-wafers-v1"
    evidence_policy = EvidencePolicy.CURATED

    def __init__(self, subject: str, *, mode: str = "theme") -> None:
        normalized = subject.strip().lower()
        subjects = THEME_SUBJECTS if mode == "theme" else ANCHOR_SUBJECTS
        if normalized not in subjects:
            supported = "、".join(sorted(subjects))
            raise ValueError(f"Fixture provider only supports: {supported}")
        if mode == "anchor":
            filename = "anchor_gigadevice_cn.json"
        elif normalized in {
            "alphabet q2 2026 ai capex transmission",
            "alphabet 2026年q2 ai资本开支传导",
        }:
            filename = "theme_alphabet_q2_2026_us.json"
        else:
            filename = "theme_semiconductor_wafers_cn.json"
        fixture_path = files("capexgraph.fixtures").joinpath(filename)
        self._payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.model_name = self._payload["fixture"]["id"]
        self.execution_context = {
            "api_surface": "local_fixture",
            "transport": "bundled_fixture",
            "auth_mode": "none",
            "billing_mode": "none",
            "endpoint_scope": "local",
        }
        self.call_count = 0

    def generate(
        self,
        output_model: type[StructuredOutput],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> StructuredOutput:
        del system_prompt, user_prompt
        self.call_count += 1
        raw_output = self._payload["outputs"].get(output_model.__name__)
        if raw_output is None:
            raise KeyError(f"Fixture has no output for {output_model.__name__}")
        return output_model.model_validate(raw_output)
