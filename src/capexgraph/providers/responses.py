from __future__ import annotations

from typing import Any

from capexgraph.providers.base import StructuredOutput
from capexgraph.providers.errors import (
    ProviderOutputValidationError,
    ResearchProviderError,
    classify_provider_exception,
)


def generate_responses_output(
    client: Any,
    *,
    provider_name: str,
    model_name: str,
    output_model: type[StructuredOutput],
    system_prompt: str,
    user_prompt: str,
) -> StructuredOutput:
    """Call one Responses-compatible endpoint and validate the Pydantic output."""

    try:
        response = client.responses.parse(
            model=model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=output_model,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderOutputValidationError(
                f"{provider_name} returned no schema-validated output.",
                provider=provider_name,
            )
        if isinstance(parsed, output_model):
            return parsed
        return output_model.model_validate(parsed)
    except ResearchProviderError:
        raise
    except Exception as error:
        raise classify_provider_exception(error, provider=provider_name) from error
