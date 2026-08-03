from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    CorporateEventVersion,
)
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class EventCalendarStore:
    """Append-only persistence for point-in-time corporate event versions."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = (db_path or state_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_database(self.db_path)

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

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CorporateEventVersion:
        return CorporateEventVersion.model_validate_json(row["payload"])

    def save(self, event: CorporateEventVersion) -> CorporateEventVersion:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO corporate_event_versions (
                    id, run_id, event_key, version, version_hash, entity_id,
                    ticker, market, event_type, status, announced_date,
                    expected_date, effective_date, known_at, observed_at,
                    provider, external_id, source_suggestion_id, evidence_id, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.event_key,
                    event.version,
                    event.version_hash,
                    event.entity_id,
                    event.ticker,
                    event.market,
                    event.event_type.value,
                    event.status.value,
                    event.announced_date.isoformat() if event.announced_date else None,
                    event.expected_date.isoformat() if event.expected_date else None,
                    event.effective_date.isoformat() if event.effective_date else None,
                    event.known_at.isoformat(),
                    event.observed_at.isoformat(),
                    event.provider,
                    event.external_id,
                    event.source_suggestion_id,
                    event.evidence_id,
                    event.model_dump_json(),
                ),
            )
        return event

    def latest_for_key(
        self,
        run_id: str,
        event_key: str,
    ) -> CorporateEventVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM corporate_event_versions
                WHERE run_id = ? AND event_key = ?
                ORDER BY version DESC LIMIT 1
                """,
                (run_id, event_key),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_version_hash(
        self,
        run_id: str,
        event_key: str,
        version_hash: str,
    ) -> CorporateEventVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM corporate_event_versions
                WHERE run_id = ? AND event_key = ? AND version_hash = ?
                """,
                (run_id, event_key, version_hash),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        run_id: str,
        *,
        as_of: datetime | None = None,
        latest_only: bool = True,
        ticker: str | None = None,
        event_type: CorporateEventType | None = None,
        status: CorporateEventStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[CorporateEventVersion]:
        query = "SELECT payload FROM corporate_event_versions WHERE run_id = ?"
        parameters: list[object] = [run_id]
        if as_of is not None:
            if as_of.tzinfo is None:
                raise ValueError("as_of must include a timezone")
            query += " AND observed_at <= ?"
            parameters.append(as_of.astimezone(UTC).isoformat())
        query += " ORDER BY event_key, version"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        events = [self._from_row(row) for row in rows]
        if latest_only:
            by_key: dict[str, CorporateEventVersion] = {}
            for event in events:
                by_key[event.event_key] = event
            events = list(by_key.values())

        def included(event: CorporateEventVersion) -> bool:
            if ticker is not None and event.ticker != ticker:
                return False
            if event_type is not None and event.event_type != event_type:
                return False
            if status is not None and event.status != status:
                return False
            event_date = (
                event.effective_date
                or event.expected_date
                or event.occurred_date
                or event.announced_date
            )
            if date_from is not None and (event_date is None or event_date < date_from):
                return False
            if date_to is not None and (event_date is None or event_date > date_to):
                return False
            return True

        return sorted(
            (event for event in events if included(event)),
            key=lambda event: (
                event.effective_date
                or event.expected_date
                or event.occurred_date
                or event.announced_date
                or date.min,
                event.known_at,
                event.event_key,
                event.version,
            ),
            reverse=True,
        )
