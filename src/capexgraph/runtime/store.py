from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from capexgraph.domain import ResearchRun, RunStatus, StepCheckpoint


def runs_dir() -> Path:
    return Path(os.getenv("CAPEXGRAPH_RUNS_DIR", "runs")).resolve()


def state_db_path() -> Path:
    configured = os.getenv("CAPEXGRAPH_STATE_DB")
    return Path(configured).resolve() if configured else runs_dir() / "capexgraph.db"


class RunStore:
    """SQLite-backed system of record for runs and step checkpoints."""

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
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    market TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_updated_at
                    ON runs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_status
                    ON runs(status);

                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT NOT NULL,
                    step_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    message TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (run_id, step_key),
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                );
                """
            )

    def save_run(self, run: ResearchRun) -> ResearchRun:
        payload = run.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, mode, subject, market, as_of_date, status,
                    created_at, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    mode = excluded.mode,
                    subject = excluded.subject,
                    market = excluded.market,
                    as_of_date = excluded.as_of_date,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    run.id,
                    run.mode.value,
                    run.subject,
                    run.market,
                    run.as_of_date.isoformat(),
                    run.status.value,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                    payload,
                ),
            )
        return run

    def load_run(self, run_id: str) -> ResearchRun | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        return ResearchRun.model_validate_json(row["payload"]) if row else None

    def list_runs(
        self,
        *,
        limit: int = 50,
        status: RunStatus | None = None,
    ) -> list[ResearchRun]:
        limit = max(1, min(limit, 500))
        query = "SELECT payload FROM runs"
        parameters: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status.value)
        query += " ORDER BY updated_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ResearchRun.model_validate_json(row["payload"]) for row in rows]

    def save_checkpoint(self, checkpoint: StepCheckpoint) -> StepCheckpoint:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (
                    run_id, step_key, status, attempt, started_at, completed_at,
                    message, error, output_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_key) DO UPDATE SET
                    status = excluded.status,
                    attempt = excluded.attempt,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    message = excluded.message,
                    error = excluded.error,
                    output_json = excluded.output_json
                """,
                (
                    checkpoint.run_id,
                    checkpoint.step_key,
                    checkpoint.status.value,
                    checkpoint.attempt,
                    checkpoint.started_at.isoformat() if checkpoint.started_at else None,
                    checkpoint.completed_at.isoformat() if checkpoint.completed_at else None,
                    checkpoint.message,
                    checkpoint.error,
                    checkpoint.model_dump_json(include={"output"}),
                ),
            )
        return checkpoint

    def list_checkpoints(self, run_id: str) -> list[StepCheckpoint]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        checkpoints: list[StepCheckpoint] = []
        for row in rows:
            checkpoints.append(
                StepCheckpoint(
                    run_id=run_id,
                    step_key=row["step_key"],
                    status=row["status"],
                    attempt=row["attempt"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    message=row["message"],
                    error=row["error"],
                    output=json.loads(row["output_json"]).get("output", {}),
                )
            )
        return checkpoints
