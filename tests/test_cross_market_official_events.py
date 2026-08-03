from __future__ import annotations

from datetime import date

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from capexgraph.api.app import app
from capexgraph.domain import (
    CorporateEventType,
    EvidenceKind,
    EvidenceStatus,
    RunMode,
    SourceAuthority,
    SourceSuggestion,
)
from capexgraph.events import EventCalendarService
from capexgraph.financials import FinancialFactService, ReviewedDisclosureFactService
from capexgraph.fixtures import seed_frozen_market_fixture
from capexgraph.monitoring import MainlineService, MainlineStore
from capexgraph.providers.filings import OpenDartFinancialFactsProvider
from capexgraph.providers.sources import (
    CninfoSourceProvider,
    KindSourceProvider,
    OpenDartSourceProvider,
    SecEdgarSourceProvider,
)
from capexgraph.sources import SourceDiscoveryService
from capexgraph.themes import ThemeRegistryService, load_frozen_theme_fixture
from capexgraph.tools.evidence import EvidenceCollector, review_run_evidence
from capexgraph.workflows import create_run, load_run


def _public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def test_cninfo_disclosure_maps_to_versioned_event_and_shared_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "安集科技", "CN", date(2026, 8, 3))

    def discover_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "announcements": [
                    {
                        "announcementId": "1212345678",
                        "secCode": "688019",
                        "secName": "安集科技",
                        "announcementTitle": "2026年半年度报告",
                        "announcementTime": 1785686400000,
                        "adjunctUrl": "finalpage/2026-08-03/1212345678.PDF",
                        "announcementTypeName": "半年度报告",
                    }
                ]
            },
            request=request,
        )

    provider = CninfoSourceProvider(
        client=httpx.Client(transport=httpx.MockTransport(discover_handler))
    )
    suggestions = SourceDiscoveryService().discover(
        run.id,
        provider=provider,
        identifier="688019.SH",
    )
    assert suggestions[0].authority == SourceAuthority.REGULATOR
    assert suggestions[0].metadata["ticker"] == "688019.SH"

    initial = EventCalendarService().ingest_suggestions(run.id, suggestions)
    assert initial[0].event_type == CorporateEventType.FINANCIAL_REPORT
    assert initial[0].evidence_id is None

    capture_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><body>安集科技 2026年半年度报告。"
                    "营业收入为12.5亿元。</body></html>"
                ),
                request=request,
            )
        )
    )
    captured = SourceDiscoveryService().capture(
        run.id,
        suggestions[0].id,
        collector=EvidenceCollector(client=capture_client, resolver=_public_resolver),
    )
    with pytest.raises(ValueError, match="human-reviewed"):
        ReviewedDisclosureFactService().preview(run.id, captured.evidence_id or "")
    reviewed = review_run_evidence(run.id, captured.evidence_id or "", approved=True)
    assert reviewed.status == EvidenceStatus.REVIEWED

    versions = EventCalendarService().refresh_from_sources(run.id)
    latest = EventCalendarService().list(run.id)[0]
    assert versions
    assert latest.version == 2
    assert latest.evidence_id == reviewed.id
    assert latest.source_hash == reviewed.source_hash

    extractor = ReviewedDisclosureFactService()
    candidates = extractor.preview(run.id, reviewed.id)
    assert len(candidates) == 1
    assert candidates[0].metric == "revenue"
    assert candidates[0].value == 1_250_000_000
    assert FinancialFactService().list(run.id) == []
    accepted = extractor.decide(run.id, candidates[0].id, accepted=True)
    facts = FinancialFactService().list(run.id)
    assert accepted.fact_id == facts[0].id
    assert facts[0].source_evidence_id == reviewed.id


def test_opendart_and_kind_frozen_disclosures_are_normalized(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "韩国存储", "KR", date(2026, 8, 3))

    def dart_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["crtfc_key"] == "test-secret"
        return httpx.Response(
            200,
            json={
                "status": "000",
                "list": [
                    {
                        "corp_code": "00164779",
                        "corp_name": "SK hynix",
                        "stock_code": "000660",
                        "report_nm": "신규시설투자등",
                        "rcept_no": "20260803000123",
                        "rcept_dt": "20260803",
                        "flr_nm": "SK hynix",
                        "rm": "",
                    }
                ],
            },
            request=request,
        )

    dart = OpenDartSourceProvider(
        "test-secret",
        client=httpx.Client(transport=httpx.MockTransport(dart_handler)),
    )
    dart_items = dart.discover(run, identifier="000660.KO")
    assert dart_items[0].metadata["corp_code"] == "00164779"
    assert "test-secret" not in dart_items[0].model_dump_json()
    dart_event = EventCalendarService().ingest_suggestions(run.id, dart_items)[0]
    assert dart_event.event_type == CorporateEventType.CAPEX_MILESTONE

    kind = KindSourceProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "list": [
                            {
                                "announcement_id": "20260803000456",
                                "title": "기업설명회 개최 안내",
                                "published_at": "2026-08-03",
                                "company_name": "SK hynix",
                                "ticker": "000660",
                            }
                        ]
                    },
                    request=request,
                )
            )
        )
    )
    kind_items = kind.discover(run, identifier="000660")
    assert kind_items[0].metadata["ticker"] == "000660.KO"
    kind_event = EventCalendarService().ingest_suggestions(run.id, kind_items)[0]
    assert kind_event.event_type == CorporateEventType.INVESTOR_DAY


def test_sec_historical_submission_shard_is_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "GOOGL", "US", date(2026, 8, 3))
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
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
                            "accessionNumber": [],
                            "form": [],
                            "filingDate": [],
                            "reportDate": [],
                            "primaryDocument": [],
                        },
                        "files": [
                            {"name": "CIK0001652044-submissions-001.json"},
                            {"name": "CIK0001652044-submissions-002.json"},
                        ],
                    },
                },
                request=request,
            )
        if request.url.path.endswith("-001.json"):
            return httpx.Response(
                200,
                json={
                    "accessionNumber": ["0001652044-15-000001"],
                    "form": ["10-K"],
                    "filingDate": ["2015-02-12"],
                    "reportDate": ["2014-12-31"],
                    "primaryDocument": ["goog-20141231.htm"],
                },
                request=request,
            )
        return httpx.Response(500, request=request)

    provider = SecEdgarSourceProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="CapexGraph test test@example.com",
    )
    result = provider.discover(run, identifier="GOOGL", forms=["10-K"], limit=1)
    assert result[0].published_at == date(2015, 2, 12)
    assert not any(path.endswith("-002.json") for path in requested_paths)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_official_provider_capabilities_are_public_and_credential_safe() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/official/providers")
    assert response.status_code == 200
    payload = response.json()
    assert {item["provider"] for item in payload} >= {
        "sec-edgar-submissions",
        "cninfo-announcements",
        "opendart-disclosures",
        "kind-krx-disclosures",
    }
    assert "test-secret" not in response.text


def test_opendart_financial_facts_share_one_captured_official_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "SK hynix", "KR", date(2026, 8, 3))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "000",
                "list": [
                    {
                        "corp_name": "SK hynix",
                        "stock_code": "000660",
                        "account_id": "ifrs-full_Revenue",
                        "account_nm": "매출액",
                        "thstrm_amount": "12,345,000",
                        "thstrm_dt": "2026.01.01-2026.06.30",
                        "rcept_no": "20260803000123",
                    },
                    {
                        "corp_name": "SK hynix",
                        "stock_code": "000660",
                        "account_id": "dart_OperatingIncomeLoss",
                        "account_nm": "영업이익",
                        "thstrm_amount": "2,345,000",
                        "thstrm_dt": "2026.01.01-2026.06.30",
                        "rcept_no": "20260803000123",
                    },
                ],
            },
            request=request,
        )

    provider = OpenDartFinancialFactsProvider(
        "test-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    facts = FinancialFactService().extract(
        run.id,
        identifier="000660.KO",
        provider=provider,
    )
    revenue = next(item for item in facts if item.metric == "revenue")
    assert revenue.value == 12_345_000
    assert revenue.unit == "KRW"
    assert revenue.period_end == date(2026, 6, 30)
    assert all(item.source_evidence_id == revenue.source_evidence_id for item in facts)
    refreshed = load_run(run.id)
    assert refreshed is not None
    evidence = next(item for item in refreshed.evidence if item.id == revenue.source_evidence_id)
    assert evidence.publisher == "Financial Supervisory Service OpenDART"
    assert "test-secret" not in evidence.model_dump_json()


def test_official_event_creates_human_gated_theme_reevaluation_proposal(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_STATE_DB", str(tmp_path / "event-trigger.db"))
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path / "runs"))
    ThemeRegistryService().persist_import(load_frozen_theme_fixture())
    seed_frozen_market_fixture()
    MainlineService().run_daily(
        "memory-semiconductors",
        market="CN",
        as_of_date=date(2026, 8, 3),
        provider="fixture-market",
    )
    run = create_run(RunMode.ANCHOR, "安集科技", "CN", date(2026, 8, 3))
    suggestion = SourceSuggestion(
        id="cninfo-event-trigger",
        run_id=run.id,
        title="安集科技扩建项目公告",
        url="https://static.cninfo.com.cn/finalpage/example.PDF",
        canonical_url="https://static.cninfo.com.cn/finalpage/example.PDF",
        kind=EvidenceKind.COMPANY_DISCLOSURE,
        publisher="巨潮资讯网",
        authority=SourceAuthority.REGULATOR,
        reason="Frozen official event trigger.",
        provider="cninfo-announcements",
        provider_version="1",
        published_at=date(2026, 8, 3),
        metadata={
            "jurisdiction": "CN",
            "ticker": "688019.SH",
            "company_name": "安集科技",
            "announcement_id": "trigger-001",
            "announcement_type": "投资项目",
            "published_datetime": "2026-08-03T01:00:00Z",
        },
    )

    SourceDiscoveryService().store.add(suggestion)
    EventCalendarService().ingest_suggestions(run.id, [suggestion])
    proposals = MainlineStore().list_proposals("memory-semiconductors")
    triggered = [item for item in proposals if item.action == "reevaluate_candidates"]
    assert len(triggered) == 1
    assert triggered[0].auto_execute is False
    assert triggered[0].human_status.value == "pending"
    assert "安集科技" in triggered[0].reason
