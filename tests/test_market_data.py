from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import httpx
import pytest

from capexgraph.domain import (
    DataQualityStatus,
    MarketBar,
    MarketBarSet,
    QualitySeverity,
    RunMode,
)
from capexgraph.market import (
    EodhdProvider,
    MarketDataQualityError,
    MarketDataService,
    MarketDataStore,
    MarketFetchResult,
    MarketProviderConfigurationError,
    MarketProviderError,
    MarketSettings,
    TushareDailyProvider,
    UnsupportedMarketError,
    YahooChartProvider,
    build_market_provider,
    compare_market_histories,
    eodhd_symbol,
    evaluate_market_quality,
    tushare_symbol,
)
from capexgraph.tools.identity import TickerResolver
from capexgraph.tools.market import calculate_market_snapshot, capture_market_snapshot
from capexgraph.workflows import create_run, load_run


def _market_bar(day: date, close: float = 100) -> MarketBar:
    return MarketBar(
        date=day,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        adjusted_close=close,
        volume=1000,
    )


def test_cross_market_identity_and_eodhd_mapping() -> None:
    resolver = TickerResolver()

    assert resolver.resolve("AAPL").market == "US"
    assert resolver.resolve("AAPL.US").currency == "USD"
    assert resolver.resolve("000660.KO").exchange == "KRX"
    assert resolver.resolve("247540.KQ").exchange == "KOSDAQ"
    assert eodhd_symbol("688019.SH") == "688019.SHG"
    assert eodhd_symbol("000001.SZ") == "000001.SHE"
    assert eodhd_symbol("AAPL") == "AAPL.US"
    assert eodhd_symbol("000660.KO") == "000660.KO"
    with pytest.raises(UnsupportedMarketError, match="Beijing Stock Exchange"):
        eodhd_symbol("920001.BJ")
    assert tushare_symbol("688019.SH") == "688019.SH"
    assert tushare_symbol("920001.BJ") == "920001.BJ"
    with pytest.raises(UnsupportedMarketError, match="restricted to A-share"):
        tushare_symbol("AAPL")


def test_eodhd_parses_raw_and_adjusted_prices_without_leaking_token() -> None:
    token = "do-not-print-this-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/688019.SHG")
        assert request.url.params["api_token"] == token
        assert request.url.params["order"] == "a"
        return httpx.Response(
            200,
            json=[
                {
                    "date": "2026-07-27",
                    "open": 300,
                    "high": 310,
                    "low": 295,
                    "close": 305,
                    "adjusted_close": 304.5,
                    "volume": 10000,
                },
                {
                    "date": "2026-07-28",
                    "open": 306,
                    "high": 315,
                    "low": 301,
                    "close": 312,
                    "adjusted_close": 311.5,
                    "volume": 12000,
                },
            ],
            request=request,
        )

    provider = EodhdProvider(
        token,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _seconds: None,
    )
    fetched = provider.fetch_history(
        "688019.SH",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
    )

    assert fetched.bar_set.provider == "eodhd"
    assert fetched.bar_set.bars[-1].close == 312
    assert fetched.bar_set.bars[-1].adjusted_close == 311.5
    assert fetched.bar_set.bars[-1].volume == 12000
    assert len(fetched.bar_set.raw_hash) == 64
    assert token not in str(fetched.bar_set.source_url)


def test_eodhd_error_is_credential_safe() -> None:
    token = "secret-that-must-never-appear"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized", request=request)

    provider = EodhdProvider(
        token,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(MarketProviderError) as captured:
        provider.fetch_history("AAPL")

    assert token not in str(captured.value)


def test_provider_selection_is_explicit_and_keeps_no_key_fallback() -> None:
    fallback = build_market_provider(
        settings=MarketSettings(provider="yahoo", eodhd_api_token=None)
    )
    assert isinstance(fallback, YahooChartProvider)

    with pytest.raises(MarketProviderConfigurationError, match="EODHD_API_TOKEN"):
        build_market_provider(
            settings=MarketSettings(provider="eodhd", eodhd_api_token=None)
        )
    with pytest.raises(MarketProviderConfigurationError, match="TUSHARE_API_TOKEN"):
        build_market_provider(settings=MarketSettings(provider="tushare"))


def test_tushare_parses_daily_and_adjustment_factor_without_leaking_token() -> None:
    token = "tushare-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["token"] == token
        if payload["api_name"] == "daily":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "fields": [
                            "ts_code",
                            "trade_date",
                            "open",
                            "high",
                            "low",
                            "close",
                            "vol",
                        ],
                        "items": [
                            ["688019.SH", "20260728", 310, 315, 305, 312, 12000],
                            ["688019.SH", "20260727", 300, 310, 295, 305, 10000],
                        ],
                    },
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": ["ts_code", "trade_date", "adj_factor"],
                    "items": [
                        ["688019.SH", "20260728", 2.0],
                        ["688019.SH", "20260727", 1.9],
                    ],
                },
            },
            request=request,
        )

    provider = TushareDailyProvider(
        token,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.fetch_history(
        "688019.SH",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
    )

    assert [item.date for item in result.bar_set.bars] == [
        date(2026, 7, 27),
        date(2026, 7, 28),
    ]
    assert result.bar_set.bars[0].adjusted_close == pytest.approx(305 * 1.9 / 2.0)
    assert token not in str(result.bar_set.source_url)
    assert token not in result.raw_payload.decode()


def test_quality_gate_detects_duplicates_order_ohlc_volume_and_staleness() -> None:
    bars = [
        _market_bar(date(2026, 7, 20)),
        MarketBar(
            date=date(2026, 7, 19),
            open=100,
            high=90,
            low=95,
            close=101,
            adjusted_close=-1,
            volume=-10,
        ),
        _market_bar(date(2026, 7, 20)),
    ]

    quality = evaluate_market_quality(bars, as_of=date(2026, 7, 29))
    codes = {issue.code for issue in quality.issues}

    assert quality.status == DataQualityStatus.FAIL
    assert {
        "duplicate_dates",
        "non_ascending_dates",
        "invalid_ohlc",
        "negative_volume",
        "invalid_adjusted_close",
        "stale_history",
    } <= codes
    assert any(issue.severity == QualitySeverity.ERROR for issue in quality.issues)


def test_quality_distinguishes_expected_sessions_suspension_and_adjustment() -> None:
    bars = [
        _market_bar(date(2026, 7, 27), 100),
        MarketBar(
            date=date(2026, 7, 29),
            open=50,
            high=52,
            low=49,
            close=50,
            adjusted_close=100,
            volume=1000,
        ),
    ]
    quality = evaluate_market_quality(
        bars,
        as_of=date(2026, 7, 29),
        expected_sessions=[date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29)],
        suspended_dates=[date(2026, 7, 28)],
    )
    codes = {item.code for item in quality.issues}
    assert "missing_trading_sessions" not in codes
    assert "corporate_action_adjustment_detected" in codes


def test_cross_provider_comparison_reports_overlap_and_price_differences() -> None:
    primary = [_market_bar(date(2026, 7, day), 100 + day) for day in range(1, 25)]
    reference = [
        _market_bar(date(2026, 7, day), (100 + day) * (1.03 if day == 24 else 1.0))
        for day in range(1, 25)
    ]
    result = compare_market_histories(
        "688019.SH",
        "eodhd",
        primary,
        "tushare",
        reference,
        as_of_date=date(2026, 7, 24),
        tolerance_pct=0.02,
    )
    assert result.overlap_count == 24
    assert result.status == DataQualityStatus.WARN
    assert {item.code for item in result.issues} == {"reference_close_difference"}


def test_market_store_is_idempotent_and_preserves_adjustment_semantics(tmp_path) -> None:
    store = MarketDataStore(tmp_path / "market.db")
    bars = [
        _market_bar(date(2026, 7, 27), 100),
        _market_bar(date(2026, 7, 28), 102),
    ]
    bar_set = MarketBarSet(
        ticker="AAPL",
        market="US",
        exchange="US",
        currency="USD",
        timezone="America/New_York",
        provider="fixture-market",
        provider_version="1",
        source_url="https://example.com/eod/AAPL",
        raw_hash="a" * 64,
        bars=bars,
    )
    quality = evaluate_market_quality(bars, as_of=date(2026, 7, 28))

    store.save_quality(bar_set, quality)
    assert store.save_bars(bar_set) == 2
    assert store.save_bars(bar_set) == 2
    stored = store.list_bars("AAPL", provider="fixture-market")

    assert len(stored) == 2
    assert stored[-1].adjusted_close == 102
    assert store.latest_quality("AAPL", provider="fixture-market") == quality


class _InvalidProvider:
    provider_name = "invalid-fixture"
    provider_version = "1"

    @classmethod
    def capability(cls):
        raise NotImplementedError

    def source_url(self, ticker: str) -> str:
        return f"https://example.com/{ticker}"

    def fetch_history(self, ticker: str, **_kwargs) -> MarketFetchResult:
        raw = json.dumps({"ticker": ticker}).encode()
        return MarketFetchResult(
            bar_set=MarketBarSet(
                ticker=ticker,
                market="US",
                exchange="US",
                currency="USD",
                timezone="America/New_York",
                provider=self.provider_name,
                provider_version=self.provider_version,
                source_url=self.source_url(ticker),
                raw_hash=hashlib.sha256(raw).hexdigest(),
                bars=[
                    MarketBar(
                        date=date(2026, 7, 28),
                        open=100,
                        high=90,
                        low=95,
                        close=101,
                        adjusted_close=101,
                        volume=100,
                    )
                ],
            ),
            raw_payload=raw,
        )


def test_quality_failure_is_recorded_but_blocks_bar_persistence(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    store = MarketDataStore(tmp_path / "market.db")
    service = MarketDataService(store=store, provider=_InvalidProvider())

    with pytest.raises(MarketDataQualityError, match="invalid_ohlc"):
        service.sync("AAPL", end_date=date(2026, 7, 28))

    assert store.list_bars("AAPL", provider="invalid-fixture") == []
    quality = store.latest_quality("AAPL", provider="invalid-fixture")
    assert quality is not None
    assert quality.status == DataQualityStatus.FAIL
    assert list((tmp_path / "runs" / "_market_data" / "raw").rglob("*.json"))


class _FixtureProvider:
    provider_name = "fixture-market"
    provider_version = "1"

    @classmethod
    def capability(cls):
        raise NotImplementedError

    def source_url(self, ticker: str) -> str:
        return f"https://example.com/{ticker}"

    def fetch_history(
        self,
        ticker: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        **_kwargs,
    ) -> MarketFetchResult:
        effective_end = end_date or date.today()
        effective_start = start_date or effective_end - timedelta(days=90)
        bars = [
            _market_bar(effective_start + timedelta(days=index), 100 + index)
            for index in range((effective_end - effective_start).days + 1)
        ]
        raw = json.dumps(
            [bar.model_dump(mode="json") for bar in bars],
            sort_keys=True,
        ).encode()
        return MarketFetchResult(
            bar_set=MarketBarSet(
                ticker=ticker,
                market="US",
                exchange="US",
                currency="USD",
                timezone="America/New_York",
                provider=self.provider_name,
                provider_version=self.provider_version,
                source_url=self.source_url(ticker),
                raw_hash=hashlib.sha256(raw).hexdigest(),
                bars=bars,
            ),
            raw_payload=raw,
        )


def test_run_market_capture_uses_shared_quality_and_persistence_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    run = create_run(RunMode.THEME, "test market capture", "US")

    snapshot = capture_market_snapshot(
        run.id,
        "AAPL",
        provider=_FixtureProvider(),
        days=90,
    )
    refreshed = load_run(run.id)

    assert snapshot.provider == "fixture-market"
    assert snapshot.price_basis == "raw_close"
    assert refreshed is not None
    assert refreshed.manifest["market_quality"]["AAPL"]["status"] == "pass"
    assert refreshed.manifest["market_snapshots"]["AAPL"]["price"] == snapshot.price
    assert (tmp_path / "runs" / run.id / "market" / "AAPL.json").is_file()
    assert MarketDataStore().list_bars("AAPL", provider="fixture-market")


def test_snapshot_uses_raw_price_but_adjusted_close_for_returns() -> None:
    start = date(2026, 1, 1)
    bars = [
        MarketBar(
            date=start + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            adjusted_close=51 + index,
            volume=1000,
        )
        for index in range(70)
    ]

    snapshot = calculate_market_snapshot(
        "AAPL",
        bars,
        provider="fixture",
        currency="USD",
    )

    assert snapshot.price == 170
    expected_return = round(((120 / 99) - 1) * 100, 2)
    assert snapshot.ret_1m_pct == expected_return


def test_env_file_loader_status_never_exposes_token(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CAPEXGRAPH_MARKET_PROVIDER=eodhd\nEODHD_API_TOKEN=private-token\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CAPEXGRAPH_MARKET_PROVIDER", raising=False)
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    monkeypatch.setenv("CAPEXGRAPH_ENV_FILE", str(env_path))

    settings = MarketSettings.from_environment()
    public = settings.public_status()

    assert public == {
        "configured_provider": "eodhd",
        "eodhd_token_configured": True,
        "tushare_token_configured": False,
    }
    assert "private-token" not in repr(settings)
    assert "private-token" not in json.dumps(public)
