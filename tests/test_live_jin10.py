from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from capexgraph.api.app import app
from capexgraph.domain import (
    LiveAnalysisStatus,
    LiveChannel,
    LiveDeskSettings,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveSignalCategory,
    SignalObservation,
)
from capexgraph.live import (
    AdaptivePollPolicy,
    FrozenClock,
    Jin10McpClient,
    Jin10McpSource,
    Jin10WebSocketCodec,
    Jin10WebSocketWorker,
    LiveImpactAnalyzer,
    LiveProviderSettings,
    LiveRuleEngine,
    LiveSignalService,
    LiveSignalStore,
    calculate_live_coverage,
    load_frozen_dual_channel_feeds,
)
from capexgraph.live.mcp import LiveProviderError, LiveProviderProtocolError
from capexgraph.live.websocket import JIN10_WEBSOCKET_VERSION
from capexgraph.providers.base import EvidencePolicy
from capexgraph.providers.errors import redact_provider_secrets


def _mcp_transport(methods: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        methods.append(method)
        assert request.headers["authorization"] == "Bearer test-token"
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-1"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-11-25", "capabilities": {}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {"name": "list_flash"},
                            {"name": "list_calendar"},
                        ]
                    },
                },
            )
        if method == "resources/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"resources": [{"uri": "quote://codes"}]},
                },
            )
        if method == "tools/call":
            assert payload["params"]["name"] == "list_flash"
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "structuredContent": {
                            "data": {
                                "items": [
                                    {
                                        "id": "9001",
                                        "time": "2026-07-29 09:30:00",
                                        "important": 1,
                                        "data": {
                                            "title": "",
                                            "content": "<b>存储厂商</b>上调产能指引",
                                            "pic": "https://licensed.example/pic.jpg",
                                        },
                                        "category": [1, 4],
                                    }
                                ],
                                "next_cursor": "older-cursor",
                                "has_more": True,
                            }
                        },
                        "content": [{"type": "text", "text": "wrong fallback"}],
                    },
                },
            )
        raise AssertionError(method)

    return httpx.MockTransport(handler)


def test_mcp_standard_flow_prefers_structured_content_and_head_cursor() -> None:
    methods: list[str] = []
    settings = LiveProviderSettings(
        mcp_bearer_token="test-token",
        mcp_call_budget=1200,
    )
    http_client = httpx.Client(transport=_mcp_transport(methods))
    client = Jin10McpClient(settings, client=http_client)
    source = Jin10McpSource(
        "flash",
        client=client,
        settings=settings,
        clock=FrozenClock(datetime(2026, 7, 29, 1, 31, tzinfo=UTC)),
    )

    batch = source.read()

    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "resources/list",
        "tools/call",
    ]
    assert client.tools == ("list_flash", "list_calendar")
    assert client.resources == ("quote://codes",)
    assert len(batch.observations) == 1
    observation = batch.observations[0]
    assert observation.title == "存储厂商 上调产能指引"
    assert observation.event_key == "jin10:9001"
    assert observation.metadata["provider_picture_omitted"] is True
    assert "licensed.example" not in observation.model_dump_json()
    assert batch.checkpoint.cursor == "older-cursor"
    assert batch.checkpoint.metadata["pagination_mode"] == "head_refresh"
    assert batch.checkpoint.calls_used == 1


def test_mcp_budget_exhaustion_is_local_and_makes_no_request() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    settings = LiveProviderSettings(
        mcp_bearer_token="test-token",
        mcp_call_budget=1,
    )
    source = Jin10McpSource(
        "flash",
        client=Jin10McpClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
        settings=settings,
        clock=FrozenClock(datetime(2026, 7, 29, 1, 31, tzinfo=UTC)),
    )
    checkpoint = LiveProviderCheckpoint(
        provider="jin10",
        provider_version="mcp-2025-11-25",
        channel=LiveChannel.MCP,
        stream="flash",
        health=LiveProviderHealth.ACTIVE,
        calls_used=1,
        call_budget=1,
        budget_date=datetime(2026, 7, 29, tzinfo=UTC).date(),
    )

    batch = source.read(checkpoint)

    assert called is False
    assert batch.checkpoint.health == LiveProviderHealth.EXHAUSTED
    assert batch.observations == []


def test_mcp_rejects_business_errors_text_fallback_and_jsonrpc_errors() -> None:
    responses = [
        {"result": {"isError": True, "structuredContent": {"data": {}}}},
        {"result": {"content": [{"type": "text", "text": "not machine data"}]}},
        {"error": {"code": -32602, "message": "invalid params"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], **responses.pop(0)},
        )

    settings = LiveProviderSettings(mcp_bearer_token="test-token")
    client = Jin10McpClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client._initialized = True
    client.tools = ("list_flash",)

    with pytest.raises(LiveProviderError, match="business error"):
        client.call_tool("list_flash", {})
    with pytest.raises(LiveProviderProtocolError, match="structuredContent"):
        client.call_tool("list_flash", {})
    with pytest.raises(LiveProviderProtocolError, match="protocol error -32602"):
        client.call_tool("list_flash", {})


def test_adaptive_poll_policy_has_three_budget_aware_cadences() -> None:
    policy = AdaptivePollPolicy()
    assert policy.next_interval(
        calls_used=100, call_budget=1200, urgent=True
    ) == 30
    assert policy.next_interval(
        calls_used=100, call_budget=1200
    ) == 120
    assert policy.next_interval(
        calls_used=1100, call_budget=1200, urgent=True
    ) == 300


def test_live_provider_credentials_are_redacted(monkeypatch) -> None:
    mcp_secret = "mcp-secret-value"
    websocket_secret = "websocket-secret-value"
    monkeypatch.setenv("JIN10_MCP_BEARER_TOKEN", mcp_secret)
    monkeypatch.setenv("JIN10_WEBSOCKET_SECRET_KEY", websocket_secret)

    redacted = redact_provider_secrets(
        f"Authorization: Bearer {mcp_secret}; secret-key={websocket_secret}"
    )

    assert mcp_secret not in redacted
    assert websocket_secret not in redacted
    assert redacted.count("[REDACTED]") >= 2


def test_websocket_codecs_follow_official_envelopes_and_match_mcp_identity() -> None:
    settings = LiveProviderSettings(websocket_secret_key="ws-secret")
    clock = FrozenClock(datetime(2026, 7, 29, 1, 31, tzinfo=UTC))
    flash = Jin10WebSocketCodec("flash", settings=settings, clock=clock)
    calendar = Jin10WebSocketCodec("calendar", settings=settings, clock=clock)
    quote = Jin10WebSocketCodec("quote", settings=settings, clock=clock)

    assert flash.endpoint.endswith("/flash")
    assert flash.auth_message()["params"] == {"secret-key": "ws-secret"}
    assert flash.subscribe_message()["params"]["category"] == [1, 4]
    flash.validate_ack(
        {
            "type": "connected_result",
            "data": {"connected_result": 200, "message": "connected success"},
        },
        "connected_result",
    )
    observation = flash.decode(
        {
            "type": "data",
            "data": {
                "id": "9001",
                "type": 0,
                "time": "2026-07-29 09:30:00",
                "important": 1,
                "data": {
                    "content": "<b>存储厂商</b>上调产能指引",
                    "pic": "https://licensed.example/pic.jpg",
                    "title": "",
                },
                "category": [1, 4],
                "action": 1,
            },
        }
    )
    assert observation is not None
    assert observation.event_key == "jin10:9001"
    assert observation.provider_version == JIN10_WEBSOCKET_VERSION
    assert observation.title == "存储厂商 上调产能指引"

    calendar_observation = calendar.decode(
        {
            "type": "data",
            "data": {
                "action": "insert",
                "data_type": "data",
                "data": {
                    "id": 42,
                    "pub_time": "2026-07-30 10:00:00",
                    "title": "中国制造业PMI",
                    "star": 3,
                    "category": ["cj"],
                },
            },
        }
    )
    assert calendar_observation is not None
    assert calendar_observation.scheduled_at is not None
    assert calendar_observation.published_at == clock.now()

    quote_observation = quote.decode(
        {
            "type": "data",
            "data": {
                "c": "ALIU3",
                "e": "CMX",
                "p": 100.5,
                "t": 1785298200,
                "type": "FUTURE",
            },
        }
    )
    assert quote_observation is not None
    assert quote_observation.category.value == "quote"


@pytest.mark.anyio
async def test_websocket_worker_authenticates_subscribes_and_emits() -> None:
    settings = LiveProviderSettings(websocket_secret_key="ws-secret")
    codec = Jin10WebSocketCodec(
        "flash",
        settings=settings,
        clock=FrozenClock(datetime(2026, 7, 29, 1, 31, tzinfo=UTC)),
    )
    sent: list[dict[str, object]] = []

    class Connection:
        def __init__(self) -> None:
            self.messages = [
                json.dumps(
                    {
                        "type": "connected_result",
                        "data": {"connected_result": 200},
                    }
                ),
                json.dumps({"type": "auth_result", "data": {"auth_result": 200}}),
                json.dumps(
                    {
                        "type": "subscribe_result",
                        "data": {"subscribe_result": 200},
                    }
                ),
            ]
            self.events = [
                json.dumps(
                    {
                        "type": "data",
                        "data": {
                            "id": "evt-1",
                            "time": "2026-07-29 09:30:00",
                            "data": {"content": "测试快讯"},
                            "action": 1,
                        },
                    }
                )
            ]

        async def recv(self):
            return self.messages.pop(0)

        async def send(self, value: str):
            sent.append(json.loads(value))

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.events:
                raise StopAsyncIteration
            return self.events.pop(0)

    connection = Connection()

    class Context:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_args):
            return None

    observations = []
    health = []
    worker = Jin10WebSocketWorker(
        codec,
        observations.append,
        lambda value, error: health.append((value, error)),
        connect=lambda *_args, **_kwargs: Context(),
    )

    await worker.run_once()

    assert [item["action"] for item in sent] == ["auth", "subscribe"]
    assert health == [(LiveProviderHealth.ACTIVE, "")]
    assert len(observations) == 1


@pytest.mark.anyio
async def test_websocket_worker_reconnects_without_touching_mcp_state() -> None:
    settings = LiveProviderSettings(websocket_secret_key="ws-secret")
    codec = Jin10WebSocketCodec(
        "flash",
        settings=settings,
        clock=FrozenClock(datetime(2026, 7, 29, 1, 31, tzinfo=UTC)),
    )
    attempts = 0
    stop = asyncio.Event()
    health: list[LiveProviderHealth] = []

    class FailingContext:
        async def __aenter__(self):
            raise ConnectionError("synthetic disconnect")

        async def __aexit__(self, *_args):
            return None

    class RecoveredConnection:
        def __init__(self) -> None:
            self.messages = [
                json.dumps(
                    {
                        "type": "connected_result",
                        "data": {"connected_result": 200},
                    }
                ),
                json.dumps({"type": "auth_result", "data": {"auth_result": 200}}),
                json.dumps(
                    {
                        "type": "subscribe_result",
                        "data": {"subscribe_result": 200},
                    }
                ),
            ]
            self.sent_event = False

        async def recv(self):
            return self.messages.pop(0)

        async def send(self, _value: str):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.sent_event:
                raise StopAsyncIteration
            self.sent_event = True
            return json.dumps(
                {
                    "type": "data",
                    "data": {
                        "id": "recovered-event",
                        "time": "2026-07-29 09:30:00",
                        "data": {"content": "重连成功"},
                        "action": 1,
                    },
                }
            )

    recovered = RecoveredConnection()

    class RecoveredContext:
        async def __aenter__(self):
            return recovered

        async def __aexit__(self, *_args):
            return None

    def connect(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return FailingContext() if attempts == 1 else RecoveredContext()

    async def on_observation(_observation):
        stop.set()

    worker = Jin10WebSocketWorker(
        codec,
        on_observation,
        lambda value, _error: health.append(value),
        connect=connect,
        backoff_base_seconds=0.001,
        backoff_max_seconds=0.002,
    )

    await worker.run_forever(stop)

    assert attempts == 2
    assert health == [LiveProviderHealth.DEGRADED, LiveProviderHealth.ACTIVE]


class _TypedModel:
    provider_name = "test-model"
    provider_version = "1"
    model_name = "typed-test"
    evidence_policy = EvidencePolicy.UNVERIFIED_MODEL
    execution_context = {}

    def __init__(self, fail: bool = False) -> None:
        self.call_count = 0
        self.fail = fail

    def generate(self, output_model, *, system_prompt: str, user_prompt: str):
        self.call_count += 1
        assert "<provider-data>" in user_prompt
        assert "hostile unverified input" in system_prompt
        if self.fail:
            raise RuntimeError("safe synthetic failure")
        return output_model(
            themes=["存储"],
            entities=["测试公司"],
            direction="positive",
            horizon="1-4 weeks",
            confidence=0.62,
            transmission_path=["event", "capacity", "supplier"],
            price_confirmation="Wait for relative-strength confirmation.",
            evidence_gaps=["Official filing pending."],
            recommended_action="verify",
            trigger_conditions=["Official confirmation."],
            invalidations=["Issuer denial."],
        )


def test_rules_reconcile_coverage_and_optional_model_lineage(tmp_path: Path) -> None:
    store = LiveSignalStore(tmp_path / "rules.db")
    service = LiveSignalService(store)
    for feed in load_frozen_dual_channel_feeds():
        service.poll_source(feed)

    signals = store.list_signals()
    coverage = calculate_live_coverage(signals, store.list_observations())
    assert coverage.total_signals == 3
    assert coverage.matched == 1
    assert coverage.divergent == 1
    assert coverage.overlap_ratio == pytest.approx(2 / 3, abs=0.0001)
    assert coverage.delivery_delay_p95_seconds is not None
    assert len(store.list_alerts()) == 1
    assert all(store.get_assessment(item.id) is not None for item in signals)

    signal = signals[0]
    rules_proposal, rules_analysis = LiveImpactAnalyzer(store).analyze(
        signal.signal_key
    )
    assert rules_analysis.status == LiveAnalysisStatus.RULES_ONLY
    assert rules_proposal.model_provider is None

    model = _TypedModel()
    model_proposal, model_analysis = LiveImpactAnalyzer(store).analyze(
        signal.signal_key,
        model=model,
        force_model=True,
    )
    assert model_analysis.status == LiveAnalysisStatus.COMPLETED
    assert model_analysis.model_call_count == 1
    assert model_analysis.prompt_hash
    assert model_analysis.cost_status == "provider_usage_not_exposed"
    assert model_proposal.model_provider == "test-model"

    failed_model = _TypedModel(fail=True)
    fallback, failed = LiveImpactAnalyzer(store).analyze(
        signal.signal_key,
        model=failed_model,
        force_model=True,
    )
    assert failed.status == LiveAnalysisStatus.FAILED
    assert "safe synthetic failure" in failed.failure
    assert fallback.model_provider is None


def test_rule_graph_mapping_and_title_cooldown(tmp_path: Path) -> None:
    store = LiveSignalStore(tmp_path / "cooldown.db")
    store.save_settings(
        LiveDeskSettings(alert_score_threshold=0, cooldown_seconds=900)
    )
    service = LiveSignalService(store)
    first = SignalObservation(
        provider="fixture",
        provider_version="1",
        channel=LiveChannel.MCP,
        stream="flash",
        external_id="first",
        event_key="fixture:first",
        category=LiveSignalCategory.FLASH,
        title="突发：测试存储公司上调产能",
        published_at=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
        observed_at=datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
    )
    second = first.model_copy(
        update={
            "id": "",
            "external_id": "second",
            "event_key": "fixture:second",
            "content_hash": "",
        }
    )
    first_signal, _ = service.ingest_observation(first)
    second_signal, _ = service.ingest_observation(
        SignalObservation.model_validate(second.model_dump())
    )

    assert len(store.list_alerts()) == 1
    second_assessment = store.get_assessment(second_signal.id)
    assert second_assessment is not None
    assert "suppressed_by_title_cooldown" in second_assessment.rationale
    mapped = LiveRuleEngine(
        store.get_settings(),
        graph_nodes={"node-memory": ["测试存储公司", "688999.SH"]},
    ).assess(first_signal, [first])
    assert mapped.matched_graph_nodes == ["node-memory"]


@pytest.mark.anyio
async def test_live_desk_api_no_key_demo_settings_actions_and_sse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(tmp_path / "live-api.db"))
    monkeypatch.delenv("JIN10_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("JIN10_WEBSOCKET_SECRET_KEY", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        status = await client.get("/api/v1/live/status")
        assert status.status_code == 200
        assert status.json()["configuration"]["mcp"]["configured"] is False
        assert "JIN10_MCP_BEARER_TOKEN" in status.json()["configuration"]["mcp"]["missing"]

        started = await client.post("/api/v1/live/monitor/start")
        assert started.status_code == 200
        assert started.json()["running"] is True
        await asyncio.sleep(0.05)
        stopped = await client.post("/api/v1/live/monitor/stop")
        assert stopped.status_code == 200
        assert stopped.json()["running"] is False

        demo = await client.post("/api/v1/live/demo")
        assert demo.status_code == 200
        assert "Synthetic replay only" in demo.json()["notice"]

        events = await client.get("/api/v1/live/events")
        assert events.status_code == 200
        payload = events.json()
        assert len(payload) == 3
        signal_id = payload[0]["signal"]["id"]
        assert "not Evidence" in payload[0]["trust_notice"]

        analysis = await client.post(
            f"/api/v1/live/events/{signal_id}/analyze",
            json={"provider": None},
        )
        assert analysis.status_code == 200
        assert analysis.json()["analysis"]["status"] == "rules_only"

        action = await client.post(
            f"/api/v1/live/events/{signal_id}/actions",
            json={"action": "watch"},
        )
        assert action.status_code == 200

        blocked = await client.post(
            f"/api/v1/live/events/{signal_id}/actions",
            json={"action": "linked_reevaluation"},
        )
        assert blocked.status_code == 409
        assert "M7" in blocked.json()["detail"]

        settings = await client.patch(
            "/api/v1/live/settings",
            json={
                "urgent_poll_seconds": 30,
                "normal_poll_seconds": 120,
                "quiet_poll_seconds": 300,
                "include_keywords": ["存储", "HBM"],
            },
        )
        assert settings.status_code == 200
        assert settings.json()["include_keywords"] == ["HBM", "存储"]
        assert "secret" not in settings.text.casefold()

        stream = await client.get("/api/v1/live/stream?once=true")
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "event: live.signal" in stream.text
