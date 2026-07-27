from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from capexgraph.domain import FinancialFact
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path


class FinancialFactStore:
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

    def add(self, run_id: str, fact: FinancialFact) -> FinancialFact:
        return self.add_many(run_id, [fact])[0]

    def add_many(self, run_id: str, facts: list[FinancialFact]) -> list[FinancialFact]:
        persisted: list[FinancialFact] = []
        with self._connect() as connection:
            for fact in facts:
                row = connection.execute(
                    "SELECT payload FROM financial_facts WHERE id = ?",
                    (fact.id,),
                ).fetchone()
                if row is not None:
                    existing = FinancialFact.model_validate_json(row["payload"])
                    if existing != fact:
                        raise ValueError(
                            "Financial fact identity conflict; historical facts are immutable: "
                            f"{fact.id}"
                        )
                    persisted.append(existing)
                    continue
                connection.execute(
                    """
                    INSERT INTO financial_facts (
                        id, run_id, ticker, metric, statement, period_end, fact_type,
                        source_evidence_id, created_at, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact.id,
                        run_id,
                        fact.ticker,
                        fact.metric,
                        fact.statement.value,
                        fact.period_end.isoformat() if fact.period_end else None,
                        fact.fact_type.value,
                        fact.source_evidence_id,
                        datetime.now(UTC).isoformat(),
                        fact.model_dump_json(),
                    ),
                )
                persisted.append(fact)
        return persisted

    def list(self, run_id: str) -> list[FinancialFact]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM financial_facts
                WHERE run_id = ?
                ORDER BY period_end DESC, statement, metric, created_at
                """,
                (run_id,),
            ).fetchall()
        return [FinancialFact.model_validate_json(row["payload"]) for row in rows]
