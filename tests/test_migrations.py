from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from capexgraph.cli import app
from capexgraph.runtime import MigrationError, RunStore
from capexgraph.runtime.migrations import (
    MIGRATIONS,
    Migration,
    backup_database,
    database_status,
    restore_database,
    upgrade_database,
)
from capexgraph.tracking.store import TrackingStore

FIXTURE = Path(__file__).parent / "fixtures" / "databases" / "v0_2_legacy.sql"


def _legacy_database(path: Path) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(FIXTURE.read_text(encoding="utf-8"))
    return path


def _counts(path: Path) -> dict[str, int]:
    tables = (
        "runs",
        "checkpoints",
        "tracked_candidates",
        "tracking_snapshots",
        "trigger_events",
    )
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def test_legacy_v0_2_upgrade_preserves_every_record(tmp_path) -> None:
    path = _legacy_database(tmp_path / "legacy.db")
    before = _counts(path)
    initial = database_status(path)

    assert initial.legacy is True
    assert initial.current_version == 0
    assert initial.pending_versions == (1,)

    upgraded = upgrade_database(path)

    assert upgraded.current_version == upgraded.latest_version == 1
    assert upgraded.pending_versions == ()
    assert _counts(path) == before
    assert RunStore(path).load_run("legacy-theme-001") is not None
    assert len(RunStore(path).list_checkpoints("legacy-theme-001")) == 1
    tracking = TrackingStore(path)
    assert tracking.get_candidate("legacy-tracked-001") is not None
    assert len(tracking.list_snapshots("legacy-tracked-001")) == 1
    assert len(tracking.list_events("legacy-tracked-001")) == 1


def test_fresh_and_repeated_upgrade_are_idempotent(tmp_path) -> None:
    path = tmp_path / "fresh.db"

    first = upgrade_database(path)
    second = upgrade_database(path)

    assert first.current_version == second.current_version == 1
    assert first.applied_versions == second.applied_versions == (1,)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_failed_migration_rolls_back_its_schema_changes(tmp_path) -> None:
    path = _legacy_database(tmp_path / "failed.db")
    upgrade_database(path)
    failing = Migration(
        version=2,
        name="intentional_failure",
        statements=(
            "CREATE TABLE should_rollback (id INTEGER PRIMARY KEY)",
            "THIS IS NOT VALID SQL",
        ),
    )

    with pytest.raises(MigrationError, match="intentional_failure"):
        upgrade_database(path, migrations=(*MIGRATIONS, failing))

    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert "should_rollback" not in tables
    assert versions == [(1,)]
    assert RunStore(path).load_run("legacy-theme-001") is not None


def test_backup_and_restore_round_trip(tmp_path) -> None:
    source = _legacy_database(tmp_path / "source.db")
    upgrade_database(source)
    backup = backup_database(source, tmp_path / "backups" / "capexgraph.db")

    with closing(sqlite3.connect(source)) as connection:
        connection.execute("DELETE FROM checkpoints")
        connection.execute("DELETE FROM runs")
        connection.commit()
    assert _counts(source)["runs"] == 0

    restore_database(backup, source, overwrite=True)

    assert _counts(source)["runs"] == 1
    assert RunStore(source).load_run("legacy-theme-001") is not None
    assert database_status(source).up_to_date is True


def test_database_cli_status_upgrade_and_backup(tmp_path) -> None:
    path = _legacy_database(tmp_path / "cli.db")
    runner = CliRunner()

    status = runner.invoke(app, ["db", "status", "--path", str(path)])
    upgraded = runner.invoke(app, ["db", "upgrade", "--path", str(path)])
    backup = runner.invoke(
        app,
        [
            "db",
            "backup",
            "--path",
            str(path),
            "--output",
            str(tmp_path / "cli-backup.db"),
        ],
    )

    assert status.exit_code == 0
    assert "legacy" in status.stdout
    assert upgraded.exit_code == 0
    assert "schema 1" in upgraded.stdout
    assert backup.exit_code == 0
    assert (tmp_path / "cli-backup.db").is_file()
