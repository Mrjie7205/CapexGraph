from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

from capexgraph.domain import MarketBarSet, MarketComparisonResult, MarketSyncResult
from capexgraph.market.providers import (
    MarketDataProvider,
    MarketProviderError,
    build_market_provider,
)
from capexgraph.market.quality import compare_market_histories, evaluate_market_quality
from capexgraph.market.store import MarketDataStore
from capexgraph.runtime.artifacts import atomic_write_bytes
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.identity import TickerResolver


class MarketDataQualityError(MarketProviderError):
    """Raised when structural quality checks block normalized persistence."""


class MarketDataService:
    def __init__(
        self,
        *,
        store: MarketDataStore | None = None,
        provider: MarketDataProvider | None = None,
    ) -> None:
        self.store = store or MarketDataStore()
        self.provider = provider or build_market_provider()

    @staticmethod
    def _raw_path(bar_set: MarketBarSet):
        safe_ticker = bar_set.ticker.replace(".", "-")
        return (
            runs_dir()
            / "_market_data"
            / "raw"
            / bar_set.provider
            / safe_ticker
            / f"{bar_set.raw_hash}.json"
        )

    def _fetch_start(
        self,
        ticker: str,
        *,
        days: int,
        end_date: date,
    ) -> tuple[date, date]:
        target_start = end_date - timedelta(days=max(days, 1))
        bounds = self.store.date_bounds(ticker, self.provider.provider_name)
        if bounds is None:
            return target_start, target_start
        first_date, latest_date = bounds
        if first_date > target_start:
            return target_start, target_start
        overlap_start = latest_date - timedelta(days=7)
        return max(target_start, overlap_start), target_start

    def sync(
        self,
        ticker: str,
        *,
        days: int = 400,
        end_date: date | None = None,
    ) -> MarketSyncResult:
        if days < 1:
            raise ValueError("days must be at least 1")
        identity = TickerResolver().resolve(ticker)
        effective_end = end_date or datetime.now(UTC).date()
        fetch_start, target_start = self._fetch_start(
            identity.ticker,
            days=days,
            end_date=effective_end,
        )
        fetched = self.provider.fetch_history(
            identity.ticker,
            days=days,
            start_date=fetch_start,
            end_date=effective_end,
        )
        if fetched.bar_set.ticker != identity.ticker:
            raise MarketProviderError(
                f"{self.provider.provider_name} returned identity "
                f"{fetched.bar_set.ticker} for requested ticker {identity.ticker}."
            )
        if (
            fetched.bar_set.provider != self.provider.provider_name
            or fetched.bar_set.provider_version != self.provider.provider_version
        ):
            raise MarketProviderError(
                "Market provider identity does not match the returned bar set."
            )
        actual_hash = hashlib.sha256(fetched.raw_payload).hexdigest()
        if fetched.bar_set.raw_hash != actual_hash:
            raise MarketProviderError("Market provider raw-response hash does not match its bytes.")
        raw_path = self._raw_path(fetched.bar_set)
        atomic_write_bytes(raw_path, fetched.raw_payload)

        batch_quality = evaluate_market_quality(
            fetched.bar_set.bars,
            as_of=effective_end,
            expected_sessions=fetched.expected_sessions,
            suspended_dates=fetched.suspended_dates,
        )
        self.store.save_quality(fetched.bar_set, batch_quality)
        if batch_quality.blocks_persistence:
            codes = ", ".join(issue.code for issue in batch_quality.issues)
            raise MarketDataQualityError(
                f"{fetched.bar_set.provider} history for {identity.ticker} "
                f"failed quality checks: {codes}."
            )

        persisted = self.store.save_bars(fetched.bar_set)
        merged_bars = self.store.list_bars(
            identity.ticker,
            provider=fetched.bar_set.provider,
            start_date=target_start,
            end_date=effective_end,
        )
        merged_quality = evaluate_market_quality(
            merged_bars,
            as_of=effective_end,
            expected_sessions=fetched.expected_sessions,
            suspended_dates=fetched.suspended_dates,
        )
        merged_set = fetched.bar_set.model_copy(update={"bars": merged_bars})
        self.store.save_quality(merged_set, merged_quality)
        if merged_quality.blocks_persistence:
            codes = ", ".join(issue.code for issue in merged_quality.issues)
            raise MarketDataQualityError(
                f"Stored {fetched.bar_set.provider} history for {identity.ticker} "
                f"failed quality checks: {codes}."
            )
        return MarketSyncResult(
            bar_set=merged_set,
            quality=merged_quality,
            persisted_bars=persisted,
            raw_path=raw_path.relative_to(runs_dir()).as_posix(),
        )

    def sync_many(
        self,
        tickers: list[str],
        *,
        days: int = 400,
        end_date: date | None = None,
    ) -> list[MarketSyncResult]:
        return [self.sync(ticker, days=days, end_date=end_date) for ticker in tickers]

    def compare(
        self,
        ticker: str,
        *,
        primary_provider: str,
        reference_provider: str,
        as_of_date: date,
        tolerance_pct: float = 0.02,
        minimum_overlap: int = 20,
    ) -> MarketComparisonResult:
        identity = TickerResolver().resolve(ticker)
        primary = self.store.list_bars(
            identity.ticker,
            provider=primary_provider,
            end_date=as_of_date,
        )
        reference = self.store.list_bars(
            identity.ticker,
            provider=reference_provider,
            end_date=as_of_date,
        )
        result = compare_market_histories(
            identity.ticker,
            primary_provider,
            primary,
            reference_provider,
            reference,
            as_of_date=as_of_date,
            tolerance_pct=tolerance_pct,
            minimum_overlap=minimum_overlap,
        )
        return self.store.save_comparison(result)
