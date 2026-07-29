from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from capexgraph.domain import (
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    MarketBar,
    MarketSnapshot,
)
from capexgraph.market import (
    EodhdProvider,
    MarketDataProvider,
    MarketDataService,
    YahooChartProvider,
    build_market_provider,
    eodhd_symbol,
    yahoo_symbol,
)
from capexgraph.runtime.artifacts import atomic_write_bytes
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.identity import TickerResolver, canonical_ticker
from capexgraph.workflows import load_run, save_run

__all__ = [
    "EodhdProvider",
    "MarketDataProvider",
    "YahooChartProvider",
    "build_market_provider",
    "calculate_market_snapshot",
    "capture_market_snapshot",
    "eodhd_symbol",
    "yahoo_symbol",
]


def _return_pct(closes: Sequence[float], lookback: int) -> float | None:
    if len(closes) <= lookback or closes[-lookback - 1] <= 0:
        return None
    return round((closes[-1] / closes[-lookback - 1] - 1) * 100, 2)


def calculate_market_snapshot(
    ticker: str,
    bars: Sequence[MarketBar],
    *,
    provider: str,
    currency: str,
    source_url: str | None = None,
) -> MarketSnapshot:
    if not bars:
        raise ValueError("At least one market bar is required")
    ordered = sorted(bars, key=lambda bar: bar.date)
    raw_closes = [bar.close for bar in ordered]
    return_closes = [bar.return_close for bar in ordered]
    six_month = ordered[-126:]
    six_low = min(bar.low for bar in six_month)
    six_high = max(bar.high for bar in six_month)
    price = raw_closes[-1]
    range_position = (
        round((price - six_low) / (six_high - six_low) * 100, 2)
        if six_high > six_low
        else 50.0
    )
    off_high = round((price / six_high - 1) * 100, 2) if six_high else None
    sma50 = sum(raw_closes[-50:]) / min(50, len(raw_closes))
    ret_1m = _return_pct(return_closes, 21)
    ret_3m = _return_pct(return_closes, 63)
    above_sma50 = price > sma50
    if (ret_3m is not None and ret_3m > 120) or (ret_1m is not None and ret_1m > 40):
        stage = "extended"
    elif above_sma50 and ret_3m is not None and ret_3m > 5:
        stage = "early_uptrend"
    elif not above_sma50 and ret_3m is not None and ret_3m < -10:
        stage = "basing"
    else:
        stage = "range"
    return MarketSnapshot(
        ticker=canonical_ticker(ticker),
        as_of_date=ordered[-1].date,
        price=round(price, 4),
        currency=currency,
        provider=provider,
        ret_1m_pct=ret_1m,
        ret_3m_pct=ret_3m,
        range_pos_6mo_pct=range_position,
        pct_off_6mo_high=off_high,
        above_sma50=above_sma50,
        stage=stage,
        source_url=source_url,
    )


def capture_market_snapshot(
    run_id: str,
    ticker: str,
    *,
    provider: MarketDataProvider | None = None,
    days: int = 400,
) -> MarketSnapshot:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    active_provider = provider or build_market_provider()
    identity = TickerResolver().resolve(ticker)
    sync = MarketDataService(provider=active_provider).sync(identity.ticker, days=days)
    bar_set = sync.bar_set
    source_url = str(bar_set.source_url) if bar_set.source_url else None
    snapshot = calculate_market_snapshot(
        identity.ticker,
        bar_set.bars,
        provider=bar_set.provider,
        currency=identity.currency,
        source_url=source_url,
    )
    payload = {
        "snapshot": snapshot.model_dump(mode="json"),
        "bar_set": bar_set.model_dump(mode="json"),
        "quality": sync.quality.model_dump(mode="json"),
        "persisted_bars": sync.persisted_bars,
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    safe_ticker = identity.ticker.replace(".", "-")
    relative_path = f"market/{safe_ticker}.json"
    atomic_write_bytes(runs_dir() / run.id / relative_path, raw)
    evidence_id = f"market-{safe_ticker}-{snapshot.as_of_date.isoformat()}"
    chinese_name = any("\u4e00" <= character <= "\u9fff" for character in identity.name)
    market_evidence = Evidence(
        id=evidence_id,
        title=(
            f"{identity.name} 日度行情"
            if chinese_name
            else f"{identity.name} daily adjusted market history"
        ),
        kind=EvidenceKind.MARKET_DATA,
        source_url=source_url,
        published_at=snapshot.as_of_date,
        excerpt=json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
        source_hash=hashlib.sha256(raw).hexdigest(),
        publisher=bar_set.provider,
        content_type="application/json",
        local_path=relative_path,
        status=EvidenceStatus.CAPTURED,
    )
    evidence = {item.id: item for item in run.evidence}
    evidence[market_evidence.id] = market_evidence
    run.evidence = list(evidence.values())
    snapshots = run.manifest.setdefault("market_snapshots", {})
    snapshots[identity.ticker] = snapshot.model_dump(mode="json")
    quality = run.manifest.setdefault("market_quality", {})
    quality[identity.ticker] = sync.quality.model_dump(mode="json")
    providers = run.manifest.setdefault("data_providers", [])
    if bar_set.provider not in providers:
        providers.append(bar_set.provider)
    records = run.manifest.setdefault("data_provider_records", [])
    provider_identity = {
        "name": bar_set.provider,
        "version": bar_set.provider_version,
    }
    if provider_identity not in records:
        records.append(provider_identity)
    save_run(run)
    return snapshot
