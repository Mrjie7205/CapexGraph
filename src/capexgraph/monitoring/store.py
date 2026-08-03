from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from capexgraph.domain import (
    MainlineAssessment,
    MainlinePolicy,
    MainlineStateEvent,
    MonitorJob,
    ThemeDailyMetric,
    ThemeResearchProposal,
)
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class MainlineStore:
    """Durable deterministic metrics, policies, state changes, and jobs."""

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

    def save_metric(self, metric: ThemeDailyMetric) -> ThemeDailyMetric:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theme_daily_metrics (
                    id, theme_id, snapshot_id, as_of_date, market, provider,
                    coverage_ratio, quality_status, input_hash, computed_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    metric.id,
                    metric.theme_id,
                    metric.snapshot_id,
                    metric.as_of_date.isoformat(),
                    metric.market,
                    metric.provider,
                    metric.coverage_ratio,
                    metric.quality_status.value,
                    metric.input_hash,
                    metric.computed_at.isoformat(),
                    metric.model_dump_json(),
                ),
            )
        return metric

    def list_metrics(
        self,
        theme_id: str,
        *,
        market: str | None = None,
        limit: int = 200,
    ) -> list[ThemeDailyMetric]:
        query = "SELECT payload FROM theme_daily_metrics WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if market is not None:
            query += " AND market = ?"
            parameters.append(market)
        query += " ORDER BY as_of_date DESC, computed_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 5000)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ThemeDailyMetric.model_validate_json(row["payload"]) for row in rows]

    def save_policy(self, policy: MainlinePolicy) -> MainlinePolicy:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mainline_policies (
                    id, name, version, effective_from, known_at, experimental,
                    policy_hash, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    policy.id,
                    policy.name,
                    policy.version,
                    policy.effective_from.isoformat(),
                    policy.known_at.isoformat(),
                    int(policy.experimental),
                    policy.policy_hash,
                    policy.model_dump_json(),
                ),
            )
        return policy

    def get_policy(self, policy_id: str) -> MainlinePolicy | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mainline_policies WHERE id = ?",
                (policy_id,),
            ).fetchone()
        return MainlinePolicy.model_validate_json(row["payload"]) if row else None

    def list_policies(self) -> list[MainlinePolicy]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM mainline_policies ORDER BY effective_from DESC, version DESC"
            ).fetchall()
        return [MainlinePolicy.model_validate_json(row["payload"]) for row in rows]

    def save_assessment(self, assessment: MainlineAssessment) -> MainlineAssessment:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mainline_assessments (
                    id, theme_id, metric_id, policy_id, as_of_date, state,
                    score, changed, input_hash, assessed_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    assessment.id,
                    assessment.theme_id,
                    assessment.metric_id,
                    assessment.policy_id,
                    assessment.as_of_date.isoformat(),
                    assessment.state.value,
                    assessment.score,
                    int(assessment.changed),
                    assessment.input_hash,
                    assessment.assessed_at.isoformat(),
                    assessment.model_dump_json(),
                ),
            )
        return assessment

    def latest_assessment(
        self,
        theme_id: str,
        *,
        before: date | None = None,
    ) -> MainlineAssessment | None:
        query = "SELECT payload FROM mainline_assessments WHERE theme_id = ?"
        parameters: list[object] = [theme_id]
        if before is not None:
            query += " AND as_of_date < ?"
            parameters.append(before.isoformat())
        query += " ORDER BY as_of_date DESC, assessed_at DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return MainlineAssessment.model_validate_json(row["payload"]) if row else None

    def list_assessments(
        self,
        theme_id: str | None = None,
        *,
        limit: int = 500,
    ) -> list[MainlineAssessment]:
        query = "SELECT payload FROM mainline_assessments"
        parameters: list[object] = []
        if theme_id is not None:
            query += " WHERE theme_id = ?"
            parameters.append(theme_id)
        query += " ORDER BY as_of_date DESC, assessed_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 5000)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [MainlineAssessment.model_validate_json(row["payload"]) for row in rows]

    def save_state_event(self, event: MainlineStateEvent) -> MainlineStateEvent:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mainline_state_events (
                    id, theme_id, assessment_id, as_of_date, from_state, to_state,
                    created_at, acknowledged_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    acknowledged_at = excluded.acknowledged_at,
                    payload = excluded.payload
                """,
                (
                    event.id,
                    event.theme_id,
                    event.assessment_id,
                    event.as_of_date.isoformat(),
                    event.from_state.value if event.from_state else None,
                    event.to_state.value,
                    event.created_at.isoformat(),
                    event.acknowledged_at.isoformat() if event.acknowledged_at else None,
                    event.model_dump_json(),
                ),
            )
        return event

    def list_state_events(
        self,
        theme_id: str | None = None,
        *,
        limit: int = 500,
    ) -> list[MainlineStateEvent]:
        query = "SELECT payload FROM mainline_state_events"
        parameters: list[object] = []
        if theme_id is not None:
            query += " WHERE theme_id = ?"
            parameters.append(theme_id)
        query += " ORDER BY as_of_date DESC, created_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 5000)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [MainlineStateEvent.model_validate_json(row["payload"]) for row in rows]

    def acknowledge_state_event(self, event_id: str) -> MainlineStateEvent:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mainline_state_events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Mainline state event not found: {event_id}")
            event = MainlineStateEvent.model_validate_json(row["payload"])
            if event.acknowledged_at is None:
                event.acknowledged_at = datetime.now(UTC)
                connection.execute(
                    """
                    UPDATE mainline_state_events
                    SET acknowledged_at = ?, payload = ? WHERE id = ?
                    """,
                    (event.acknowledged_at.isoformat(), event.model_dump_json(), event.id),
                )
        return event

    def save_proposal(self, proposal: ThemeResearchProposal) -> ThemeResearchProposal:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theme_research_proposals (
                    id, theme_id, assessment_id, action, human_status,
                    auto_execute, run_id, created_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    human_status = excluded.human_status,
                    run_id = excluded.run_id,
                    payload = excluded.payload
                """,
                (
                    proposal.id,
                    proposal.theme_id,
                    proposal.assessment_id,
                    proposal.action,
                    proposal.human_status.value,
                    int(proposal.auto_execute),
                    proposal.run_id,
                    proposal.created_at.isoformat(),
                    proposal.model_dump_json(),
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> ThemeResearchProposal | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM theme_research_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        return ThemeResearchProposal.model_validate_json(row["payload"]) if row else None

    def list_proposals(
        self,
        theme_id: str | None = None,
        *,
        limit: int = 500,
    ) -> list[ThemeResearchProposal]:
        query = "SELECT payload FROM theme_research_proposals"
        parameters: list[object] = []
        if theme_id is not None:
            query += " WHERE theme_id = ?"
            parameters.append(theme_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 5000)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ThemeResearchProposal.model_validate_json(row["payload"]) for row in rows]

    def save_job(self, job: MonitorJob) -> MonitorJob:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO monitor_jobs (
                    id, theme_id, market, as_of_date, policy_id, status,
                    started_at, completed_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    completed_at = excluded.completed_at,
                    payload = excluded.payload
                """,
                (
                    job.id,
                    job.theme_id,
                    job.market,
                    job.as_of_date.isoformat(),
                    job.policy_id,
                    job.status.value,
                    job.started_at.isoformat(),
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.model_dump_json(),
                ),
            )
        return job

    def get_job(self, job_id: str) -> MonitorJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM monitor_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return MonitorJob.model_validate_json(row["payload"]) if row else None

    def list_jobs(self, *, limit: int = 500) -> list[MonitorJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM monitor_jobs
                ORDER BY as_of_date DESC, started_at DESC LIMIT ?
                """,
                (max(1, min(limit, 5000)),),
            ).fetchall()
        return [MonitorJob.model_validate_json(row["payload"]) for row in rows]
