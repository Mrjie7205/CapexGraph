from __future__ import annotations

import json
from pathlib import Path

import httpx

from capexgraph.domain import EvidenceStatus, RunMode, RunStatus
from capexgraph.providers import ProviderName
from capexgraph.reporting import render_run_report
from capexgraph.research import build_executor_for_run
from capexgraph.tools.evidence import (
    EvidenceCollector,
    EvidencePack,
    collect_evidence_pack,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metrics
from capexgraph.tools.identity import TickerResolver
from capexgraph.workflows import create_run

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "alphabet_q2_2026"
SUBJECT = "Alphabet 2026年Q2 AI资本开支传导"


def public_resolver(*_args):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def frozen_source_handler(request: httpx.Request) -> httpx.Response:
    if "earnings-release.pdf" in request.url.path:
        text = """
        <html><body>
        <h1>Alphabet Announces Second Quarter 2026 Results</h1>
        <p>Revenues were $119,796 million and Google Cloud revenue was $24,768 million.</p>
        <p>Purchases of property and equipment were $44,924 million.</p>
        <p>Free cash flow was negative $5,855 million.</p>
        <p>Equity securities gain was $99,031 million with a $6.26 EPS effect.</p>
        </body></html>
        """
    else:
        text = """
        <html><body>
        <h1>Q2 2026 earnings call: Remarks from our CEO</h1>
        <p>Cloud backlog grew to $514 billion.</p>
        <p>Demand remains supply constrained and APIs process 22 billion tokens per minute.</p>
        <p>Virgo Network connects accelerators across multiple data-center sites.</p>
        </body></html>
        """
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=text,
        request=request,
    )


def test_alphabet_q2_frozen_replay_preserves_evidence_boundaries(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, SUBJECT, "US", "2026-07-22")

    completed = build_executor_for_run(run, provider=ProviderName.FIXTURE).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert completed.manifest["model"] == "golden-alphabet-q2-2026-ai-capex-v1"
    assert len(completed.nodes) == 5
    assert len(completed.edges) == 3
    assert len(completed.evidence) == 2
    assert len(completed.candidates) == 3
    assert not any("nvidia" in node.label.casefold() for node in completed.nodes)

    power_edges = [
        edge
        for edge in completed.edges
        if "hypothesis-power-cooling" in {edge.source, edge.target}
    ]
    assert power_edges == []

    decision = json.loads((tmp_path / run.id / "decision.json").read_text(encoding="utf-8"))
    limitations = " ".join(decision["limitations"])
    assert "尚未自动注入Theme Scan推理上下文" in limitations
    assert "没有建立任何具名外部供应商关系" in limitations


def test_alphabet_q2_capture_review_financials_and_replay(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, SUBJECT, "US", "2026-07-22")
    pack = EvidencePack.model_validate_json(
        (CASE_DIR / "evidence_pack.json").read_text(encoding="utf-8")
    )
    collector = EvidenceCollector(
        client=httpx.Client(transport=httpx.MockTransport(frozen_source_handler)),
        resolver=public_resolver,
    )

    documents = collect_evidence_pack(run.id, pack, collector=collector)
    assert len(documents) == 2
    for document in documents:
        review_run_evidence(run.id, document.evidence.id, approved=True)

    metrics = attach_financial_metrics(run.id, CASE_DIR / "financial_metrics.csv")
    assert len(metrics) == 11
    assert next(item for item in metrics if item.metric == "capital_expenditures").value == 44924
    assert next(item for item in metrics if item.metric == "free_cash_flow").value == -5855
    assert next(item for item in metrics if item.metric == "equity_gain_eps_effect").value == 6.26

    completed = build_executor_for_run(run, provider=ProviderName.FIXTURE).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert all(item.status == EvidenceStatus.REVIEWED for item in completed.evidence)
    assert all(item.source_hash for item in completed.evidence)
    assert all(item.local_path for item in completed.evidence)
    assert completed.manifest["financial_metrics"]["count"] == 11
    assert all(
        edge.metadata["reviewed_sources"] is True for edge in completed.edges
    )
    report_path = render_run_report(completed.id)
    report = report_path.read_text(encoding="utf-8")
    assert '<html lang="zh-CN">' in report
    assert "AI加速器与服务器容量" in report
    assert "04 / 财务与经营指标" in report
    assert "Google Cloud收入同比" in report
    assert "仅供研究和教育，不构成投资建议。" in report


def test_alphabet_ticker_identity_is_registry_backed() -> None:
    resolver = TickerResolver()

    class_a = resolver.resolve("GOOGL")
    company = resolver.resolve("Alphabet")

    assert class_a.ticker == "GOOGL"
    assert class_a.currency == "USD"
    assert company.ticker == "GOOG"
