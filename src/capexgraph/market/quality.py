from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from capexgraph.domain import (
    DataQualityIssue,
    DataQualityResult,
    DataQualityStatus,
    MarketBar,
    MarketComparisonResult,
    QualitySeverity,
)


def _issue(
    code: str,
    severity: QualitySeverity,
    message: str,
    dates: Sequence[date] = (),
) -> DataQualityIssue:
    return DataQualityIssue(
        code=code,
        severity=severity,
        message=message,
        dates=list(dates)[:20],
    )


def evaluate_market_quality(
    bars: Sequence[MarketBar],
    *,
    as_of: date | None = None,
    stale_after_days: int = 7,
    expected_sessions: Sequence[date] = (),
    suspended_dates: Sequence[date] = (),
) -> DataQualityResult:
    """Run deterministic structural checks before bars enter the shared store."""

    checked_at = datetime.now(UTC)
    effective_as_of = as_of or checked_at.date()
    if not bars:
        return DataQualityResult(
            status=DataQualityStatus.FAIL,
            checked_at=checked_at,
            bar_count=0,
            issues=[
                _issue(
                    "empty_history",
                    QualitySeverity.ERROR,
                    "Provider returned no daily bars.",
                )
            ],
        )

    issues: list[DataQualityIssue] = []
    dates = [bar.date for bar in bars]
    duplicate_dates = sorted(
        item for item, count in Counter(dates).items() if count > 1
    )
    if duplicate_dates:
        issues.append(
            _issue(
                "duplicate_dates",
                QualitySeverity.ERROR,
                "Daily history contains duplicate trading dates.",
                duplicate_dates,
            )
        )
    if dates != sorted(dates):
        issues.append(
            _issue(
                "non_ascending_dates",
                QualitySeverity.ERROR,
                "Daily history is not ordered from oldest to newest.",
            )
        )

    invalid_ohlc: list[date] = []
    negative_volume: list[date] = []
    invalid_adjusted_close: list[date] = []
    missing_adjusted_close: list[date] = []
    future_dates: list[date] = []
    for bar in bars:
        if (
            min(bar.open, bar.high, bar.low, bar.close) <= 0
            or bar.low > bar.high
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            invalid_ohlc.append(bar.date)
        if bar.volume is not None and bar.volume < 0:
            negative_volume.append(bar.date)
        if bar.adjusted_close is None:
            missing_adjusted_close.append(bar.date)
        elif bar.adjusted_close <= 0:
            invalid_adjusted_close.append(bar.date)
        if bar.date > effective_as_of:
            future_dates.append(bar.date)

    for code, message, affected in (
        ("invalid_ohlc", "Daily history contains invalid OHLC values.", invalid_ohlc),
        ("negative_volume", "Daily history contains negative volume.", negative_volume),
        (
            "invalid_adjusted_close",
            "Daily history contains non-positive adjusted close values.",
            invalid_adjusted_close,
        ),
        (
            "future_dates",
            "Daily history contains dates after the requested end date.",
            future_dates,
        ),
    ):
        if affected:
            issues.append(_issue(code, QualitySeverity.ERROR, message, affected))

    if missing_adjusted_close:
        issues.append(
            _issue(
                "missing_adjusted_close",
                QualitySeverity.WARNING,
                "Adjusted close is missing; affected returns will use raw close.",
                missing_adjusted_close,
            )
        )

    if expected_sessions:
        actual_dates = set(dates)
        suspended = set(suspended_dates)
        missing_sessions = sorted(
            item
            for item in expected_sessions
            if item <= effective_as_of and item not in actual_dates and item not in suspended
        )
        if missing_sessions:
            issues.append(
                _issue(
                    "missing_trading_sessions",
                    QualitySeverity.WARNING,
                    "Expected exchange sessions are missing and are not marked as suspensions.",
                    missing_sessions,
                )
            )

    adjustment_dates: list[date] = []
    extreme_adjusted_dates: list[date] = []
    ordered = sorted(bars, key=lambda item: item.date)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        raw_return = current.close / previous.close - 1
        if previous.adjusted_close and current.adjusted_close:
            adjusted_return = current.adjusted_close / previous.adjusted_close - 1
            if abs(raw_return) >= 0.30 and abs(adjusted_return) <= 0.10:
                adjustment_dates.append(current.date)
            if abs(adjusted_return) >= 0.50:
                extreme_adjusted_dates.append(current.date)
    if adjustment_dates:
        issues.append(
            _issue(
                "corporate_action_adjustment_detected",
                QualitySeverity.WARNING,
                "Raw and adjusted returns diverge sharply; inspect split/dividend semantics.",
                adjustment_dates,
            )
        )
    if extreme_adjusted_dates:
        issues.append(
            _issue(
                "extreme_adjusted_return",
                QualitySeverity.WARNING,
                "Adjusted history contains an extreme one-session return.",
                extreme_adjusted_dates,
            )
        )

    latest = max(dates)
    if latest < effective_as_of - timedelta(days=max(stale_after_days, 1)):
        issues.append(
            _issue(
                "stale_history",
                QualitySeverity.WARNING,
                (
                    f"Latest bar is {latest.isoformat()}, more than "
                    f"{stale_after_days} calendar days before the requested end date."
                ),
                [latest],
            )
        )

    if any(item.severity == QualitySeverity.ERROR for item in issues):
        status = DataQualityStatus.FAIL
    elif issues:
        status = DataQualityStatus.WARN
    else:
        status = DataQualityStatus.PASS
    return DataQualityResult(
        status=status,
        checked_at=checked_at,
        bar_count=len(bars),
        first_date=min(dates),
        latest_date=latest,
        issues=issues,
    )


def compare_market_histories(
    ticker: str,
    primary_provider: str,
    primary: Sequence[MarketBar],
    reference_provider: str,
    reference: Sequence[MarketBar],
    *,
    as_of_date: date,
    tolerance_pct: float = 0.02,
    minimum_overlap: int = 20,
) -> MarketComparisonResult:
    """Compare shared-session raw closes without treating either source as infallible."""

    primary_by_date = {item.date: item for item in primary if item.date <= as_of_date}
    reference_by_date = {item.date: item for item in reference if item.date <= as_of_date}
    overlap = sorted(set(primary_by_date) & set(reference_by_date))
    differences = [
        abs(primary_by_date[item].close / reference_by_date[item].close - 1)
        for item in overlap
        if reference_by_date[item].close > 0
    ]
    issues: list[DataQualityIssue] = []
    if len(overlap) < minimum_overlap:
        issues.append(
            _issue(
                "insufficient_reference_overlap",
                QualitySeverity.WARNING if overlap else QualitySeverity.ERROR,
                f"Only {len(overlap)} shared sessions are available for comparison.",
            )
        )
    max_difference = max(differences) if differences else None
    median_difference = statistics.median(differences) if differences else None
    outlier_dates = [
        item
        for item in overlap
        if reference_by_date[item].close > 0
        and abs(primary_by_date[item].close / reference_by_date[item].close - 1)
        > tolerance_pct
    ]
    if outlier_dates:
        severity = (
            QualitySeverity.ERROR
            if median_difference is not None and median_difference > tolerance_pct
            else QualitySeverity.WARNING
        )
        issues.append(
            _issue(
                "reference_close_difference",
                severity,
                f"Shared-session raw closes differ by more than {tolerance_pct:.2%}.",
                outlier_dates,
            )
        )
    if any(item.severity == QualitySeverity.ERROR for item in issues):
        status = DataQualityStatus.FAIL
    elif issues:
        status = DataQualityStatus.WARN
    else:
        status = DataQualityStatus.PASS
    semantic = {
        "ticker": ticker,
        "primary_provider": primary_provider,
        "reference_provider": reference_provider,
        "as_of_date": as_of_date,
        "primary": [item.model_dump(mode="json") for item in primary],
        "reference": [item.model_dump(mode="json") for item in reference],
        "tolerance_pct": tolerance_pct,
    }
    comparison_hash = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, default=str).encode()
    ).hexdigest()
    return MarketComparisonResult(
        id=f"market-comparison-{comparison_hash[:24]}",
        ticker=ticker,
        primary_provider=primary_provider,
        reference_provider=reference_provider,
        as_of_date=as_of_date,
        overlap_count=len(overlap),
        primary_only_count=len(set(primary_by_date) - set(reference_by_date)),
        reference_only_count=len(set(reference_by_date) - set(primary_by_date)),
        max_close_diff_pct=max_difference,
        median_close_diff_pct=median_difference,
        status=status,
        issues=issues,
        comparison_hash=comparison_hash,
    )
