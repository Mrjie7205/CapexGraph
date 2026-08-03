from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from capexgraph.domain import ThemeSourceKind
from capexgraph.themes import (
    ThemeRegistryService,
    ThemeRegistryStore,
    import_theme_json,
    load_frozen_theme_fixture,
)


def test_frozen_theme_fixture_reconstructs_point_in_time_without_future_members(
    tmp_path: Path,
) -> None:
    store = ThemeRegistryStore(tmp_path / "themes.db")
    service = ThemeRegistryService(store)
    fixture = load_frozen_theme_fixture()
    service.persist_import(fixture)
    service.persist_import(fixture)

    march = service.snapshot(
        "memory-semiconductors",
        as_of_date=date(2024, 3, 1),
        knowledge_cutoff=datetime(2024, 3, 1, 23, 59, tzinfo=UTC),
        market="CN",
    )
    july = service.snapshot(
        "memory-semiconductors",
        as_of_date=date(2024, 7, 1),
        knowledge_cutoff=datetime(2024, 7, 1, 23, 59, tzinfo=UTC),
        market="CN",
    )
    january = service.snapshot(
        "memory-semiconductors",
        as_of_date=date(2025, 1, 2),
        knowledge_cutoff=datetime(2025, 1, 2, 23, 59, tzinfo=UTC),
        market="CN",
    )

    assert {item.ticker for item in march.members} == {"603986.SH", "605358.SH"}
    assert {item.ticker for item in july.members} == {
        "603986.SH",
        "605358.SH",
        "688019.SH",
    }
    assert {item.ticker for item in january.members} == {
        "603986.SH",
        "688019.SH",
        "688126.SH",
    }
    anji = next(item for item in july.members if item.ticker == "688019.SH")
    assert anji.recognition_score == pytest.approx(0.42)
    assert anji.exposure_score == pytest.approx(0.90)
    assert len(store.list_definitions()) == 1
    assert len(store.list_snapshots("memory-semiconductors")) == 3


def test_market_recognition_source_cannot_claim_industrial_exposure() -> None:
    payload = {
        "theme": {
            "theme_id": "invalid",
            "name": "Invalid",
            "markets": ["CN"],
            "benchmark_tickers": {"CN": "000300.SH"},
            "valid_from": "2026-01-01",
            "known_at": "2026-01-01T00:00:00Z",
        },
        "sources": [
            {
                "name": "Index",
                "kind": ThemeSourceKind.INDEX.value,
                "provider": "fixture",
                "market": "CN",
                "observed_at": "2026-01-01T00:00:00Z",
                "memberships": [
                    {
                        "ticker": "688019.SH",
                        "entity_name": "安集科技",
                        "exchange": "SSE STAR",
                        "valid_from": "2026-01-01",
                        "exposure_score": 0.9,
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="cannot set exposure_score"):
        import_theme_json(payload)
