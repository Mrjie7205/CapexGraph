from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from capexgraph.domain import DataQualityResult, MarketBar, MarketBarSet
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class MarketDataStore:
    """Idempotent SQLite persistence for normalized bars and quality reports."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = (db_path or state_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_database(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def date_bounds(self, ticker: str, provider: str) -> tuple[date, date] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MIN(trade_date) AS first_date, MAX(trade_date) AS latest_date
                FROM market_bars
                WHERE ticker = ? AND provider = ?
                """,
                (ticker, provider),
            ).fetchone()
        if row is None or row["first_date"] is None or row["latest_date"] is None:
            return None
        return date.fromisoformat(row["first_date"]), date.fromisoformat(row["latest_date"])

    def save_quality(
        self,
        bar_set: MarketBarSet,
        quality: DataQualityResult,
    ) -> DataQualityResult:
        payload = quality.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_quality_reports (
                    ticker, provider, raw_hash, checked_at, status, first_date,
                    latest_date, bar_count, source_url, provider_version, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, provider, raw_hash) DO UPDATE SET
                    checked_at = excluded.checked_at,
                    status = excluded.status,
                    first_date = excluded.first_date,
                    latest_date = excluded.latest_date,
                    bar_count = excluded.bar_count,
                    source_url = excluded.source_url,
                    provider_version = excluded.provider_version,
                    payload = excluded.payload
                """,
                (
                    bar_set.ticker,
                    bar_set.provider,
                    bar_set.raw_hash,
                    quality.checked_at.isoformat(),
                    quality.status.value,
                    quality.first_date.isoformat() if quality.first_date else None,
                    quality.latest_date.isoformat() if quality.latest_date else None,
                    quality.bar_count,
                    str(bar_set.source_url) if bar_set.source_url else None,
                    bar_set.provider_version,
                    payload,
                ),
            )
        return quality

    def save_bars(self, bar_set: MarketBarSet) -> int:
        values = [
            (
                bar_set.ticker,
                bar_set.provider,
                bar.date.isoformat(),
                bar_set.market,
                bar_set.exchange,
                bar_set.currency,
                bar_set.timezone,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.adjusted_close,
                bar.volume,
                bar_set.raw_hash,
                bar_set.fetched_at.isoformat(),
            )
            for bar in bar_set.bars
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO market_bars (
                    ticker, provider, trade_date, market, exchange, currency,
                    timezone, open, high, low, close, adjusted_close, volume,
                    raw_hash, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, provider, trade_date) DO UPDATE SET
                    market = excluded.market,
                    exchange = excluded.exchange,
                    currency = excluded.currency,
                    timezone = excluded.timezone,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adjusted_close = excluded.adjusted_close,
                    volume = excluded.volume,
                    raw_hash = excluded.raw_hash,
                    fetched_at = excluded.fetched_at
                """,
                values,
            )
        return len(values)

    def list_bars(
        self,
        ticker: str,
        *,
        provider: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MarketBar]:
        clauses = ["ticker = ?"]
        parameters: list[object] = [ticker]
        if provider is not None:
            clauses.append("provider = ?")
            parameters.append(provider)
        if start_date is not None:
            clauses.append("trade_date >= ?")
            parameters.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("trade_date <= ?")
            parameters.append(end_date.isoformat())
        query = (
            "SELECT trade_date, open, high, low, close, adjusted_close, volume "
            "FROM market_bars WHERE "
            + " AND ".join(clauses)
            + " ORDER BY trade_date"
        )
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            MarketBar(
                date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                adjusted_close=row["adjusted_close"],
                volume=row["volume"],
            )
            for row in rows
        ]

    def latest_quality(
        self,
        ticker: str,
        *,
        provider: str | None = None,
    ) -> DataQualityResult | None:
        query = "SELECT payload FROM market_quality_reports WHERE ticker = ?"
        parameters: list[object] = [ticker]
        if provider is not None:
            query += " AND provider = ?"
            parameters.append(provider)
        query += " ORDER BY checked_at DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return DataQualityResult.model_validate_json(row["payload"]) if row else None
