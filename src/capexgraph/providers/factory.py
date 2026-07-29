from __future__ import annotations

from typing import Any

from capexgraph.providers.base import ProviderName, ResearchModel
from capexgraph.providers.fixture import FixtureResearchModel


def create_research_model(
    provider: ProviderName | str,
    *,
    subject: str,
    mode: str = "theme",
    model: str | None = None,
    client: Any | None = None,
) -> ResearchModel:
    selected = ProviderName(provider)
    if selected == ProviderName.FIXTURE:
        return FixtureResearchModel(subject, mode=mode)
    if selected == ProviderName.CODEX_SUBSCRIPTION:
        from capexgraph.providers.codex_subscription import CodexSubscriptionResearchModel

        return CodexSubscriptionResearchModel(model=model, client=client)
    if selected == ProviderName.OPENAI:
        from capexgraph.providers.openai import OpenAIResearchModel

        return OpenAIResearchModel(model=model, client=client)
    raise ValueError(f"Unsupported research provider: {provider}")
