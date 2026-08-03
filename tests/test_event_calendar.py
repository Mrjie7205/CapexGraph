from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from typer.testing import CliRunner

from capexgraph.api.app import app
from capexgraph.cli import app as cli_app
from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    CorporateEventVersion,
    RunMode,
    SourceSuggestionStatus,
)
from capexgraph.events import (
    EventCalendarService,
    EventCalendarStore,
    parse_sec_acceptance,
)
from capexgraph.providers.sources import SecEdgarSourceProvider
from capexgraph.sources import SourceDiscoveryService
from capexgraph.tools.evidence import EvidenceCollector
from capexgraph.workflows import create_run, load_run


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _sec_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 1652044,
                        "ticker": "GOOGL",
                        "title": "Alphabet Inc.",
                    }
                },
                request=request,
            )
        if request.url.path == "/submissions/CIK0001652044.json":
            return httpx.Response(
                200,
                json={
                    "name": "Alphabet Inc.",
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0001652044-26-000101",
                                "0001652044-26-000099",
                            ],
                            "form": ["10-Q", "8-K"],
                            "filingDate": ["2026-07-23", "2026-07-22"],
                            "reportDate": ["2026-06-30", "2026-06-30"],
                            "acceptanceDateTime": [
                                "2026-07-23T20:01:02.000Z",
                                "2026-07-22T20:03:04.000Z",
                            ],
                            "primaryDocument": [
                                "goog-20260630.htm",
                                "goog-20260722.htm",
                            ],
                            "items": ["", "2.02,9.01"],
                            "isXBRL": [1, 1],
                            "isInlineXBRL": [1, 1],
                        }
                    },
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def _sec_provider() -> SecEdgarSourceProvider:
    return SecEdgarSourceProvider(
        client=httpx.Client(transport=_sec_transport()),
        user_agent="CapexGraph test test@example.com",
    )


def test_event_contract_requires_timeline_source_and_aware_datetimes() -> None:
    payload = {
        "id": "event-1",
        "event_key": "sec:1:accession",
        "version": 1,
        "version_hash": "a" * 64,
        "run_id": "run-1",
        "entity_id": "sec-cik-0000000001",
        "ticker": "TEST",
        "entity_name": "Test Inc.",
        "market": "US",
        "event_type": CorporateEventType.REGULATORY_FILING,
        "status": CorporateEventStatus.OCCURRED,
        "title": "Test filing",
        "effective_date": "2026-07-23",
        "known_at": datetime(2026, 7, 23, 20, 0),
        "observed_at": datetime(2026, 7, 23, 20, 1, tzinfo=UTC),
        "source_suggestion_id": "source-1",
        "source_url": "https://www.sec.gov/example",
        "provider": "fixture",
        "provider_version": "1",
        "external_id": "accession",
        "revision_reason": "test",
    }

    with pytest.raises(ValidationError, match="timezone-aware"):
        CorporateEventVersion(**payload)

    payload["known_at"] = datetime(2026, 7, 23, 20, 0, tzinfo=UTC)
    event = CorporateEventVersion(**payload)
    assert event.status == CorporateEventStatus.OCCURRED


def test_sec_acceptance_parses_iso_and_compact_formats() -> None:
    assert parse_sec_acceptance("2026-07-23T20:01:02.000Z") == datetime(
        2026,
        7,
        23,
        20,
        1,
        2,
        tzinfo=UTC,
    )
    assert parse_sec_acceptance("20260723200102") == datetime(
        2026,
        7,
        23,
        20,
        1,
        2,
        tzinfo=UTC,
    )
    assert parse_sec_acceptance("invalid") is None


def test_sec_discovery_builds_idempotent_versioned_event_calendar(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI infrastructure", "US")
    service = EventCalendarService()

    first = service.discover_sec_filings(
        run.id,
        provider=_sec_provider(),
        identifier="GOOGL",
        limit=2,
    )
    repeated = service.discover_sec_filings(
        run.id,
        provider=_sec_provider(),
        identifier="GOOGL",
        limit=2,
    )

    assert len(first) == len(repeated) == 2
    assert first[0].event_type == CorporateEventType.FINANCIAL_REPORT
    assert first[1].event_type == CorporateEventType.REGULATORY_FILING
    assert first[0].status == CorporateEventStatus.OCCURRED
    assert first[0].known_at == datetime(2026, 7, 23, 20, 1, 2, tzinfo=UTC)
    assert first[0].source_suggestion_id
    assert first[0].evidence_id is None
    assert first[0].metadata["source_provider"] == "sec-edgar-submissions"
    assert first[0].metadata["source_provider_version"] == "2"
    assert all(item.version == 1 for item in repeated)
    assert len(service.list(run.id, latest_only=False)) == 2

    artifact = json.loads((tmp_path / run.id / "events.json").read_text(encoding="utf-8"))
    assert len(artifact["latest"]) == 2
    assert len(artifact["versions"]) == 2
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert refreshed.manifest["event_calendar"]["latest_count"] == 2

    with closing(sqlite3.connect(tmp_path / "capexgraph.db")) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "corporate_event_versions" in tables


def test_capture_appends_evidence_linked_version_and_as_of_preserves_history(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "GOOGL", "US")
    calendar = EventCalendarService()
    discovered = calendar.discover_sec_filings(
        run.id,
        provider=_sec_provider(),
        identifier="GOOGL",
        forms=["10-Q"],
        limit=1,
    )[0]

    capture_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body>Official quarterly filing.</body></html>",
                request=request,
            )
        )
    )
    suggestion = SourceDiscoveryService().capture(
        run.id,
        discovered.source_suggestion_id or "",
        collector=EvidenceCollector(client=capture_client, resolver=public_resolver),
    )

    latest = EventCalendarService().list(run.id)[0]
    history = EventCalendarService().list(run.id, latest_only=False)
    point_in_time = EventCalendarService().list(
        run.id,
        as_of=discovered.observed_at,
    )

    assert suggestion.evidence_id is not None
    assert latest.version == 2
    assert latest.evidence_id == suggestion.evidence_id
    assert latest.source_hash == suggestion.content_hash
    assert latest.revision_reason == "captured_evidence_linked"
    assert [item.version for item in history] == [2, 1]
    assert point_in_time[0].version == 1
    assert point_in_time[0].evidence_id is None


def test_event_projection_failure_does_not_undo_successful_source_capture(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "GOOGL", "US")
    discovered = EventCalendarService().discover_sec_filings(
        run.id,
        provider=_sec_provider(),
        identifier="GOOGL",
        forms=["10-Q"],
        limit=1,
    )[0]

    def fail_projection(*_args, **_kwargs):
        raise RuntimeError("event projection unavailable")

    monkeypatch.setattr(EventCalendarService, "ingest_suggestions", fail_projection)
    capture_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body>Official quarterly filing.</body></html>",
                request=request,
            )
        )
    )
    captured = SourceDiscoveryService().capture(
        run.id,
        discovered.source_suggestion_id or "",
        collector=EvidenceCollector(client=capture_client, resolver=public_resolver),
    )

    refreshed = load_run(run.id)
    assert captured.status == SourceSuggestionStatus.CAPTURED
    assert captured.evidence_id is not None
    assert refreshed is not None
    assert len(refreshed.evidence) == 1
    assert refreshed.manifest["event_calendar_errors"][-1]["suggestion_id"] == captured.id
    assert "event projection unavailable" in (
        refreshed.manifest["event_calendar_errors"][-1]["error"]
    )


@pytest.mark.anyio
async def test_event_api_and_cli_read_same_calendar(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI infrastructure", "US")
    EventCalendarService().discover_sec_filings(
        run.id,
        provider=_sec_provider(),
        identifier="GOOGL",
        forms=["10-Q"],
        limit=1,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/runs/{run.id}/events")
        history = await client.get(
            f"/api/v1/runs/{run.id}/events",
            params={"history": "true", "type": "financial_report"},
        )

    assert response.status_code == 200
    assert response.json()[0]["ticker"] == "GOOGL"
    assert history.status_code == 200
    assert history.json()[0]["event_type"] == "financial_report"

    result = CliRunner().invoke(cli_app, ["events", "list", run.id])
    assert result.exit_code == 0
    assert "corporate event calendar" in result.stdout
    assert "GOOGL" in result.stdout


def test_event_store_filters_dates_types_and_latest_versions(tmp_path) -> None:
    store = EventCalendarStore(tmp_path / "events.db")
    with closing(sqlite3.connect(tmp_path / "events.db")) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                id, mode, subject, market, as_of_date, status,
                created_at, updated_at, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "theme",
                "test",
                "US",
                "2026-07-23",
                "created",
                "2026-07-23T00:00:00+00:00",
                "2026-07-23T00:00:00+00:00",
                "{}",
            ),
        )
        connection.commit()

    base = CorporateEventVersion(
        id="event-v1",
        event_key="sec:1:a",
        version=1,
        version_hash="1" * 64,
        run_id="run-1",
        entity_id="sec-cik-0000000001",
        ticker="TEST",
        entity_name="Test Inc.",
        market="US",
        event_type=CorporateEventType.REGULATORY_FILING,
        status=CorporateEventStatus.OCCURRED,
        title="Filing",
        effective_date=date(2026, 7, 23),
        known_at=datetime(2026, 7, 23, 20, tzinfo=UTC),
        observed_at=datetime(2026, 7, 23, 21, tzinfo=UTC),
        source_suggestion_id="source-1",
        source_url="https://www.sec.gov/example",
        provider="fixture",
        provider_version="1",
        external_id="a",
        revision_reason="discovered",
    )
    revised = base.model_copy(
        update={
            "id": "event-v2",
            "version": 2,
            "version_hash": "2" * 64,
            "evidence_id": "evidence-1",
            "observed_at": datetime(2026, 7, 24, 21, tzinfo=UTC),
            "revision_reason": "evidence_linked",
        }
    )
    store.save(base)
    store.save(revised)

    assert store.list("run-1")[0].version == 2
    assert len(store.list("run-1", latest_only=False)) == 2
    assert store.list(
        "run-1",
        as_of=datetime(2026, 7, 23, 23, tzinfo=UTC),
    )[0].version == 1
    assert store.list(
        "run-1",
        event_type=CorporateEventType.FINANCIAL_REPORT,
    ) == []
