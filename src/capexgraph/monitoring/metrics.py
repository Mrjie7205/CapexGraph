from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import UTC, datetime

from capexgraph.domain import (
    DataQualityStatus,
    MarketBar,
    ThemeDailyMetric,
    ThemeUniverseMember,
    ThemeUniverseSnapshot,
)
from capexgraph.market.store import MarketDataStore
from capexgraph.monitoring.store import MainlineStore
from capexgraph.themes.store import ThemeRegistryStore


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _period_return(bars: list[MarketBar], sessions: int) -> float | None:
    if len(bars) <= sessions:
        return None
    start = bars[-sessions - 1].return_close
    end = bars[-1].return_close
    return end / start - 1 if start > 0 else None


def _above_average(bars: list[MarketBar], sessions: int = 20) -> bool | None:
    if len(bars) < sessions:
        return None
    values = [item.return_close for item in bars[-sessions:]]
    return values[-1] > statistics.fmean(values)


def _annualized_volatility(bars: list[MarketBar], sessions: int = 20) -> float | None:
    if len(bars) <= sessions:
        return None
    values = [item.return_close for item in bars[-sessions - 1 :]]
    returns = [
        current / previous - 1
        for previous, current in zip(values, values[1:], strict=False)
        if previous > 0
    ]
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns) * math.sqrt(252)


def _aggregate(
    values: list[tuple[ThemeUniverseMember, float]],
    weighting: str,
) -> float | None:
    if not values:
        return None
    numbers = [value for _, value in values]
    if weighting == "median":
        return statistics.median(numbers)
    if weighting == "source_weight":
        weighted = [(member.weight or 0.0, value) for member, value in values]
        total = sum(weight for weight, _ in weighted)
        if total > 0:
            return sum(weight * value for weight, value in weighted) / total
    return statistics.fmean(numbers)


class ThemeMetricService:
    def __init__(
        self,
        *,
        market_store: MarketDataStore | None = None,
        theme_store: ThemeRegistryStore | None = None,
        mainline_store: MainlineStore | None = None,
    ) -> None:
        self.market_store = market_store or MarketDataStore()
        self.theme_store = theme_store or ThemeRegistryStore(self.market_store.db_path)
        self.mainline_store = mainline_store or MainlineStore(self.market_store.db_path)

    def calculate(
        self,
        snapshot: ThemeUniverseSnapshot,
        *,
        market: str,
        provider: str,
        weighting: str = "equal",
    ) -> ThemeDailyMetric:
        if weighting not in {"equal", "median", "source_weight"}:
            raise ValueError("weighting must be equal, median, or source_weight")
        definition = self.theme_store.latest_definition(
            snapshot.theme_id,
            as_of_date=snapshot.as_of_date,
            knowledge_cutoff=snapshot.knowledge_cutoff,
        )
        if definition is None:
            raise KeyError(f"Theme definition not found: {snapshot.theme_id}")
        normalized_market = market.upper()
        members = [item for item in snapshot.members if item.market == normalized_market]
        benchmark_ticker = definition.benchmark_tickers.get(normalized_market)
        if not benchmark_ticker:
            raise ValueError(f"Theme {snapshot.theme_id} has no {normalized_market} benchmark")

        bar_payload: dict[str, list[dict]] = {}
        return_20: list[tuple[ThemeUniverseMember, float]] = []
        return_60: list[tuple[ThemeUniverseMember, float]] = []
        breadth_values: list[bool] = []
        volatilities: list[float] = []
        member_returns: dict[str, float | None] = {}
        persistent = 0
        for member in members:
            bars = self.market_store.list_bars(
                member.ticker,
                provider=provider,
                end_date=snapshot.as_of_date,
            )
            bars = bars[-90:]
            bar_payload[member.ticker] = [item.model_dump(mode="json") for item in bars]
            value_20 = _period_return(bars, 20)
            value_60 = _period_return(bars, 60)
            member_returns[member.ticker] = value_20
            if value_20 is not None:
                return_20.append((member, value_20))
            if value_60 is not None:
                return_60.append((member, value_60))
            above = _above_average(bars)
            if above is not None:
                breadth_values.append(above)
            volatility = _annualized_volatility(bars)
            if volatility is not None:
                volatilities.append(volatility)
            if value_20 is not None and value_60 is not None and value_20 > 0 and value_60 > 0:
                persistent += 1

        benchmark_bars = self.market_store.list_bars(
            benchmark_ticker,
            provider=provider,
            end_date=snapshot.as_of_date,
        )[-90:]
        bar_payload[benchmark_ticker] = [item.model_dump(mode="json") for item in benchmark_bars]
        theme_return_20 = _aggregate(return_20, weighting)
        benchmark_return_20 = _period_return(benchmark_bars, 20)
        coverage_ratio = len(return_20) / len(members) if members else 0.0
        issues: list[str] = []
        if not members:
            issues.append(f"No {normalized_market} members in the point-in-time universe.")
        if coverage_ratio < 0.8:
            issues.append(
                f"Only {len(return_20)} of {len(members)} members have a 20-session return."
            )
        if benchmark_return_20 is None:
            issues.append(f"Benchmark {benchmark_ticker} lacks 20-session history.")
        if snapshot.partial:
            issues.append("Theme membership coverage is explicitly partial.")
        if not return_20:
            quality_status = DataQualityStatus.FAIL
        elif issues:
            quality_status = DataQualityStatus.WARN
        else:
            quality_status = DataQualityStatus.PASS
        input_hash = _hash(
            {
                "snapshot_hash": snapshot.content_hash,
                "market": normalized_market,
                "provider": provider,
                "weighting": weighting,
                "bars": bar_payload,
            }
        )
        metric = ThemeDailyMetric(
            id=f"theme-metric-{input_hash[:24]}",
            theme_id=snapshot.theme_id,
            snapshot_id=snapshot.id,
            as_of_date=snapshot.as_of_date,
            market=normalized_market,
            provider=provider,
            benchmark_ticker=benchmark_ticker,
            weighting=weighting,
            return_20d=theme_return_20,
            return_60d=_aggregate(return_60, weighting),
            benchmark_return_20d=benchmark_return_20,
            relative_strength_20d=(
                theme_return_20 - benchmark_return_20
                if theme_return_20 is not None and benchmark_return_20 is not None
                else None
            ),
            breadth_above_20d=(
                sum(breadth_values) / len(breadth_values) if breadth_values else None
            ),
            positive_participation_20d=(
                sum(value > 0 for _, value in return_20) / len(return_20)
                if return_20
                else None
            ),
            dispersion_20d=(
                statistics.pstdev(value for _, value in return_20)
                if len(return_20) > 1
                else 0.0 if return_20 else None
            ),
            annualized_volatility=(
                statistics.fmean(volatilities) if volatilities else None
            ),
            persistence_ratio=(persistent / len(return_20) if return_20 else None),
            sample_count=len(return_20),
            missing_count=max(0, len(members) - len(return_20)),
            coverage_ratio=coverage_ratio,
            quality_status=quality_status,
            issues=issues,
            member_returns=member_returns,
            computed_at=datetime.now(UTC),
            input_hash=input_hash,
        )
        return self.mainline_store.save_metric(metric)
