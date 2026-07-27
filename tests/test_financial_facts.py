from __future__ import annotations

import json

import httpx
import pytest

from capexgraph.domain import EvidenceStatus, FinancialFactType, RunMode
from capexgraph.financials import FinancialFactService
from capexgraph.providers.filings import SecCompanyFactsProvider
from capexgraph.reporting import render_run_report
from capexgraph.research.theme import _prompt
from capexgraph.workflows import create_run, load_run


def company_registry() -> dict:
    return {
        "0": {
            "cik_str": 1652044,
            "ticker": "GOOGL",
            "title": "Alphabet Inc.",
        }
    }


def fact(
    value: float,
    *,
    start: str | None = "2026-01-01",
    end: str = "2026-06-30",
    filed: str = "2026-07-22",
    accession: str = "0001652044-26-000001",
    form: str = "10-Q",
) -> dict:
    payload = {
        "end": end,
        "val": value,
        "accn": accession,
        "fy": 2026,
        "fp": "Q2",
        "form": form,
        "filed": filed,
    }
    if start:
        payload["start"] = start
    return payload


def company_facts_payload() -> dict:
    revenue_entries = [
        fact(
            900,
            start="2025-01-01",
            end="2025-06-30",
            filed="2025-07-20",
            accession="original",
        ),
        fact(
            900,
            start="2025-01-01",
            end="2025-06-30",
            filed="2025-07-21",
            accession="duplicate-same-value",
        ),
        fact(
            910,
            start="2025-01-01",
            end="2025-06-30",
            filed="2026-02-01",
            accession="restatement",
        ),
        fact(119796),
    ]
    concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {"USD": revenue_entries}
        },
        "OperatingIncomeLoss": {"units": {"USD": [fact(35000)]}},
        "NetIncomeLoss": {"units": {"USD": [fact(28000)]}},
        "NetCashProvidedByUsedInOperatingActivities": {
            "units": {"USD": [fact(50000)]}
        },
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "units": {"USD": [fact(44924)]}
        },
        "CashAndCashEquivalentsAtCarryingValue": {
            "units": {"USD": [fact(95000, start=None)]}
        },
        "PropertyPlantAndEquipmentNet": {
            "units": {"USD": [fact(210000, start=None)]}
        },
    }
    return {
        "cik": 1652044,
        "entityName": "Alphabet Inc.",
        "facts": {"us-gaap": concepts},
    }


def sec_handler(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        body = company_registry() if "company_tickers" in request.url.path else payload
        return httpx.Response(200, json=body, request=request)

    return handler


def test_sec_company_facts_are_versioned_traced_and_derived(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI CapEx", "US", "2026-07-22")
    provider = SecCompanyFactsProvider(
        client=httpx.Client(transport=httpx.MockTransport(sec_handler(company_facts_payload())))
    )

    facts = FinancialFactService().extract(run.id, identifier="GOOGL", provider=provider)

    refreshed = load_run(run.id)
    assert refreshed is not None
    evidence_id = refreshed.manifest["financial_facts"]["source_evidence_id"]
    evidence = next(item for item in refreshed.evidence if item.id == evidence_id)
    assert evidence.status == EvidenceStatus.CAPTURED
    assert evidence.source_hash
    assert evidence.content_type == "application/json"
    assert (tmp_path / run.id / str(evidence.local_path)).is_file()

    prior_revenue = [
        item
        for item in facts
        if item.metric == "revenue" and str(item.period_end) == "2025-06-30"
    ]
    assert len(prior_revenue) == 2
    assert {item.value for item in prior_revenue} == {900, 910}
    assert {item.fact_type for item in prior_revenue} == {
        FinancialFactType.REPORTED,
        FinancialFactType.RESTATED,
    }
    missing_debt = next(item for item in facts if item.metric == "debt")
    assert missing_debt.fact_type == FinancialFactType.MISSING
    assert missing_debt.value is None

    free_cash_flow = next(
        item
        for item in facts
        if item.metric == "free_cash_flow" and item.value is not None
    )
    assert free_cash_flow.value == 5076
    assert free_cash_flow.fact_type == FinancialFactType.DERIVED
    assert free_cash_flow.formula == "operating_cash_flow - capital_expenditures"
    assert len(free_cash_flow.input_fact_ids) == 2
    assert all(item.source_evidence_id == evidence_id for item in facts)
    assert all(item.source_locator for item in facts)

    artifact = json.loads(
        (tmp_path / run.id / "financials" / "facts.json").read_text(encoding="utf-8")
    )
    assert artifact["provider"] == {"name": "sec-companyfacts", "version": "1"}
    assert len(artifact["items"]) == len(facts)
    assert refreshed.manifest["data_provider_records"][-1] == {
        "name": "sec-companyfacts",
        "version": "1",
    }
    research_prompt = json.loads(_prompt(refreshed, "Use filing facts.", {}))
    injected = research_prompt["context"]["financial_facts"]
    assert any(item["metric"] == "capital_expenditures" for item in injected)
    assert any(item["source_locator"].startswith("facts.us-gaap") for item in injected)
    report = render_run_report(run.id).read_text(encoding="utf-8")
    assert "Providers and evidence coverage" in report
    assert "Source locator" in report
    assert "facts.us-gaap.PaymentsToAcquirePropertyPlantAndEquipment" in report
    assert "Facts, inferences, and unverified hypotheses" in report


def test_sec_company_facts_unit_conflict_fails_and_is_persisted(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI CapEx", "US", "2026-07-22")
    payload = company_facts_payload()
    payload["facts"]["us-gaap"][
        "PaymentsToAcquirePropertyPlantAndEquipment"
    ] = {"units": {"EUR": [fact(44924)]}}
    provider = SecCompanyFactsProvider(
        client=httpx.Client(transport=httpx.MockTransport(sec_handler(payload)))
    )

    with pytest.raises(ValueError, match="has no USD unit"):
        FinancialFactService().extract(run.id, identifier="GOOGL", provider=provider)

    refreshed = load_run(run.id)
    assert refreshed is not None
    assert "has no USD unit" in refreshed.manifest["financial_fact_errors"][-1]["error"]
    assert "financial_facts" not in refreshed.manifest
    assert len(refreshed.evidence) == 1
    assert refreshed.evidence[0].status == EvidenceStatus.CAPTURED


def test_sec_company_facts_period_value_conflict_fails_deterministically(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI CapEx", "US", "2026-07-22")
    payload = company_facts_payload()
    payload["facts"]["us-gaap"][
        "OperatingIncomeLoss"
    ]["units"]["USD"].append(fact(36000))
    provider = SecCompanyFactsProvider(
        client=httpx.Client(transport=httpx.MockTransport(sec_handler(payload)))
    )

    with pytest.raises(ValueError, match="one filing reports multiple values"):
        FinancialFactService().extract(run.id, identifier="GOOGL", provider=provider)


def test_exact_cik_bypasses_remote_ticker_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Alphabet AI CapEx", "US", "2026-07-22")
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, json=company_facts_payload(), request=request)

    provider = SecCompanyFactsProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    facts = FinancialFactService().extract(run.id, identifier="1652044", provider=provider)

    assert requested_paths == ["/api/xbrl/companyfacts/CIK0001652044.json"]
    assert {item.ticker for item in facts} == {"GOOG"}
