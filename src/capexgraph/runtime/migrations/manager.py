from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class MigrationError(RuntimeError):
    """Raised when the persisted schema cannot be upgraded safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]
    automatic: bool = True

    @property
    def checksum(self) -> str:
        payload = f"{self.version}:{self.name}\n" + "\n".join(self.statements)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DatabaseStatus:
    path: Path
    exists: bool
    current_version: int
    latest_version: int
    applied_versions: tuple[int, ...]
    pending_versions: tuple[int, ...]
    legacy: bool

    @property
    def up_to_date(self) -> bool:
        return not self.pending_versions


BASELINE_STATEMENTS = (
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
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)",
    """
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
    )
    """,
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="v0_2_baseline", statements=BASELINE_STATEMENTS),
    Migration(
        version=2,
        name="source_suggestion_queue",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS source_suggestions (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                status TEXT NOT NULL,
                provider TEXT NOT NULL,
                authority TEXT NOT NULL,
                content_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(run_id, canonical_url),
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_source_suggestions_run_status
            ON source_suggestions(run_id, status, updated_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_source_suggestions_content_hash
            ON source_suggestions(run_id, content_hash)
            """,
        ),
    ),
    Migration(
        version=3,
        name="versioned_financial_facts",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS financial_facts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                metric TEXT NOT NULL,
                statement TEXT NOT NULL,
                period_end TEXT,
                fact_type TEXT NOT NULL,
                source_evidence_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_financial_facts_run_metric_period
            ON financial_facts(run_id, metric, period_end DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_financial_facts_source
            ON financial_facts(run_id, source_evidence_id)
            """,
        ),
    ),
    Migration(
        version=4,
        name="cross_market_daily_history",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS market_bars (
                ticker TEXT NOT NULL,
                provider TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                market TEXT NOT NULL,
                exchange TEXT NOT NULL,
                currency TEXT NOT NULL,
                timezone TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                adjusted_close REAL,
                volume REAL,
                raw_hash TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, provider, trade_date)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_market_bars_ticker_date
            ON market_bars(ticker, trade_date DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS market_quality_reports (
                ticker TEXT NOT NULL,
                provider TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                first_date TEXT,
                latest_date TEXT,
                bar_count INTEGER NOT NULL,
                source_url TEXT,
                provider_version TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (ticker, provider, raw_hash)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_market_quality_ticker_checked
            ON market_quality_reports(ticker, checked_at DESC)
            """,
        ),
    ),
    Migration(
        version=5,
        name="versioned_corporate_event_calendar",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS corporate_event_versions (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                version INTEGER NOT NULL,
                version_hash TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                ticker TEXT,
                market TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                announced_date TEXT,
                expected_date TEXT,
                effective_date TEXT,
                known_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                source_suggestion_id TEXT,
                evidence_id TEXT,
                payload TEXT NOT NULL,
                UNIQUE (run_id, event_key, version),
                UNIQUE (run_id, event_key, version_hash),
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_corporate_events_run_known
            ON corporate_event_versions(run_id, known_at, observed_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_corporate_events_ticker_effective
            ON corporate_event_versions(ticker, effective_date DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_corporate_events_type_status
            ON corporate_event_versions(event_type, status)
            """,
        ),
    ),
    Migration(
        version=6,
        name="live_signal_gateway_foundation",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS live_signal_observations (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_version TEXT NOT NULL,
                channel TEXT NOT NULL,
                stream TEXT NOT NULL,
                external_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                category TEXT NOT NULL,
                published_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                retention_class TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (provider, channel, external_id, content_hash)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_live_observations_event_key
            ON live_signal_observations(event_key, observed_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_live_observations_channel_observed
            ON live_signal_observations(provider, channel, observed_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS live_signal_versions (
                id TEXT PRIMARY KEY,
                signal_key TEXT NOT NULL,
                version INTEGER NOT NULL,
                version_hash TEXT NOT NULL,
                category TEXT NOT NULL,
                published_at TEXT NOT NULL,
                first_observed_at TEXT NOT NULL,
                last_observed_at TEXT NOT NULL,
                match_status TEXT NOT NULL,
                verification_state TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (signal_key, version),
                UNIQUE (signal_key, version_hash)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_live_signals_last_observed
            ON live_signal_versions(last_observed_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS live_signal_observation_links (
                signal_version_id TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                PRIMARY KEY (signal_version_id, observation_id),
                FOREIGN KEY (signal_version_id)
                    REFERENCES live_signal_versions(id) ON DELETE CASCADE,
                FOREIGN KEY (observation_id)
                    REFERENCES live_signal_observations(id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_live_signal_links_observation
            ON live_signal_observation_links(observation_id, signal_version_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS live_provider_checkpoints (
                provider TEXT NOT NULL,
                provider_version TEXT NOT NULL,
                channel TEXT NOT NULL,
                stream TEXT NOT NULL,
                cursor TEXT NOT NULL DEFAULT '',
                last_external_id TEXT,
                last_published_at TEXT,
                last_observed_at TEXT,
                health TEXT NOT NULL,
                calls_used INTEGER NOT NULL DEFAULT 0,
                call_budget INTEGER,
                budget_date TEXT,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                PRIMARY KEY (provider, channel, stream)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS live_dead_letters (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL,
                stream TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                error TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_live_dead_letters_observed
            ON live_dead_letters(observed_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS research_action_proposals (
                id TEXT PRIMARY KEY,
                signal_key TEXT NOT NULL,
                analysis_version INTEGER NOT NULL,
                human_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (signal_key, analysis_version)
            )
            """,
        ),
    ),
)

MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""

LEGACY_TABLES = frozenset(
    {
        "runs",
        "checkpoints",
        "tracked_candidates",
        "tracking_snapshots",
        "trigger_events",
    }
)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _applied_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    if "schema_migrations" not in _table_names(connection):
        return []
    return connection.execute(
        "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()


def _validate_registry(migrations: Sequence[Migration]) -> None:
    versions = [migration.version for migration in migrations]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise MigrationError("Migration versions must be unique and sorted")
    if versions and versions != list(range(1, versions[-1] + 1)):
        raise MigrationError("Migration versions must be contiguous and start at 1")


def _validate_applied(
    rows: Sequence[sqlite3.Row],
    migrations: Sequence[Migration],
) -> None:
    by_version = {migration.version: migration for migration in migrations}
    for row in rows:
        version = int(row["version"])
        migration = by_version.get(version)
        if migration is None:
            raise MigrationError(
                f"Database schema version {version} is newer than this CapexGraph build"
            )
        if row["name"] != migration.name or row["checksum"] != migration.checksum:
            raise MigrationError(
                f"Migration {version} does not match the registered checksum; "
                "restore a known backup before continuing"
            )


def database_status(
    path: Path,
    *,
    migrations: Sequence[Migration] | None = None,
) -> DatabaseStatus:
    registry = tuple(migrations or MIGRATIONS)
    _validate_registry(registry)
    resolved = path.resolve()
    latest = registry[-1].version if registry else 0
    if not resolved.exists():
        return DatabaseStatus(
            path=resolved,
            exists=False,
            current_version=0,
            latest_version=latest,
            applied_versions=(),
            pending_versions=tuple(migration.version for migration in registry),
            legacy=False,
        )

    with closing(_connect(resolved)) as connection:
        tables = _table_names(connection)
        rows = _applied_rows(connection)
        _validate_applied(rows, registry)

    applied = tuple(int(row["version"]) for row in rows)
    current = applied[-1] if applied else 0
    pending = tuple(
        migration.version for migration in registry if migration.version not in applied
    )
    return DatabaseStatus(
        path=resolved,
        exists=True,
        current_version=current,
        latest_version=latest,
        applied_versions=applied,
        pending_versions=pending,
        legacy=not rows and bool(tables & LEGACY_TABLES),
    )


def upgrade_database(
    path: Path,
    *,
    automatic_only: bool = False,
    migrations: Sequence[Migration] | None = None,
) -> DatabaseStatus:
    registry = tuple(migrations or MIGRATIONS)
    _validate_registry(registry)
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    connection = _connect(resolved)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(MIGRATION_TABLE)
        connection.commit()

        rows = _applied_rows(connection)
        _validate_applied(rows, registry)
        applied = {int(row["version"]) for row in rows}

        for migration in registry:
            if migration.version in applied:
                continue
            if automatic_only and not migration.automatic:
                raise MigrationError(
                    f"Database migration {migration.version} ({migration.name}) "
                    "requires `capexgraph db upgrade`"
                )
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum, applied_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.execute(f"PRAGMA user_version = {migration.version}")
                connection.commit()
            except Exception as error:
                connection.rollback()
                raise MigrationError(
                    f"Migration {migration.version} ({migration.name}) failed: {error}"
                ) from error
    finally:
        connection.close()

    return database_status(resolved, migrations=registry)


def ensure_database(path: Path) -> DatabaseStatus:
    """Apply only migrations explicitly marked safe for application startup."""

    return upgrade_database(path, automatic_only=True)


def _temporary_database_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.{os.getpid()}.tmp")


def _verify_database(path: Path) -> None:
    with closing(_connect(path)) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise MigrationError(f"SQLite integrity check failed for {path}")


def backup_database(source: Path, output: Path, *, overwrite: bool = False) -> Path:
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Database not found: {source}")
    if source == output:
        raise ValueError("Backup output must differ from the source database")
    if output.exists() and not overwrite:
        raise FileExistsError(f"Backup already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_database_path(output)
    if temporary.exists():
        temporary.unlink()
    try:
        with (
            closing(_connect(source)) as source_connection,
            closing(_connect(temporary)) as target_connection,
        ):
            source_connection.backup(target_connection)
        _verify_database(temporary)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def restore_database(
    backup: Path,
    target: Path,
    *,
    overwrite: bool = False,
    upgrade: bool = True,
) -> Path:
    backup = backup.resolve()
    target = target.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"Backup not found: {backup}")
    if backup == target:
        raise ValueError("Restore source must differ from the target database")
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"Target database already exists: {target}; pass --force to replace it"
        )

    _verify_database(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_database_path(target)
    if temporary.exists():
        temporary.unlink()
    try:
        with (
            closing(_connect(backup)) as source_connection,
            closing(_connect(temporary)) as target_connection,
        ):
            source_connection.backup(target_connection)
        _verify_database(temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    if upgrade:
        upgrade_database(target)
    return target
