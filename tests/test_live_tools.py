from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from capexgraph.domain import EvidenceKind, EvidenceStatus, FinancialMetric, MarketBar, RunMode
from capexgraph.tools.evidence import (
    EvidenceCollector,
    EvidenceSourceRequest,
    collect_evidence_for_run,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metric_items
from capexgraph.tools.identity import TickerResolver, canonical_ticker
from capexgraph.tools.market import calculate_market_snapshot
from capexgraph.workflows import create_run, load_run


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def test_evidence_capture_hash_and_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "test theme", "CN")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("CapexGraph")
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><body><h1>Official filing</h1>"
                "<script>ignore()</script><p>Fact A.</p></body></html>"
            ),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = EvidenceCollector(client=client, resolver=public_resolver)
    document = collect_evidence_for_run(
        run.id,
        EvidenceSourceRequest(
            id="filing-1",
            title="Official filing",
            kind=EvidenceKind.FILING,
            url="https://example.com/filing",
        ),
        collector=collector,
    )

    assert document.evidence.status == EvidenceStatus.CAPTURED
    assert "Fact A" in document.text
    assert "ignore" not in document.text
    assert len(document.evidence.source_hash or "") == 64
    assert (tmp_path / run.id / "sources" / "filing-1.html").is_file()
    reviewed = review_run_evidence(run.id, "filing-1", approved=True)
    assert reviewed.status == EvidenceStatus.REVIEWED


def test_evidence_review_detects_tampering(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "test theme", "CN")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="source", request=request)
        )
    )
    collect_evidence_for_run(
        run.id,
        EvidenceSourceRequest(
            id="source-1",
            title="Source",
            kind=EvidenceKind.COMPANY_DISCLOSURE,
            url="https://example.com/source",
        ),
        collector=EvidenceCollector(client=client, resolver=public_resolver),
    )
    (tmp_path / run.id / "sources" / "source-1.html").write_text("tampered", "utf-8")

    with pytest.raises(ValueError, match="hash does not match"):
        review_run_evidence(run.id, "source-1", approved=True)


def test_evidence_collector_blocks_private_urls() -> None:
    collector = EvidenceCollector(allow_private=False)
    source = EvidenceSourceRequest(
        id="private",
        title="Private",
        kind=EvidenceKind.NEWS,
        url="http://127.0.0.1/admin",
    )
    with pytest.raises(ValueError, match="blocked"):
        collector.collect("run", source)


def test_ticker_resolution_is_canonical_and_registry_backed() -> None:
    resolver = TickerResolver()
    identity = resolver.resolve("兆易创新")

    assert identity.ticker == "603986.SH"
    assert identity.name == "兆易创新"
    assert canonical_ticker("688126.SS") == "688126.SH"
    assert canonical_ticker("000001") == "000001.SZ"


def test_market_snapshot_calculates_stage_and_returns() -> None:
    start = date(2025, 1, 1)
    bars = [
        MarketBar(
            date=start + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000,
        )
        for index in range(130)
    ]

    snapshot = calculate_market_snapshot(
        "603986.SH",
        bars,
        provider="fixture",
        currency="CNY",
    )

    assert snapshot.price == 230
    assert snapshot.ret_1m_pct is not None
    assert snapshot.ret_3m_pct is not None
    assert snapshot.above_sma50 is True
    assert snapshot.stage in {"early_uptrend", "extended"}


def test_financial_metrics_require_existing_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "603986", "CN")
    metric = FinancialMetric(
        ticker="603986.SH",
        metric="revenue",
        period_end="2025-12-31",
        value=100,
        unit="CNY million",
        source_evidence_id="missing",
    )

    with pytest.raises(ValueError, match="missing evidence"):
        attach_financial_metric_items(run.id, [metric])

    metric.source_evidence_id = None
    attached = attach_financial_metric_items(run.id, [metric])
    assert len(attached) == 1
    refreshed = load_run(run.id)
    assert refreshed is not None
    assert refreshed.manifest["financial_metrics"]["count"] == 1
