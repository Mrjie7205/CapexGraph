from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from capexgraph.domain import (
    DataQualityIssue,
    DataQualityResult,
    DataQualityStatus,
    MarketBar,
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
