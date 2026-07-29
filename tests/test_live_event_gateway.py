from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from capexgraph.cli import app
from capexgraph.domain import (
    LiveChannel,
    LiveMatchStatus,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveRetentionClass,
    LiveSignalCategory,
    ProposalHumanStatus,
    ResearchAction,
    ResearchActionProposal,
    SignalObservation,
)
from capexgraph.live import (
    FrozenClock,
    LiveSignalService,
    LiveSignalStore,
    LiveSourceDescriptor,
    load_frozen_dual_channel_feeds,
)


def test_signal_observation_derives_identity_and_requires_aware_timestamps() -> None:
    payload = {
        "provider": "fixture",
        "provider_version": "1",
        "channel": LiveChannel.MCP,
        "stream": "flash",
        "external_id": "event-1",
        "category": LiveSignalCategory.FLASH,
        "title": "Synthetic event",
        "published_at": datetime(2026, 7, 29, 1, 0),
        "observed_at": datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
    }
    with pytest.raises(ValidationError, match="timezone-aware"):
        SignalObservation(**payload)

    payload["published_at"] = datetime(2026, 7, 29, 1, 0, tzinfo=UTC)
    observation = SignalObservation(**payload)
    repeated = SignalObservation(**payload)

    assert observation.id == repeated.id
    assert observation.content_hash == repeated.content_hash
    assert len(observation.content_hash) == 64
    assert observation.event_key == "fixture:event-1"


def test_live_store_migration_and_metadata_retention(tmp_path) -> None:
    store = LiveSignalStore(tmp_path / "live.db")
    observation = SignalObservation(
        provider="fixture",
        provider_version="1",
        channel=LiveChannel.MCP,
        stream="flash",
        external_id="metadata-only",
        category=LiveSignalCategory.FLASH,
        title="Synthetic metadata-only event",
        content="This content must not be persisted.",
        published_at=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
        observed_at=datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
        retention_class=LiveRetentionClass.METADATA_ONLY,
    )
    persisted = store.save_observation(observation)

    assert persisted.content == ""
    assert persisted.content_hash == observation.content_hash
    with closing(sqlite3.connect(store.db_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "live_signal_observations",
        "live_signal_versions",
        "live_signal_observation_links",
        "live_provider_checkpoints",
        "live_dead_letters",
        "research_action_proposals",
    } <= tables


def test_frozen_dual_channels_keep_independent_checkpoints_and_match_signals(
    tmp_path,
) -> None:
    clock = FrozenClock(datetime(2026, 7, 29, 1, 29, tzinfo=UTC))
    mcp, websocket = load_frozen_dual_channel_feeds(clock=clock)
    store = LiveSignalStore(tmp_path / "dual.db")
    service = LiveSignalService(store)

    before_mcp = service.poll_source(mcp)
    before_ws = service.poll_source(websocket)
    assert before_mcp.batch.observations == []
    assert before_ws.batch.observations == []
    assert store.list_signals() == []

    clock.advance_to(datetime(2026, 7, 29, 2, 6, tzinfo=UTC))
    mcp_result = service.poll_source(mcp)
    ws_result = service.poll_source(websocket)

    assert len(mcp_result.batch.observations) == 3
    assert len(ws_result.batch.observations) == 2
    signals = {item.title: item for item in store.list_signals()}
    assert len(signals) == 3
    assert (
        signals["合成演示：存储厂商更新资本开支计划"].match_status
        == LiveMatchStatus.MATCHED
    )
    assert (
        signals["合成演示：市场传闻存储厂商可能上调产能指引"].match_status
        == LiveMatchStatus.DIVERGENT
    )
    assert (
        signals["合成演示：宏观数据公布值偏离一致预期"].match_status
        == LiveMatchStatus.SINGLE_CHANNEL
    )
    matched = signals["合成演示：存储厂商更新资本开支计划"]
    assert matched.channels == [LiveChannel.MCP, LiveChannel.WEBSOCKET]
    assert len(matched.observation_ids) == 2
    assert len(store.list_signals(latest_only=False)) == 5

    checkpoints = {item.channel: item for item in store.list_checkpoints()}
    assert checkpoints[LiveChannel.MCP].cursor == "3"
    assert checkpoints[LiveChannel.WEBSOCKET].cursor == "2"
    assert checkpoints[LiveChannel.MCP].calls_used == 2
    assert checkpoints[LiveChannel.WEBSOCKET].calls_used == 2

    repeated_mcp = service.poll_source(mcp)
    repeated_ws = service.poll_source(websocket)
    assert repeated_mcp.created_versions == repeated_ws.created_versions == 0
    assert len(store.list_signals(latest_only=False)) == 5


def test_invalid_payload_becomes_redacted_dead_letter(tmp_path) -> None:
    store = LiveSignalStore(tmp_path / "dead.db")
    service = LiveSignalService(store)

    result = service.ingest_payload(
        {"content": "do-not-persist-this-token"},
        provider="fixture",
        provider_version="1",
        channel=LiveChannel.MCP,
        stream="flash",
        observed_at=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
    )

    assert result is None
    dead = store.list_dead_letters()
    assert len(dead) == 1
    serialized = dead[0].model_dump_json()
    assert "do-not-persist-this-token" not in serialized
    assert dead[0].metadata["validation_error_count"] >= 1


def test_source_failure_degrades_only_its_checkpoint(tmp_path) -> None:
    class FailingSource:
        descriptor = LiveSourceDescriptor(
            provider="fixture",
            provider_version="1",
            channel=LiveChannel.WEBSOCKET,
            stream="flash",
            transport="test",
            requires_credentials=False,
            fixture=True,
        )

        def read(self, *_args, **_kwargs):
            raise RuntimeError("private-provider-detail")

    store = LiveSignalStore(tmp_path / "failure.db")
    store.save_checkpoint(
        LiveProviderCheckpoint(
            provider="fixture",
            provider_version="1",
            channel=LiveChannel.MCP,
            stream="flash",
            health=LiveProviderHealth.ACTIVE,
        )
    )
    service = LiveSignalService(store)

    with pytest.raises(RuntimeError, match="private-provider-detail"):
        service.poll_source(FailingSource())

    checkpoints = {item.channel: item for item in store.list_checkpoints()}
    assert checkpoints[LiveChannel.MCP].health == LiveProviderHealth.ACTIVE
    assert checkpoints[LiveChannel.WEBSOCKET].health == LiveProviderHealth.DEGRADED
    assert "private-provider-detail" not in checkpoints[LiveChannel.WEBSOCKET].error


def test_research_action_proposal_is_typed_and_human_gated() -> None:
    proposal = ResearchActionProposal(
        id="proposal-1",
        signal_key="live:signal",
        analysis_version=1,
        ruleset_version="rules-v1",
        horizon="1-12 weeks",
        novelty=0.8,
        impact_score=74,
        confidence=0.6,
        recommended_action=ResearchAction.VERIFY,
    )
    assert proposal.human_status == ProposalHumanStatus.PENDING

    with pytest.raises(ValidationError, match="model metadata requires"):
        ResearchActionProposal(
            id="proposal-2",
            signal_key="live:signal",
            analysis_version=1,
            ruleset_version="rules-v1",
            model="model-without-provider",
            horizon="1-12 weeks",
            novelty=0.8,
            impact_score=74,
            confidence=0.6,
            recommended_action=ResearchAction.VERIFY,
        )


def test_live_cli_replays_synthetic_fixture_without_keys(tmp_path) -> None:
    path = tmp_path / "cli-live.db"
    runner = CliRunner()

    replay = runner.invoke(app, ["live", "demo", "--path", str(path)])
    status = runner.invoke(app, ["live", "status", "--path", str(path)])

    assert replay.exit_code == 0
    assert "Synthetic replay only" in replay.stdout
    assert '"matched"' in replay.stdout
    assert '"divergent"' in replay.stdout
    assert status.exit_code == 0
    payload = json.loads(status.stdout)
    assert len(payload["checkpoints"]) == 2
    assert len(payload["signals"]) == 3
