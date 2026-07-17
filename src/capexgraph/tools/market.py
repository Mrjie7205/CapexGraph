from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

import httpx

from capexgraph.domain import (
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    MarketBar,
    MarketSnapshot,
)
from capexgraph.runtime.artifacts import atomic_write_bytes
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.identity import TickerResolver, canonical_ticker
from capexgraph.workflows import load_run, save_run


class MarketDataProvider(Protocol):
    provider_name: str

    def fetch_history(self, ticker: str, *, days: int = 400) -> list[MarketBar]: ...


def yahoo_symbol(ticker: str) -> str:
    canonical = canonical_ticker(ticker)
    if canonical.endswith(".SH"):
        return f"{canonical[:-3]}.SS"
    if canonical.endswith(".SZ"):
        return canonical
    if canonical.endswith(".BJ"):
        return canonical
    return canonical


class YahooChartProvider:
    """Best-effort, no-key daily price provider backed by Yahoo's chart endpoint."""

    provider_name = "yahoo-chart"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=20, follow_redirects=True)

    def source_url(self, ticker: str) -> str:
        return f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(ticker)}"

    def fetch_history(self, ticker: str, *, days: int = 400) -> list[MarketBar]:
        end = int(time.time())
        start = end - max(days, 70) * 86400
        response = self.client.get(
            self.source_url(ticker),
            params={
                "period1": start,
                "period2": end,
                "interval": "1d",
                "events": "div,splits",
            },
            headers={"User-Agent": "Mozilla/5.0 CapexGraph/0.2"},
        )
        response.raise_for_status()
        chart = response.json().get("chart", {})
        if chart.get("error"):
            raise ValueError(f"Market provider error: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise ValueError(f"No market history returned for {ticker}")
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjusted = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get(
            "adjclose"
        ) or quote.get("close", [])
        bars: list[MarketBar] = []
        for index, timestamp in enumerate(timestamps):
            values = {
                "open": (quote.get("open") or [])[index],
                "high": (quote.get("high") or [])[index],
                "low": (quote.get("low") or [])[index],
                "close": adjusted[index],
            }
            if any(value is None for value in values.values()):
                continue
            bars.append(
                MarketBar(
                    date=datetime.fromtimestamp(timestamp, UTC).date(),
                    **values,
                    volume=(quote.get("volume") or [None] * len(timestamps))[index],
                )
            )
        if not bars:
            raise ValueError(f"No valid market bars returned for {ticker}")
        return bars


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
    closes = [bar.close for bar in ordered]
    six_month = ordered[-126:]
    six_low = min(bar.low for bar in six_month)
    six_high = max(bar.high for bar in six_month)
    price = closes[-1]
    range_position = (
        round((price - six_low) / (six_high - six_low) * 100, 2)
        if six_high > six_low
        else 50.0
    )
    off_high = round((price / six_high - 1) * 100, 2) if six_high else None
    sma50 = sum(closes[-50:]) / min(50, len(closes))
    ret_1m = _return_pct(closes, 21)
    ret_3m = _return_pct(closes, 63)
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
) -> MarketSnapshot:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    active_provider = provider or YahooChartProvider()
    identity = TickerResolver().resolve(ticker)
    bars = active_provider.fetch_history(identity.ticker)
    source_url = (
        active_provider.source_url(identity.ticker)
        if hasattr(active_provider, "source_url")
        else None
    )
    snapshot = calculate_market_snapshot(
        identity.ticker,
        bars,
        provider=active_provider.provider_name,
        currency=identity.currency,
        source_url=source_url,
    )
    payload = {
        "snapshot": snapshot.model_dump(mode="json"),
        "bars": [bar.model_dump(mode="json") for bar in bars],
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    safe_ticker = identity.ticker.replace(".", "-")
    relative_path = f"market/{safe_ticker}.json"
    atomic_write_bytes(runs_dir() / run.id / relative_path, raw)
    evidence_id = f"market-{safe_ticker}-{snapshot.as_of_date.isoformat()}"
    market_evidence = Evidence(
        id=evidence_id,
        title=f"{identity.name} daily adjusted market history",
        kind=EvidenceKind.MARKET_DATA,
        source_url=source_url,
        published_at=snapshot.as_of_date,
        excerpt=json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
        source_hash=hashlib.sha256(raw).hexdigest(),
        publisher=active_provider.provider_name,
        content_type="application/json",
        local_path=relative_path,
        status=EvidenceStatus.CAPTURED,
    )
    evidence = {item.id: item for item in run.evidence}
    evidence[market_evidence.id] = market_evidence
    run.evidence = list(evidence.values())
    snapshots = run.manifest.setdefault("market_snapshots", {})
    snapshots[identity.ticker] = snapshot.model_dump(mode="json")
    providers = run.manifest.setdefault("data_providers", [])
    if active_provider.provider_name not in providers:
        providers.append(active_provider.provider_name)
    save_run(run)
    return snapshot
