from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI

from capexgraph.providers import (
    ModelSettings,
    ProviderUnavailableError,
    codex_subscription,
)
from capexgraph.providers.codex_subscription import CodexSubscriptionResearchModel
from capexgraph.providers.config import validate_codex_base_url
from capexgraph.providers.errors import ProviderConfigurationError
from capexgraph.research.theme_schemas import ThemeBoundaryOutput


def _boundary() -> ThemeBoundaryOutput:
    return ThemeBoundaryOutput(
        scope="scope",
        investment_question="question",
        included_layers=[],
        excluded_topics=[],
        capex_drivers=[],
        research_questions=[],
    )


def test_model_status_keeps_three_channels_and_redacts_credentials(monkeypatch) -> None:
    openai_key = "openai-secret-that-must-not-leak"
    proxy_key = "proxy-secret-that-must-not-leak"
    monkeypatch.setenv("OPENAI_API_KEY", openai_key)
    monkeypatch.setenv("CAPEXGRAPH_OPENAI_MODEL", "openai-model")
    monkeypatch.setenv("CAPEXGRAPH_CODEX_PROXY_KEY", proxy_key)
    monkeypatch.setenv("CAPEXGRAPH_CODEX_MODEL", "codex-model")
    monkeypatch.setenv("CAPEXGRAPH_CODEX_BASE_URL", "http://127.0.0.1:8317/v1")

    status = ModelSettings.from_environment().provider_status()

    assert [item["name"] for item in status] == [
        "fixture",
        "codex_subscription",
        "openai",
    ]
    assert all(item["configured"] for item in status)
    serialized = json.dumps(status)
    assert openai_key not in serialized
    assert proxy_key not in serialized


def test_codex_proxy_rejects_remote_endpoints_without_explicit_opt_in() -> None:
    with pytest.raises(ProviderConfigurationError, match="must use loopback"):
        validate_codex_base_url("https://proxy.example.com/v1")

    assert (
        validate_codex_base_url(
            "https://proxy.example.com/v1",
            allow_remote=True,
        )
        == "https://proxy.example.com/v1"
    )


def test_codex_provider_reuses_pydantic_responses_contract(monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_CODEX_MODEL", "codex-model")

    class FakeResponses:
        def __init__(self) -> None:
            self.kwargs = None

        def parse(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_parsed=_boundary())

    responses = FakeResponses()
    provider = CodexSubscriptionResearchModel(
        client=SimpleNamespace(responses=responses),
    )

    actual = provider.generate(
        ThemeBoundaryOutput,
        system_prompt="system",
        user_prompt="user",
    )

    assert actual == _boundary()
    assert responses.kwargs["model"] == "codex-model"
    assert responses.kwargs["text_format"] is ThemeBoundaryOutput
    assert provider.execution_context["billing_mode"] == "chatgpt_subscription"
    assert provider.call_count == 1


def test_codex_official_cli_uses_chatgpt_subscription_without_api_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_CODEX_TRANSPORT", "cli")
    monkeypatch.delenv("CAPEXGRAPH_CODEX_PROXY_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        codex_subscription,
        "probe_codex_cli",
        lambda _explicit=None: {
            "installed": True,
            "authenticated": True,
            "auth_mode": "chatgpt",
            "version": "codex-cli test",
            "reachability": "ready",
            "errors": [],
        },
    )
    monkeypatch.setattr(
        codex_subscription,
        "resolve_codex_model",
        lambda _configured=None: "gpt-test",
    )
    captured: dict[str, object] = {}

    def fake_generate(output_model, **kwargs):
        captured.update(kwargs)
        assert output_model is ThemeBoundaryOutput
        return _boundary()

    monkeypatch.setattr(
        codex_subscription,
        "generate_codex_cli_output",
        fake_generate,
    )

    provider = CodexSubscriptionResearchModel()
    actual = provider.generate(
        ThemeBoundaryOutput,
        system_prompt="system",
        user_prompt="user",
    )

    assert actual == _boundary()
    assert captured["model"] == "gpt-test"
    assert provider.execution_context == {
        "api_surface": "codex_exec",
        "transport": "official_codex_cli",
        "auth_mode": "chatgpt_managed",
        "billing_mode": "chatgpt_subscription",
        "endpoint_scope": "local_process",
        "cli_version": "codex-cli test",
    }


def test_openai_sdk_sends_strict_schema_to_codex_responses_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_CODEX_MODEL", "codex-model")
    captured: dict[str, object] = {}
    expected = _boundary()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "max_output_tokens": None,
                "model": "codex-model",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": expected.model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": True,
                "previous_response_id": None,
                "reasoning": None,
                "store": False,
                "temperature": None,
                "text": {"format": {"type": "text"}},
                "tool_choice": "auto",
                "tools": [],
                "top_p": None,
                "truncation": "disabled",
                "usage": None,
                "user": None,
                "metadata": {},
            },
        )

    client = OpenAI(
        api_key="local-proxy-test-key",
        base_url="http://127.0.0.1:8317/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    provider = CodexSubscriptionResearchModel(client=client)

    assert provider.generate(
        ThemeBoundaryOutput,
        system_prompt="system",
        user_prompt="user",
    ) == expected
    assert captured["url"] == "http://127.0.0.1:8317/v1/responses"
    body = captured["body"]
    assert isinstance(body, dict)
    schema_format = body["text"]["format"]
    assert schema_format["type"] == "json_schema"
    assert schema_format["strict"] is True
    assert schema_format["schema"]["additionalProperties"] is False


def test_codex_failure_does_not_fall_back_or_leak_keys(monkeypatch) -> None:
    secret = "proxy-secret-that-must-not-leak"
    monkeypatch.setenv("CAPEXGRAPH_CODEX_MODEL", "codex-model")
    monkeypatch.setenv("CAPEXGRAPH_CODEX_PROXY_KEY", secret)
    monkeypatch.setenv("OPENAI_API_KEY", "official-api-key-must-not-be-used")

    class FailedResponses:
        def parse(self, **_kwargs):
            raise ConnectionError(f"Authorization: Bearer {secret}")

    provider = CodexSubscriptionResearchModel(
        client=SimpleNamespace(responses=FailedResponses()),
    )

    with pytest.raises(ProviderUnavailableError) as captured:
        provider.generate(
            ThemeBoundaryOutput,
            system_prompt="system",
            user_prompt="user",
        )

    assert secret not in str(captured.value)
    assert captured.value.provider == "codex_subscription"
    assert captured.value.retryable is True
