from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from capexgraph.domain import (
    ThemeDefinition,
    ThemeMembership,
    ThemeSource,
    ThemeUniverseSnapshot,
)
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class ThemeRegistryStore:
    """Point-in-time theme definitions, sources, memberships, and snapshots."""

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

    def save_definition(self, definition: ThemeDefinition) -> ThemeDefinition:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theme_definitions (
                    id, theme_id, version, valid_from, valid_to, known_at,
                    definition_hash, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition.id,
                    definition.theme_id,
                    definition.version,
                    definition.valid_from.isoformat(),
                    definition.valid_to.isoformat() if definition.valid_to else None,
                    definition.known_at.isoformat(),
                    definition.definition_hash,
                    definition.model_dump_json(),
                ),
            )
        return definition

    def find_definition_hash(
        self,
        theme_id: str,
        definition_hash: str,
    ) -> ThemeDefinition | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM theme_definitions
                WHERE theme_id = ? AND definition_hash = ?
                """,
                (theme_id, definition_hash),
            ).fetchone()
        return ThemeDefinition.model_validate_json(row["payload"]) if row else None

    def latest_definition(
        self,
        theme_id: str,
        *,
        as_of_date: date | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> ThemeDefinition | None:
        query = "SELECT payload FROM theme_definitions WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if as_of_date is not None:
            query += " AND valid_from <= ? AND (valid_to IS NULL OR valid_to >= ?)"
            parameters.extend((as_of_date.isoformat(), as_of_date.isoformat()))
        if knowledge_cutoff is not None:
            if knowledge_cutoff.tzinfo is None:
                raise ValueError("knowledge_cutoff must include a timezone")
            query += " AND known_at <= ?"
            parameters.append(knowledge_cutoff.astimezone(UTC).isoformat())
        query += " ORDER BY version DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return ThemeDefinition.model_validate_json(row["payload"]) if row else None

    def list_definitions(self, *, latest_only: bool = True) -> list[ThemeDefinition]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM theme_definitions ORDER BY theme_id, version"
            ).fetchall()
        definitions = [ThemeDefinition.model_validate_json(row["payload"]) for row in rows]
        if not latest_only:
            return definitions
        latest: dict[str, ThemeDefinition] = {}
        for definition in definitions:
            latest[definition.theme_id] = definition
        return sorted(latest.values(), key=lambda item: item.name.casefold())

    def save_source(self, source: ThemeSource) -> ThemeSource:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theme_sources (
                    id, theme_id, kind, market, provider, observed_at,
                    content_hash, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    source.id,
                    source.theme_id,
                    source.kind.value,
                    source.market,
                    source.provider,
                    source.observed_at.isoformat(),
                    source.content_hash,
                    source.model_dump_json(),
                ),
            )
        return source

    def get_source(self, source_id: str) -> ThemeSource | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM theme_sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        return ThemeSource.model_validate_json(row["payload"]) if row else None

    def list_sources(
        self,
        theme_id: str,
        *,
        market: str | None = None,
    ) -> list[ThemeSource]:
        query = "SELECT payload FROM theme_sources WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if market is not None:
            query += " AND market = ?"
            parameters.append(market)
        query += " ORDER BY observed_at DESC, id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ThemeSource.model_validate_json(row["payload"]) for row in rows]

    def save_memberships(
        self,
        memberships: list[ThemeMembership],
    ) -> list[ThemeMembership]:
        with self._connect() as connection:
            for membership in memberships:
                connection.execute(
                    """
                    INSERT INTO theme_memberships (
                        id, theme_id, source_id, ticker, market, valid_from,
                        valid_to, known_at, observed_at, source_hash, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                    """,
                    (
                        membership.id,
                        membership.theme_id,
                        membership.source_id,
                        membership.ticker,
                        membership.market,
                        membership.valid_from.isoformat(),
                        membership.valid_to.isoformat() if membership.valid_to else None,
                        membership.known_at.isoformat(),
                        membership.observed_at.isoformat(),
                        membership.source_hash,
                        membership.model_dump_json(),
                    ),
                )
        return memberships

    def list_memberships(
        self,
        theme_id: str,
        *,
        as_of_date: date | None = None,
        knowledge_cutoff: datetime | None = None,
        market: str | None = None,
    ) -> list[ThemeMembership]:
        query = "SELECT payload FROM theme_memberships WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if market is not None:
            query += " AND market = ?"
            parameters.append(market)
        if as_of_date is not None:
            query += " AND valid_from <= ? AND (valid_to IS NULL OR valid_to >= ?)"
            parameters.extend((as_of_date.isoformat(), as_of_date.isoformat()))
        if knowledge_cutoff is not None:
            if knowledge_cutoff.tzinfo is None:
                raise ValueError("knowledge_cutoff must include a timezone")
            query += " AND known_at <= ?"
            parameters.append(knowledge_cutoff.astimezone(UTC).isoformat())
        query += " ORDER BY ticker, source_id, valid_from, known_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ThemeMembership.model_validate_json(row["payload"]) for row in rows]

    def save_snapshot(self, snapshot: ThemeUniverseSnapshot) -> ThemeUniverseSnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theme_universe_snapshots (
                    id, theme_id, definition_id, as_of_date, knowledge_cutoff,
                    content_hash, partial, generated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    snapshot.id,
                    snapshot.theme_id,
                    snapshot.definition_id,
                    snapshot.as_of_date.isoformat(),
                    snapshot.knowledge_cutoff.isoformat(),
                    snapshot.content_hash,
                    int(snapshot.partial),
                    snapshot.generated_at.isoformat(),
                    snapshot.model_dump_json(),
                ),
            )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ThemeUniverseSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM theme_universe_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
        return ThemeUniverseSnapshot.model_validate_json(row["payload"]) if row else None

    def list_snapshots(
        self,
        theme_id: str,
        *,
        as_of_date: date | None = None,
    ) -> list[ThemeUniverseSnapshot]:
        query = "SELECT payload FROM theme_universe_snapshots WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if as_of_date is not None:
            query += " AND as_of_date = ?"
            parameters.append(as_of_date.isoformat())
        query += " ORDER BY as_of_date DESC, knowledge_cutoff DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ThemeUniverseSnapshot.model_validate_json(row["payload"]) for row in rows]
