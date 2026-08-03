"""Model-provider adapters for structured research agents."""

from capexgraph.providers.base import EvidencePolicy, ProviderName, ResearchModel
from capexgraph.providers.config import ModelSettings
from capexgraph.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ResearchProviderError,
    provider_failure_record,
    redact_provider_secrets,
)
from capexgraph.providers.factory import create_research_model

__all__ = [
    "EvidencePolicy",
    "ModelSettings",
    "ProviderAuthenticationError",
    "ProviderConfigurationError",
    "ProviderName",
    "ProviderOutputValidationError",
    "ProviderProtocolError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "ResearchProviderError",
    "ResearchModel",
    "create_research_model",
    "provider_failure_record",
    "redact_provider_secrets",
]
