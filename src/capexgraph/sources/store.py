from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from capexgraph.domain import SourceSuggestion, SourceSuggestionStatus
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class SourceSuggestionStore:
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
    def _from_row(row: sqlite3.Row) -> SourceSuggestion:
        return SourceSuggestion.model_validate_json(row["payload"])

    def get(self, suggestion_id: str) -> SourceSuggestion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM source_suggestions WHERE id = ?",
                (suggestion_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_by_url(self, run_id: str, canonical_url: str) -> SourceSuggestion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM source_suggestions
                WHERE run_id = ? AND canonical_url = ?
                """,
                (run_id, canonical_url),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_by_content_hash(
        self,
        run_id: str,
        content_hash: str,
        *,
        exclude_id: str | None = None,
    ) -> SourceSuggestion | None:
        query = """
            SELECT payload FROM source_suggestions
            WHERE run_id = ? AND content_hash = ?
        """
        parameters: list[str] = [run_id, content_hash]
        if exclude_id:
            query += " AND id != ?"
            parameters.append(exclude_id)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return self._from_row(row) if row else None

    def add(self, suggestion: SourceSuggestion) -> SourceSuggestion:
        existing = self.find_by_url(suggestion.run_id, suggestion.canonical_url)
        if existing is not None:
            duplicate_count = int(existing.metadata.get("duplicate_url_count", 0)) + 1
            existing.metadata["duplicate_url_count"] = duplicate_count
            existing.metadata["last_duplicate_provider"] = suggestion.provider
            existing.updated_at = datetime.now(UTC)
            return self.save(existing)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_suggestions (
                    id, run_id, canonical_url, status, provider, authority,
                    content_hash, created_at, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.id,
                    suggestion.run_id,
                    suggestion.canonical_url,
                    suggestion.status.value,
                    suggestion.provider,
                    suggestion.authority.value,
                    suggestion.content_hash,
                    suggestion.discovered_at.isoformat(),
                    suggestion.updated_at.isoformat(),
                    suggestion.model_dump_json(),
                ),
            )
        return suggestion

    def save(self, suggestion: SourceSuggestion) -> SourceSuggestion:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE source_suggestions SET
                    canonical_url = ?,
                    status = ?,
                    provider = ?,
                    authority = ?,
                    content_hash = ?,
                    updated_at = ?,
                    payload = ?
                WHERE id = ? AND run_id = ?
                """,
                (
                    suggestion.canonical_url,
                    suggestion.status.value,
                    suggestion.provider,
                    suggestion.authority.value,
                    suggestion.content_hash,
                    suggestion.updated_at.isoformat(),
                    suggestion.model_dump_json(),
                    suggestion.id,
                    suggestion.run_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Source suggestion not found: {suggestion.id}")
        return suggestion

    def list(
        self,
        run_id: str,
        *,
        status: SourceSuggestionStatus | None = None,
    ) -> list[SourceSuggestion]:
        query = "SELECT payload FROM source_suggestions WHERE run_id = ?"
        parameters: list[str] = [run_id]
        if status is not None:
            query += " AND status = ?"
            parameters.append(status.value)
        query += """
            ORDER BY
                CASE authority
                    WHEN 'regulator' THEN 0
                    WHEN 'issuer' THEN 1
                    ELSE 2
                END,
                updated_at DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._from_row(row) for row in rows]
