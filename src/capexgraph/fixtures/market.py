from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from capexgraph.domain import MarketBar, MarketBarSet
from capexgraph.market.store import MarketDataStore

FROZEN_MARKET_PROVIDER = "fixture-market"
FROZEN_MARKET_AS_OF = date(2026, 8, 3)

SERIES = {
    "603986.SH": ("CN", "SSE", "CNY", "Asia/Shanghai", 0.0075),
    "688019.SH": ("CN", "SSE STAR", "CNY", "Asia/Shanghai", 0.0065),
    "688126.SH": ("CN", "SSE STAR", "CNY", "Asia/Shanghai", 0.0055),
    "000300.SH": ("CN", "SSE", "CNY", "Asia/Shanghai", 0.0010),
    "MU.US": ("US", "NASDAQ", "USD", "America/New_York", 0.0060),
    "AMAT.US": ("US", "NASDAQ", "USD", "America/New_York", 0.0040),
    "LRCX.US": ("US", "NASDAQ", "USD", "America/New_York", 0.0045),
    "SOXX.US": ("US", "NASDAQ", "USD", "America/New_York", 0.0020),
    "005930.KO": ("KR", "KRX", "KRW", "Asia/Seoul", 0.0038),
    "000660.KO": ("KR", "KRX", "KRW", "Asia/Seoul", 0.0068),
    "KOSPI.KO": ("KR", "KRX", "KRW", "Asia/Seoul", 0.0012),
}


def _sessions(end: date, count: int) -> list[date]:
    values: list[date] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(values))


def seed_frozen_market_fixture(
    store: MarketDataStore | None = None,
) -> dict[str, int | str]:
    """Seed synthetic multi-market bars for the no-key mainline demo."""

    active_store = store or MarketDataStore()
    inserted = 0
    sessions = _sessions(FROZEN_MARKET_AS_OF, 90)
    for ticker, (market, exchange, currency, timezone, growth) in SERIES.items():
        value = 100.0
        bars: list[MarketBar] = []
        for index, trade_date in enumerate(sessions):
            value *= 1 + growth + ((index % 7) - 3) * 0.00015
            bars.append(
                MarketBar(
                    date=trade_date,
                    open=value * 0.997,
                    high=value * 1.006,
                    low=value * 0.994,
                    close=value,
                    adjusted_close=value,
                    volume=1_000_000 + index * 1_000,
                )
            )
        raw = json.dumps(
            [item.model_dump(mode="json") for item in bars],
            sort_keys=True,
            default=str,
        ).encode()
        inserted += active_store.save_bars(
            MarketBarSet(
                ticker=ticker,
                market=market,
                exchange=exchange,
                currency=currency,
                timezone=timezone,
                provider=FROZEN_MARKET_PROVIDER,
                provider_version="1",
                source_url=None,
                raw_hash=hashlib.sha256(raw).hexdigest(),
                bars=bars,
            )
        )
    return {
        "provider": FROZEN_MARKET_PROVIDER,
        "as_of_date": FROZEN_MARKET_AS_OF.isoformat(),
        "ticker_count": len(SERIES),
        "bar_count": inserted,
    }
