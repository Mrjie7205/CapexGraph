from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from capexgraph.domain import (
    LiveChannel,
    LiveDeadLetter,
    LiveProviderCheckpoint,
    LiveRetentionClass,
    LiveSignalVersion,
    ResearchActionProposal,
    SignalObservation,
)
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class LiveSignalStore:
    """SQLite persistence for channel observations and append-only signal versions."""

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
    def _observation_from_row(row: sqlite3.Row) -> SignalObservation:
        return SignalObservation.model_validate_json(row["payload"])

    @staticmethod
    def _signal_from_row(row: sqlite3.Row) -> LiveSignalVersion:
        return LiveSignalVersion.model_validate_json(row["payload"])

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> LiveProviderCheckpoint:
        return LiveProviderCheckpoint.model_validate_json(row["payload"])

    def get_observation(self, observation_id: str) -> SignalObservation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM live_signal_observations WHERE id = ?",
                (observation_id,),
            ).fetchone()
        return self._observation_from_row(row) if row else None

    def save_observation(self, observation: SignalObservation) -> SignalObservation:
        persisted = observation
        if observation.retention_class in {
            LiveRetentionClass.EPHEMERAL,
            LiveRetentionClass.METADATA_ONLY,
        }:
            persisted = observation.model_copy(update={"content": ""})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO live_signal_observations (
                    id, provider, provider_version, channel, stream, external_id,
                    event_key, category, published_at, observed_at, content_hash,
                    retention_class, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persisted.id,
                    persisted.provider,
                    persisted.provider_version,
                    persisted.channel.value,
                    persisted.stream,
                    persisted.external_id,
                    persisted.event_key,
                    persisted.category.value,
                    persisted.published_at.isoformat(),
                    persisted.observed_at.isoformat(),
                    persisted.content_hash,
                    persisted.retention_class.value,
                    persisted.model_dump_json(),
                ),
            )
        return self.get_observation(observation.id) or persisted

    def observations_by_ids(
        self,
        observation_ids: Sequence[str],
    ) -> list[SignalObservation]:
        if not observation_ids:
            return []
        placeholders = ",".join("?" for _ in observation_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload FROM live_signal_observations
                WHERE id IN ({placeholders})
                ORDER BY observed_at, id
                """,
                tuple(observation_ids),
            ).fetchall()
        return [self._observation_from_row(row) for row in rows]

    def latest_signal(self, signal_key: str) -> LiveSignalVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM live_signal_versions
                WHERE signal_key = ?
                ORDER BY version DESC LIMIT 1
                """,
                (signal_key,),
            ).fetchone()
        return self._signal_from_row(row) if row else None

    def signal_for_observation(self, observation_id: str) -> LiveSignalVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT versions.payload
                FROM live_signal_versions AS versions
                JOIN live_signal_observation_links AS links
                  ON links.signal_version_id = versions.id
                WHERE links.observation_id = ?
                ORDER BY versions.version DESC
                LIMIT 1
                """,
                (observation_id,),
            ).fetchone()
        return self._signal_from_row(row) if row else None

    def save_signal(self, signal: LiveSignalVersion) -> LiveSignalVersion:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO live_signal_versions (
                    id, signal_key, version, version_hash, category, published_at,
                    first_observed_at, last_observed_at, match_status,
                    verification_state, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.id,
                    signal.signal_key,
                    signal.version,
                    signal.version_hash,
                    signal.category.value,
                    signal.published_at.isoformat(),
                    signal.first_observed_at.isoformat(),
                    signal.last_observed_at.isoformat(),
                    signal.match_status.value,
                    signal.verification_state.value,
                    signal.model_dump_json(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO live_signal_observation_links (
                    signal_version_id, observation_id
                ) VALUES (?, ?)
                """,
                [(signal.id, observation_id) for observation_id in signal.observation_ids],
            )
        return signal

    def list_signals(self, *, latest_only: bool = True) -> list[LiveSignalVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM live_signal_versions
                ORDER BY signal_key, version
                """
            ).fetchall()
        signals = [self._signal_from_row(row) for row in rows]
        if latest_only:
            by_key: dict[str, LiveSignalVersion] = {}
            for signal in signals:
                by_key[signal.signal_key] = signal
            signals = list(by_key.values())
        return sorted(
            signals,
            key=lambda item: (item.last_observed_at, item.signal_key, item.version),
            reverse=True,
        )

    def get_checkpoint(
        self,
        provider: str,
        channel: LiveChannel,
        stream: str,
    ) -> LiveProviderCheckpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM live_provider_checkpoints
                WHERE provider = ? AND channel = ? AND stream = ?
                """,
                (provider, channel.value, stream),
            ).fetchone()
        return self._checkpoint_from_row(row) if row else None

    def save_checkpoint(
        self,
        checkpoint: LiveProviderCheckpoint,
    ) -> LiveProviderCheckpoint:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO live_provider_checkpoints (
                    provider, provider_version, channel, stream, cursor,
                    last_external_id, last_published_at, last_observed_at,
                    health, calls_used, call_budget, budget_date, updated_at,
                    error, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, channel, stream) DO UPDATE SET
                    provider_version = excluded.provider_version,
                    cursor = excluded.cursor,
                    last_external_id = excluded.last_external_id,
                    last_published_at = excluded.last_published_at,
                    last_observed_at = excluded.last_observed_at,
                    health = excluded.health,
                    calls_used = excluded.calls_used,
                    call_budget = excluded.call_budget,
                    budget_date = excluded.budget_date,
                    updated_at = excluded.updated_at,
                    error = excluded.error,
                    payload = excluded.payload
                """,
                (
                    checkpoint.provider,
                    checkpoint.provider_version,
                    checkpoint.channel.value,
                    checkpoint.stream,
                    checkpoint.cursor,
                    checkpoint.last_external_id,
                    (
                        checkpoint.last_published_at.isoformat()
                        if checkpoint.last_published_at
                        else None
                    ),
                    (
                        checkpoint.last_observed_at.isoformat()
                        if checkpoint.last_observed_at
                        else None
                    ),
                    checkpoint.health.value,
                    checkpoint.calls_used,
                    checkpoint.call_budget,
                    checkpoint.budget_date.isoformat() if checkpoint.budget_date else None,
                    checkpoint.updated_at.isoformat(),
                    checkpoint.error,
                    checkpoint.model_dump_json(),
                ),
            )
        return checkpoint

    def list_checkpoints(self) -> list[LiveProviderCheckpoint]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM live_provider_checkpoints
                ORDER BY provider, channel, stream
                """
            ).fetchall()
        return [self._checkpoint_from_row(row) for row in rows]

    def save_dead_letter(self, item: LiveDeadLetter) -> LiveDeadLetter:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO live_dead_letters (
                    id, provider, channel, stream, observed_at,
                    payload_hash, error, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.provider,
                    item.channel.value,
                    item.stream,
                    item.observed_at.isoformat(),
                    item.payload_hash,
                    item.error,
                    item.model_dump_json(),
                ),
            )
        return item

    def list_dead_letters(self) -> list[LiveDeadLetter]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM live_dead_letters
                ORDER BY observed_at DESC, id
                """
            ).fetchall()
        return [LiveDeadLetter.model_validate_json(row["payload"]) for row in rows]

    def save_proposal(
        self,
        proposal: ResearchActionProposal,
    ) -> ResearchActionProposal:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_action_proposals (
                    id, signal_key, analysis_version, human_status, created_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.signal_key,
                    proposal.analysis_version,
                    proposal.human_status.value,
                    proposal.created_at.isoformat(),
                    proposal.model_dump_json(),
                ),
            )
        return proposal
