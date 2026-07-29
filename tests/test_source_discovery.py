from __future__ import annotations

from datetime import date

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from capexgraph.api.app import app
from capexgraph.domain import (
    EvidenceKind,
    RunMode,
    SourceAuthority,
    SourceSuggestionStatus,
)
from capexgraph.providers.sources import (
    SecEdgarSourceProvider,
    canonicalize_source_url,
)
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
from capexgraph.tools.evidence import EvidenceCollector, EvidenceSourceRequest
from capexgraph.workflows import create_run, load_run


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _sec_transport(*, filings: bool = True) -> httpx.MockTransport:
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
            recent = (
                {
                    "accessionNumber": ["0001652044-26-000101", "0001652044-26-000099"],
                    "form": ["10-Q", "8-K"],
                    "filingDate": ["2026-07-23", "2026-07-22"],
                    "reportDate": ["2026-06-30", "2026-06-30"],
                    "acceptanceDateTime": [
                        "2026-07-23T20:01:02.000Z",
                        "2026-07-22T20:03:04.000Z",
                    ],
                    "primaryDocument": ["goog-20260630.htm", "goog-20260722.htm"],
                }
                if filings
                else {
                    "accessionNumber": [],
                    "form": [],
                    "filingDate": [],
                    "reportDate": [],
                    "acceptanceDateTime": [],
                    "primaryDocument": [],
                }
            )
            return httpx.Response(
                200,
                json={"name": "Alphabet Inc.", "filings": {"recent": recent}},
                request=request,
            )
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def test_sec_discovery_creates_suggestions_not_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI infrastructure", "US")
    client = httpx.Client(transport=_sec_transport())
    provider = SecEdgarSourceProvider(client=client, user_agent="CapexGraph test test@example.com")

    items = SourceDiscoveryService().discover(
        run.id,
        provider=provider,
        identifier="GOOGL",
        limit=2,
    )

    assert [item.status for item in items] == [
        SourceSuggestionStatus.SUGGESTED,
        SourceSuggestionStatus.SUGGESTED,
    ]
    assert all(item.authority == SourceAuthority.REGULATOR for item in items)
    assert items[0].metadata["form"] == "10-Q"
    assert items[0].metadata["acceptance_datetime"] == "2026-07-23T20:01:02.000Z"
    assert "/Archives/edgar/data/1652044/" in str(items[0].url)
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert refreshed.evidence == []
    assert refreshed.manifest["source_discovery_providers"] == [
        {"name": "sec-edgar-submissions", "version": "2"}
    ]
    assert (tmp_path / run.id / "sources.json").is_file()


def test_sec_discovery_empty_and_provider_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "GOOGL", "US")
    empty = SecEdgarSourceProvider(
        client=httpx.Client(transport=_sec_transport(filings=False)),
        user_agent="CapexGraph test test@example.com",
    )

    assert SourceDiscoveryService().discover(run.id, provider=empty, identifier="GOOGL") == []

    failed = SecEdgarSourceProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, request=request)
            )
        ),
        user_agent="CapexGraph test test@example.com",
    )
    with pytest.raises(httpx.HTTPStatusError):
        SourceDiscoveryService().discover(run.id, provider=failed, identifier="GOOGL")
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert refreshed.manifest["source_discovery_errors"][-1]["provider"] == (
        "sec-edgar-submissions"
    )


def test_sec_provider_loads_project_env_without_overriding_process_env(
    tmp_path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CAPEXGRAPH_SEC_USER_AGENT=CapexGraph env env@example.com\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPEXGRAPH_ENV_FILE", str(env_path))
    monkeypatch.delenv("CAPEXGRAPH_SEC_USER_AGENT", raising=False)

    loaded = SecEdgarSourceProvider(client=httpx.Client())
    assert loaded.user_agent == "CapexGraph env env@example.com"

    monkeypatch.setenv(
        "CAPEXGRAPH_SEC_USER_AGENT",
        "CapexGraph process process@example.com",
    )
    preserved = SecEdgarSourceProvider(client=httpx.Client())
    assert preserved.user_agent == "CapexGraph process process@example.com"


def test_sec_403_explains_required_user_agent_configuration(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    provider = SecEdgarSourceProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(403, request=request)
            )
        ),
        user_agent="CapexGraph incomplete",
    )
    run = create_run(RunMode.THEME, "Alphabet", "US")

    with pytest.raises(
        RuntimeError,
        match=r"CAPEXGRAPH_SEC_USER_AGENT.*real contact address",
    ):
        provider.discover(run, identifier="1652044")


def test_manual_url_classification_and_canonical_deduplication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "Example issuer", "US")
    service = SourceDiscoveryService()

    first = service.suggest_url(
        run.id,
        url="https://investor.example.com/report?b=2&utm_source=test&a=1#page",
        title="Issuer report",
        kind=EvidenceKind.COMPANY_DISCLOSURE,
        issuer_domains=["example.com"],
    )
    duplicate = service.suggest_url(
        run.id,
        url="https://investor.example.com/report?a=1&b=2",
        title="Duplicate URL",
        kind=EvidenceKind.COMPANY_DISCLOSURE,
        issuer_domains=["example.com"],
    )

    assert first.id == duplicate.id
    assert first.authority == SourceAuthority.ISSUER
    assert first.canonical_url == "https://investor.example.com/report?a=1&b=2"
    assert duplicate.metadata["duplicate_url_count"] == 1
    assert len(service.list(run.id)) == 1
    assert canonicalize_source_url("https://SEC.GOV:443/a#x") == "https://sec.gov/a"


def test_capture_creates_evidence_and_deduplicates_identical_content(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "test theme", "US")
    service = SourceDiscoveryService()
    first = service.suggest_url(
        run.id,
        url="https://example.com/a",
        title="First",
        kind=EvidenceKind.FILING,
    )
    second = service.suggest_url(
        run.id,
        url="https://example.com/b",
        title="Second",
        kind=EvidenceKind.FILING,
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body>Same official filing</body></html>",
                request=request,
            )
        )
    )
    collector = EvidenceCollector(client=client, resolver=public_resolver)

    captured = service.capture(run.id, first.id, collector=collector)
    duplicate = service.capture(run.id, second.id, collector=collector)

    assert captured.status == SourceSuggestionStatus.CAPTURED
    assert captured.evidence_id == first.id
    assert duplicate.status == SourceSuggestionStatus.DUPLICATE
    assert duplicate.evidence_id == first.id
    assert duplicate.duplicate_of == first.id
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert len(refreshed.evidence) == 1
    assert refreshed.evidence[0].id == first.id


def test_capture_failure_is_persisted_and_retryable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "test", "US")
    service = SourceDiscoveryService()
    item = service.suggest_url(
        run.id,
        url="http://127.0.0.1/private",
        title="Blocked",
        kind=EvidenceKind.FILING,
    )

    with pytest.raises(SourceCaptureError, match="blocked"):
        service.capture(run.id, item.id)

    failed = service.list(run.id)[0]
    assert failed.status == SourceSuggestionStatus.CAPTURE_FAILED
    assert "blocked" in failed.error


def test_collector_blocks_unsafe_redirect_before_requesting_destination() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
            request=request,
        )

    collector = EvidenceCollector(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )
    with pytest.raises(ValueError, match="blocked"):
        collector.collect(
            "run",
            EvidenceSourceRequest(
                id="redirect",
                title="Redirect",
                kind=EvidenceKind.FILING,
                url="https://example.com/start",
            ),
        )
    assert requests == ["https://example.com/start"]


@pytest.mark.parametrize(
    ("headers", "content", "message"),
    [
        ({"content-type": "application/json"}, b"{}", "HTML or PDF"),
        ({"content-type": "text/html", "content-length": "100"}, b"", "exceeds"),
    ],
)
def test_collector_rejects_bad_content_type_and_declared_oversize(
    headers,
    content,
    message,
) -> None:
    collector = EvidenceCollector(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers=headers,
                    content=content,
                    request=request,
                )
            )
        ),
        max_bytes=10,
        resolver=public_resolver,
    )
    with pytest.raises(ValueError, match=message):
        collector.collect(
            "run",
            EvidenceSourceRequest(
                id="bad",
                title="Bad",
                kind=EvidenceKind.FILING,
                url="https://example.com/bad",
            ),
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_source_queue_api_manual_add_list_and_dismiss(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "manual source", "US", date(2026, 7, 27))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        added = await client.post(
            f"/api/v1/runs/{run.id}/sources/suggest",
            json={
                "url": "https://www.sec.gov/example.htm",
                "title": "SEC source",
                "kind": "filing",
            },
        )
        assert added.status_code == 200
        payload = added.json()
        assert payload["status"] == "suggested"
        assert payload["authority"] == "regulator"

        listed = await client.get(f"/api/v1/runs/{run.id}/sources")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        dismissed = await client.post(
            f"/api/v1/runs/{run.id}/sources/{payload['id']}/dismiss"
        )
        assert dismissed.status_code == 200
        assert dismissed.json()["status"] == "dismissed"
