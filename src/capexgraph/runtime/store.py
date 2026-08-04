from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from capexgraph.domain import ResearchRun, RunStatus, StepCheckpoint
from capexgraph.runtime.migrations import ensure_database


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
        ensure_database(self.db_path)

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

    @staticmethod
    def _quoted_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _delete_blockers(
        self,
        connection: sqlite3.Connection,
        run: ResearchRun,
    ) -> list[str]:
        blockers: list[str] = []
        if run.status is not RunStatus.CREATED:
            blockers.append(f"status={run.status.value}")
        if any(step.status.value != "pending" or step.attempts for step in run.pipeline):
            blockers.append("pipeline progress")
        for label, values in (
            ("nodes", run.nodes),
            ("edges", run.edges),
            ("evidence", run.evidence),
            ("candidates", run.candidates),
        ):
            if values:
                blockers.append(label)
        if run.manifest.get("agent_outputs"):
            blockers.append("agent outputs")

        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for table_row in table_rows:
            table_name = str(table_row["name"])
            quoted_table = self._quoted_identifier(table_name)
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()
            }
            reference_columns = [
                column for column in ("run_id", "parent_run_id") if column in columns
            ]
            if not reference_columns:
                continue
            where = " OR ".join(
                f"{self._quoted_identifier(column)} = ?" for column in reference_columns
            )
            count = connection.execute(
                f"SELECT COUNT(*) AS count FROM {quoted_table} WHERE {where}",
                tuple(run.id for _ in reference_columns),
            ).fetchone()["count"]
            if count:
                blockers.append(table_name)
        return blockers

    def delete_empty_run(self, run_id: str, *, expected_updated_at: datetime) -> Path:
        """Archive and delete an untouched run after a locked eligibility re-check."""

        root = runs_dir()
        source = (root / run_id).resolve()
        if source.parent != root or source.name != run_id:
            raise ValueError("Invalid research run identifier.")

        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        archived: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Research run not found: {run_id}")
            run = ResearchRun.model_validate_json(row["payload"])
            expected = expected_updated_at.astimezone(UTC)
            actual = run.updated_at.astimezone(UTC)
            if actual != expected:
                raise ValueError(
                    "Research run changed after the confirmation was opened. Refresh and try again."
                )

            blockers = self._delete_blockers(connection, run)
            if blockers:
                joined = ", ".join(dict.fromkeys(blockers))
                raise ValueError(
                    "Only untouched research runs can be deleted. Protected data: " + joined
                )
            if not source.is_dir():
                raise ValueError("Research run workspace is missing; deletion was cancelled.")

            batch = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
            archived = root / ".trash" / batch / run.id
            archived.parent.mkdir(parents=True, exist_ok=False)
            shutil.move(str(source), str(archived))
            deleted = connection.execute("DELETE FROM runs WHERE id = ?", (run.id,)).rowcount
            if deleted != 1:
                raise RuntimeError("Research run deletion did not remove exactly one record.")
            connection.commit()
            return archived.relative_to(root)
        except Exception:
            connection.rollback()
            if archived is not None and archived.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(archived), str(source))
            raise
        finally:
            connection.close()

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
