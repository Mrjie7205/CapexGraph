from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from capexgraph.providers.base import EvidencePolicy, StructuredOutput
from capexgraph.providers.config import ModelSettings, validate_codex_base_url
from capexgraph.providers.errors import ProviderConfigurationError
from capexgraph.providers.responses import generate_responses_output


class CodexSubscriptionResearchModel:
    """Responses adapter for a local CLIProxyAPI authenticated with ChatGPT OAuth."""

    provider_name = "codex_subscription"
    provider_version = "1"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        proxy_key: str | None = None,
        timeout_seconds: float | None = None,
        client: Any | None = None,
    ) -> None:
        settings = ModelSettings.from_environment()
        if settings.configuration_errors:
            raise ProviderConfigurationError(
                settings.configuration_errors[0],
                provider=self.provider_name,
            )
        self.model_name = (model or settings.codex_model or "").strip()
        if not self.model_name:
            raise ProviderConfigurationError(
                "Set CAPEXGRAPH_CODEX_MODEL when using the Codex subscription provider.",
                provider=self.provider_name,
            )
        resolved_base_url = validate_codex_base_url(
            base_url or settings.codex_base_url,
            allow_remote=settings.allow_remote_codex_proxy,
        )
        endpoint_scope = (
            "loopback"
            if urlsplit(resolved_base_url).hostname in {"127.0.0.1", "localhost", "::1"}
            else "remote_opt_in"
        )
        self.execution_context = {
            "api_surface": "responses",
            "transport": "openai_compatible_local_proxy",
            "proxy": "CLIProxyAPI",
            "auth_mode": "chatgpt_oauth_via_proxy",
            "billing_mode": "chatgpt_subscription",
            "endpoint_scope": endpoint_scope,
        }
        if client is None:
            resolved_proxy_key = proxy_key or settings.codex_proxy_key
            if not resolved_proxy_key:
                raise ProviderConfigurationError(
                    "Set CAPEXGRAPH_CODEX_PROXY_KEY when using the Codex subscription provider.",
                    provider=self.provider_name,
                )
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProviderConfigurationError(
                    'Install the model adapters with: pip install -e ".[openai]"',
                    provider=self.provider_name,
                ) from error
            client = OpenAI(
                base_url=resolved_base_url,
                api_key=resolved_proxy_key,
                timeout=timeout_seconds or settings.codex_timeout_seconds,
                max_retries=0,
            )
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
