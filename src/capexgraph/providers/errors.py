from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from capexgraph.config import load_project_env


class ResearchProviderError(RuntimeError):
    """A provider failure whose persisted message is safe to show to operators."""

    category = "provider_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.safe_message = message
        if retryable is not None:
            self.retryable = retryable


class ProviderConfigurationError(ResearchProviderError):
    category = "configuration"


class ProviderAuthenticationError(ResearchProviderError):
    category = "authentication"


class ProviderUnavailableError(ResearchProviderError):
    category = "unavailable"
    retryable = True


class ProviderRateLimitError(ResearchProviderError):
    category = "rate_limit"
    retryable = True


class ProviderProtocolError(ResearchProviderError):
    category = "protocol"


class ProviderOutputValidationError(ResearchProviderError):
    category = "output_validation"


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    if isinstance(value, int):
        return value
    response: Any = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_provider_exception(
    error: Exception,
    *,
    provider: str,
) -> ResearchProviderError:
    """Map SDK/transport errors into stable, credential-safe failure categories."""

    if isinstance(error, ResearchProviderError):
        return error
    status = _status_code(error)
    name = type(error).__name__.lower()
    if isinstance(error, ValidationError):
        return ProviderOutputValidationError(
            f"{provider} returned output that failed schema validation.",
            provider=provider,
        )
    if status in {401, 403}:
        return ProviderAuthenticationError(
            f"{provider} authentication failed.",
            provider=provider,
        )
    if status == 404:
        return ProviderConfigurationError(
            f"{provider} model or Responses endpoint was not found.",
            provider=provider,
        )
    if status == 429:
        return ProviderRateLimitError(
            f"{provider} rate limit or quota was reached.",
            provider=provider,
        )
    if status == 408 or "timeout" in name:
        return ProviderUnavailableError(
            f"{provider} request timed out.",
            provider=provider,
        )
    if status is not None and status >= 500:
        return ProviderUnavailableError(
            f"{provider} upstream service is unavailable.",
            provider=provider,
        )
    if "connection" in name:
        return ProviderUnavailableError(
            f"{provider} endpoint is unreachable.",
            provider=provider,
        )
    return ProviderProtocolError(
        f"{provider} returned an incompatible Responses payload.",
        provider=provider,
    )


def redact_provider_secrets(value: object) -> str:
    """Remove configured model credentials and common Authorization forms from text."""

    load_project_env()
    text = str(value)
    for name in (
        "OPENAI_API_KEY",
        "CAPEXGRAPH_CODEX_PROXY_KEY",
        "JIN10_MCP_BEARER_TOKEN",
        "JIN10_WEBSOCKET_SECRET_KEY",
    ):
        secret = os.getenv(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)((?:api|proxy|secret)[_-]?key\s*[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    return text


def provider_failure_record(
    *,
    error: ResearchProviderError,
    stage: str,
) -> dict[str, Any]:
    return {
        "provider": error.provider,
        "stage": stage,
        "category": error.category,
        "retryable": error.retryable,
        "error": error.safe_message,
        "at": datetime.now(UTC).isoformat(),
    }
