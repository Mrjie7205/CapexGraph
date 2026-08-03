from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from capexgraph.domain import (
    MainlineState,
    MarketBar,
    MarketBarSet,
    MonitorJobStatus,
    ProposalHumanStatus,
)
from capexgraph.market import MarketDataStore
from capexgraph.monitoring import MainlineService, MainlineStore, ThemeMetricService
from capexgraph.themes import ThemeRegistryService, ThemeRegistryStore, load_frozen_theme_fixture


def _seed_bars(
    store: MarketDataStore,
    ticker: str,
    *,
    end: date,
    daily_growth: float,
    market: str = "CN",
    exchange: str = "SSE",
) -> None:
    start = end - timedelta(days=79)
    bars: list[MarketBar] = []
    value = 100.0
    for offset in range(80):
        trade_date = start + timedelta(days=offset)
        value *= 1 + daily_growth
        bars.append(
            MarketBar(
                date=trade_date,
                open=value * 0.997,
                high=value * 1.005,
                low=value * 0.995,
                close=value,
                adjusted_close=value,
                volume=1_000_000 + offset,
            )
        )
    raw = json.dumps([item.model_dump(mode="json") for item in bars], default=str).encode()
    store.save_bars(
        MarketBarSet(
            ticker=ticker,
            market=market,
            exchange=exchange,
            currency="CNY",
            timezone="Asia/Shanghai",
            provider="fixture-market",
            provider_version="1",
            source_url=None,
            raw_hash=hashlib.sha256(raw).hexdigest(),
            bars=bars,
        )
    )


def test_daily_mainline_job_is_deterministic_and_never_auto_spends(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mainline.db"
    theme_store = ThemeRegistryStore(db_path)
    theme_service = ThemeRegistryService(theme_store)
    theme_service.persist_import(load_frozen_theme_fixture())
    market_store = MarketDataStore(db_path)
    as_of = date(2026, 8, 3)
    for ticker, growth in (
        ("603986.SH", 0.010),
        ("688019.SH", 0.009),
        ("688126.SH", 0.008),
        ("000300.SH", 0.001),
    ):
        _seed_bars(market_store, ticker, end=as_of, daily_growth=growth)

    mainline_store = MainlineStore(db_path)
    service = MainlineService(
        store=mainline_store,
        theme_service=theme_service,
        metric_service=ThemeMetricService(
            market_store=market_store,
            theme_store=theme_store,
            mainline_store=mainline_store,
        ),
    )
    first = service.run_daily(
        "memory-semiconductors",
        market="CN",
        as_of_date=as_of,
        provider="fixture-market",
    )
    second = service.run_daily(
        "memory-semiconductors",
        market="CN",
        as_of_date=as_of,
        provider="fixture-market",
    )

    assert first.id == second.id
    assert first.status == MonitorJobStatus.PARTIAL
    assessment = mainline_store.list_assessments("memory-semiconductors")[0]
    assert assessment.state == MainlineState.CONFIRMED
    assert assessment.score is not None and assessment.score >= 70
    proposals = mainline_store.list_proposals("memory-semiconductors")
    assert len(proposals) == 1
    assert proposals[0].human_status == ProposalHumanStatus.PENDING
    assert proposals[0].auto_execute is False
    assert proposals[0].run_id is None
    assert len(mainline_store.list_state_events("memory-semiconductors")) == 1
    event = mainline_store.list_state_events("memory-semiconductors")[0]
    acknowledged = mainline_store.acknowledge_state_event(event.id)
    assert acknowledged.acknowledged_at is not None

    batch = service.run_batch(
        market="CN",
        as_of_date=as_of,
        provider="fixture-market",
        theme_ids=["memory-semiconductors"],
    )
    assert [item.id for item in batch] == [first.id]


def test_mainline_job_exposes_insufficient_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "insufficient.db"
    theme_store = ThemeRegistryStore(db_path)
    theme_service = ThemeRegistryService(theme_store)
    theme_service.persist_import(load_frozen_theme_fixture())
    market_store = MarketDataStore(db_path)
    mainline_store = MainlineStore(db_path)
    service = MainlineService(
        store=mainline_store,
        theme_service=theme_service,
        metric_service=ThemeMetricService(
            market_store=market_store,
            theme_store=theme_store,
            mainline_store=mainline_store,
        ),
    )

    job = service.run_daily(
        "memory-semiconductors",
        market="CN",
        as_of_date=date(2026, 8, 3),
        provider="missing-provider",
    )

    assessment = mainline_store.list_assessments("memory-semiconductors")[0]
    assert job.status == MonitorJobStatus.PARTIAL
    assert assessment.state == MainlineState.INSUFFICIENT
    assert assessment.score is None
    assert assessment.blockers
    assert mainline_store.list_proposals("memory-semiconductors") == []


def test_policy_cannot_be_applied_before_effective_date(tmp_path: Path) -> None:
    db_path = tmp_path / "policy.db"
    theme_store = ThemeRegistryStore(db_path)
    theme_service = ThemeRegistryService(theme_store)
    theme_service.persist_import(load_frozen_theme_fixture())
    market_store = MarketDataStore(db_path)
    mainline_store = MainlineStore(db_path)
    metric_service = ThemeMetricService(
        market_store=market_store,
        theme_store=theme_store,
        mainline_store=mainline_store,
    )
    service = MainlineService(
        store=mainline_store,
        theme_service=theme_service,
        metric_service=metric_service,
    )
    snapshot = theme_service.snapshot(
        "memory-semiconductors",
        as_of_date=date(2025, 1, 2),
        market="CN",
    )
    metric = metric_service.calculate(
        snapshot,
        market="CN",
        provider="missing-provider",
    )
    with pytest.raises(ValueError, match="was not effective"):
        service.assess(metric)
