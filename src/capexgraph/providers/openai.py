from __future__ import annotations

import os
from typing import Any

from capexgraph.providers.base import EvidencePolicy, StructuredOutput


class OpenAIResearchModel:
    """Optional OpenAI Responses API adapter with native Pydantic parsing."""

    provider_name = "openai"
    provider_version = "1"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model_name = (model or os.getenv("CAPEXGRAPH_MODEL", "")).strip()
        if not self.model_name:
            raise ValueError("Set CAPEXGRAPH_MODEL when using the OpenAI provider")

        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError(
                    'Install the optional OpenAI adapter with: pip install -e ".[openai]"'
                ) from error
            client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self._client = client

    def generate(
        self,
        output_model: type[StructuredOutput],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> StructuredOutput:
        response = self._client.responses.parse(
            model=self.model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=output_model,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            refusal = getattr(response, "output_text", "")
            raise RuntimeError(f"OpenAI returned no parsed output: {refusal or 'empty response'}")
        if isinstance(parsed, output_model):
            return parsed
        return output_model.model_validate(parsed)
