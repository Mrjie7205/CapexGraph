from __future__ import annotations

from typing import Any

from capexgraph.providers.base import EvidencePolicy, StructuredOutput
from capexgraph.providers.config import ModelSettings
from capexgraph.providers.errors import ProviderConfigurationError
from capexgraph.providers.responses import generate_responses_output


class OpenAIResearchModel:
    """Optional OpenAI Responses API adapter with native Pydantic parsing."""

    provider_name = "openai"
    provider_version = "1"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL
    execution_context = {
        "api_surface": "responses",
        "transport": "openai_official_api",
        "auth_mode": "api_key",
        "billing_mode": "openai_api",
        "endpoint_scope": "api.openai.com",
    }

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        settings = ModelSettings.from_environment()
        self.model_name = (model or settings.openai_model or "").strip()
        if not self.model_name:
            raise ProviderConfigurationError(
                "Set CAPEXGRAPH_OPENAI_MODEL when using the OpenAI provider.",
                provider=self.provider_name,
            )

        if client is None:
            resolved_api_key = api_key or settings.openai_api_key
            if not resolved_api_key:
                raise ProviderConfigurationError(
                    "Set OPENAI_API_KEY when using the OpenAI provider.",
                    provider=self.provider_name,
                )
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProviderConfigurationError(
                    'Install the optional OpenAI adapter with: pip install -e ".[openai]"',
                    provider=self.provider_name,
                ) from error
            client = OpenAI(api_key=resolved_api_key, max_retries=0)
        self._client = client
        self.call_count = 0

    def generate(
        self,
        output_model: type[StructuredOutput],
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> StructuredOutput:
        self.call_count += 1
        return generate_responses_output(
            self._client,
            provider_name=self.provider_name,
            model_name=self.model_name,
            output_model=output_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
