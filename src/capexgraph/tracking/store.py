from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from capexgraph.runtime.store import state_db_path
from capexgraph.tracking.models import (
    TrackedCandidate,
    TrackingSnapshot,
    TrackingStage,
    TriggerEvent,
)


class TrackingStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = (db_path or state_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracked_candidates (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    label TEXT NOT NULL,
                    benchmark_ticker TEXT NOT NULL,
                    call_date TEXT NOT NULL,
                    call_price REAL,
                    call_benchmark_price REAL,
                    stage TEXT NOT NULL,
                    thesis TEXT NOT NULL DEFAULT '',
                    invalidation_json TEXT NOT NULL DEFAULT '[]',
                    triggers_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, node_id)
                );

                CREATE TABLE IF NOT EXISTS tracking_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tracked_id TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    price REAL NOT NULL,
                    benchmark_price REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    benchmark_return_pct REAL NOT NULL,
                    alpha_pct REAL NOT NULL,
                    source TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(tracked_id, as_of_date),
                    FOREIGN KEY(tracked_id) REFERENCES tracked_candidates(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS trigger_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tracked_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    observed_value REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    as_of_date TEXT NOT NULL,
                    acknowledged_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(tracked_id, metric, operator, threshold, as_of_date),
                    FOREIGN KEY(tracked_id) REFERENCES tracked_candidates(id) ON DELETE CASCADE
                );
                """
            )

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> TrackedCandidate:
        return TrackedCandidate(
            id=row["id"],
            run_id=row["run_id"],
            node_id=row["node_id"],
            ticker=row["ticker"],
            label=row["label"],
            benchmark_ticker=row["benchmark_ticker"],
            call_date=row["call_date"],
            call_price=row["call_price"],
            call_benchmark_price=row["call_benchmark_price"],
            stage=row["stage"],
            thesis=row["thesis"],
            invalidation=json.loads(row["invalidation_json"]),
            triggers=json.loads(row["triggers_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_candidate(self, item: TrackedCandidate) -> TrackedCandidate:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO tracked_candidates (
                    id, run_id, node_id, ticker, label, benchmark_ticker, call_date,
                    call_price, call_benchmark_price, stage, thesis, invalidation_json,
                    triggers_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.run_id,
                    item.node_id,
                    item.ticker,
                    item.label,
                    item.benchmark_ticker,
                    item.call_date.isoformat(),
                    item.call_price,
                    item.call_benchmark_price,
                    item.stage.value,
                    item.thesis,
                    json.dumps(item.invalidation, ensure_ascii=False),
                    json.dumps(
                        [trigger.model_dump() for trigger in item.triggers],
                        ensure_ascii=False,
                    ),
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        stored = self.get_candidate(item.id)
        if stored is None:
            raise RuntimeError("Tracked candidate was not persisted")
        return stored

    def get_candidate(self, tracked_id: str) -> TrackedCandidate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tracked_candidates WHERE id = ?", (tracked_id,)
            ).fetchone()
        return self._candidate_from_row(row) if row else None

    def list_candidates(self) -> list[TrackedCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tracked_candidates ORDER BY updated_at DESC"
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def update_stage(self, tracked_id: str, stage: TrackingStage) -> TrackedCandidate:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tracked_candidates SET stage = ?, updated_at = ? WHERE id = ?",
                (stage.value, now, tracked_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Tracked candidate not found: {tracked_id}")
        item = self.get_candidate(tracked_id)
        if item is None:
            raise RuntimeError("Tracked candidate disappeared")
        return item

    @staticmethod
    def _snapshot_from_row(row: sqlite3.Row) -> TrackingSnapshot:
        return TrackingSnapshot(**dict(row))

    def save_snapshot(self, snapshot: TrackingSnapshot) -> TrackingSnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tracking_snapshots (
                    tracked_id, as_of_date, price, benchmark_price, return_pct,
                    benchmark_return_pct, alpha_pct, source, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tracked_id, as_of_date) DO UPDATE SET
                    price = excluded.price,
                    benchmark_price = excluded.benchmark_price,
                    return_pct = excluded.return_pct,
                    benchmark_return_pct = excluded.benchmark_return_pct,
                    alpha_pct = excluded.alpha_pct,
                    source = excluded.source,
                    recorded_at = excluded.recorded_at
                """,
                (
                    snapshot.tracked_id,
                    snapshot.as_of_date.isoformat(),
                    snapshot.price,
                    snapshot.benchmark_price,
                    snapshot.return_pct,
                    snapshot.benchmark_return_pct,
                    snapshot.alpha_pct,
                    snapshot.source,
                    snapshot.recorded_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM tracking_snapshots WHERE tracked_id = ? AND as_of_date = ?",
                (snapshot.tracked_id, snapshot.as_of_date.isoformat()),
            ).fetchone()
        if row is None:
            raise RuntimeError("Tracking snapshot was not persisted")
        return self._snapshot_from_row(row)

    def list_snapshots(self, tracked_id: str) -> list[TrackingSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tracking_snapshots WHERE tracked_id = ? ORDER BY as_of_date",
                (tracked_id,),
            ).fetchall()
        return [self._snapshot_from_row(row) for row in rows]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> TriggerEvent:
        return TriggerEvent(**dict(row))

    def save_event(self, event: TriggerEvent) -> TriggerEvent:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO trigger_events (
                    tracked_id, metric, operator, threshold, observed_value, note,
                    as_of_date, acknowledged_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.tracked_id,
                    event.metric,
                    event.operator,
                    event.threshold,
                    event.observed_value,
                    event.note,
                    event.as_of_date.isoformat(),
                    event.acknowledged_at.isoformat() if event.acknowledged_at else None,
                    event.created_at.isoformat(),
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM trigger_events
                WHERE tracked_id = ? AND metric = ? AND operator = ?
                    AND threshold = ? AND as_of_date = ?
                """,
                (
                    event.tracked_id,
                    event.metric,
                    event.operator,
                    event.threshold,
                    event.as_of_date.isoformat(),
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("Trigger event was not persisted")
        return self._event_from_row(row)

    def list_events(self, tracked_id: str | None = None) -> list[TriggerEvent]:
        query = "SELECT * FROM trigger_events"
        params: tuple[str, ...] = ()
        if tracked_id:
            query += " WHERE tracked_id = ?"
            params = (tracked_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._event_from_row(row) for row in rows]

    def acknowledge_event(self, event_id: int) -> TriggerEvent:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE trigger_events SET acknowledged_at = ? WHERE id = ?",
                (now, event_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Trigger event not found: {event_id}")
            row = connection.execute(
                "SELECT * FROM trigger_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._event_from_row(row)
