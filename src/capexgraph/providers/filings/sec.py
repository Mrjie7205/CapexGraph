from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from capexgraph.config import load_project_env
from capexgraph.domain import (
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    FinancialFact,
    FinancialFactType,
    FinancialStatement,
    ResearchRun,
)
from capexgraph.providers.filings.base import (
    FilingFactsResult,
    FilingFactsValidationError,
)
from capexgraph.providers.sources.sec import (
    COMPANY_TICKERS_URL,
    DEFAULT_SEC_USER_AGENT,
    raise_for_sec_status,
)
from capexgraph.runtime.artifacts import atomic_write_bytes, atomic_write_text
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.identity import TickerResolver, canonical_ticker

COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ALLOWED_FORMS = frozenset({"10-K", "10-Q", "20-F", "6-K"})
MAX_COMPANY_FACTS_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class MetricDefinition:
    metric: str
    statement: FinancialStatement
    concepts: tuple[str, ...]
    expected_unit: str = "USD"


METRICS = (
    MetricDefinition(
        "revenue",
        FinancialStatement.INCOME,
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
    ),
    MetricDefinition(
        "operating_income",
        FinancialStatement.INCOME,
        ("OperatingIncomeLoss",),
    ),
    MetricDefinition(
        "net_income",
        FinancialStatement.INCOME,
        ("NetIncomeLoss", "ProfitLoss"),
    ),
    MetricDefinition(
        "operating_cash_flow",
        FinancialStatement.CASH_FLOW,
        ("NetCashProvidedByUsedInOperatingActivities",),
    ),
    MetricDefinition(
        "capital_expenditures",
        FinancialStatement.CASH_FLOW,
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsForAdditionsToPropertyPlantAndEquipment",
        ),
    ),
    MetricDefinition(
        "cash_and_equivalents",
        FinancialStatement.BALANCE_SHEET,
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
    ),
    MetricDefinition(
        "debt",
        FinancialStatement.BALANCE_SHEET,
        (
            "LongTermDebtAndFinanceLeaseObligationsCurrent",
            "LongTermDebtCurrent",
            "LongTermDebt",
        ),
    ),
    MetricDefinition(
        "property_plant_equipment",
        FinancialStatement.BALANCE_SHEET,
        ("PropertyPlantAndEquipmentNet",),
    ),
)


def _fact_id(run_id: str, *parts: object) -> str:
    payload = "|".join(str(part or "") for part in (run_id, *parts))
    return f"fact-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def _parse_date(value: object, *, field: str) -> date | None:
    if value in {None, ""}:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"SEC Company Facts contains invalid {field}: {value}") from error


class SecCompanyFactsProvider:
    """Capture and normalize a bounded set of official SEC Company Facts."""

    provider_name = "sec-companyfacts"
    provider_version = "1"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        user_agent: str | None = None,
        max_bytes: int = MAX_COMPANY_FACTS_BYTES,
    ) -> None:
        load_project_env()
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self.user_agent = (
            user_agent or os.getenv("CAPEXGRAPH_SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        ).strip()
        self.max_bytes = max_bytes

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }

    def _get_json(self, url: str) -> tuple[dict[str, Any], bytes]:
        response = self.client.get(url, headers=self.headers)
        raise_for_sec_status(response)
        raw = response.content
        if len(raw) > self.max_bytes:
            raise ValueError(f"SEC Company Facts response exceeds {self.max_bytes} bytes")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("SEC returned an unexpected Company Facts payload")
        return payload, raw

    def _resolve_company(self, identifier: str) -> tuple[str, str, str]:
        if identifier.strip().isdigit() and len(identifier.strip()) <= 10:
            cik = identifier.strip().zfill(10)
            return cik, f"CIK{cik}", f"CIK {cik}"
        payload, _raw = self._get_json(COMPANY_TICKERS_URL)
        candidates = [item for item in payload.values() if isinstance(item, dict)]
        query = identifier.strip().casefold()
        numeric_cik = identifier.strip().zfill(10) if identifier.strip().isdigit() else None
        exact = [
            item
            for item in candidates
            if str(item.get("ticker", "")).casefold() == query
            or str(item.get("title", "")).casefold() == query
            or (
                numeric_cik is not None
                and str(item.get("cik_str", "")).zfill(10) == numeric_cik
            )
        ]
        if len(exact) != 1:
            raise KeyError(
                f"SEC issuer could not be resolved exactly: {identifier}; "
                "provide an exact ticker, company name, or CIK"
            )
        item = exact[0]
        return (
            str(item["cik_str"]).zfill(10),
            canonical_ticker(str(item["ticker"])),
            str(item["title"]),
        )

    @staticmethod
    def _normalized_entries(
        payload: dict[str, Any],
        definition: MetricDefinition,
        *,
        as_of_date: date,
    ) -> tuple[str, list[dict[str, Any]]]:
        us_gaap = payload.get("facts", {}).get("us-gaap", {})
        if not isinstance(us_gaap, dict):
            raise ValueError("SEC Company Facts has no us-gaap fact namespace")

        selected_concept = definition.concepts[0]
        selected: list[dict[str, Any]] = []
        for concept in definition.concepts:
            concept_payload = us_gaap.get(concept)
            if not isinstance(concept_payload, dict):
                continue
            units = concept_payload.get("units", {})
            if not isinstance(units, dict):
                raise ValueError(f"SEC concept {concept} has invalid units")
            raw_entries = units.get(definition.expected_unit)
            if raw_entries is None:
                if units:
                    raise ValueError(
                        f"SEC concept {concept} has no {definition.expected_unit} unit; "
                        f"found {sorted(units)}"
                    )
                continue
            if not isinstance(raw_entries, list):
                raise ValueError(f"SEC concept {concept} has invalid unit observations")
            for index, item in enumerate(raw_entries):
                if not isinstance(item, dict):
                    continue
                form = str(item.get("form") or "")
                filed = _parse_date(item.get("filed"), field="filed date")
                if form not in ALLOWED_FORMS or filed is None or filed > as_of_date:
                    continue
                period_end = _parse_date(item.get("end"), field="period end")
                if period_end is None:
                    raise ValueError(f"SEC concept {concept} observation has no period end")
                value = item.get("val")
                if not isinstance(value, (int, float)):
                    raise ValueError(f"SEC concept {concept} observation has a non-numeric value")
                selected.append(
                    {
                        "concept": concept,
                        "index": index,
                        "period_start": _parse_date(item.get("start"), field="period start"),
                        "period_end": period_end,
                        "fiscal_year": int(item["fy"]) if item.get("fy") is not None else None,
                        "fiscal_period": str(item.get("fp") or "") or None,
                        "form": form,
                        "filed_date": filed,
                        "accession": str(item.get("accn") or "") or None,
                        "value": float(value),
                        "unit": definition.expected_unit,
                    }
                )
            if selected:
                selected_concept = concept
                break
        return selected_concept, selected

    def _facts(
        self,
        run: ResearchRun,
        payload: dict[str, Any],
        *,
        company: str,
        ticker: str,
        evidence_id: str,
    ) -> list[FinancialFact]:
        facts: list[FinancialFact] = []
        for definition in METRICS:
            concept, entries = self._normalized_entries(
                payload,
                definition,
                as_of_date=run.as_of_date,
            )
            if not entries:
                facts.append(
                    FinancialFact(
                        id=_fact_id(run.id, definition.metric, "missing", run.as_of_date),
                        company=company,
                        ticker=ticker,
                        statement=definition.statement,
                        metric=definition.metric,
                        concept=concept,
                        unit=definition.expected_unit,
                        fact_type=FinancialFactType.MISSING,
                        source_evidence_id=evidence_id,
                        source_locator=f"facts.us-gaap.{concept}.units.{definition.expected_unit}",
                        provider=self.provider_name,
                        provider_version=self.provider_version,
                    )
                )
                continue

            by_period: dict[tuple[object, ...], list[dict[str, Any]]] = defaultdict(list)
            for entry in entries:
                key = (
                    definition.metric,
                    entry["period_start"],
                    entry["period_end"],
                    entry["unit"],
                )
                by_period[key].append(entry)

            for group in by_period.values():
                accession_values: dict[
                    tuple[str | None, date | None], set[float]
                ] = defaultdict(set)
                for entry in group:
                    accession_values[(entry["accession"], entry["filed_date"])].add(entry["value"])
                conflicts = [key for key, values in accession_values.items() if len(values) > 1]
                if conflicts:
                    raise ValueError(
                        f"SEC fact conflict for {definition.metric}: one filing reports "
                        "multiple values for the same period and unit"
                    )

                latest_by_value: dict[float, dict[str, Any]] = {}
                for entry in sorted(
                    group,
                    key=lambda item: (
                        item["filed_date"] or date.min,
                        item["accession"] or "",
                    ),
                ):
                    latest_by_value[entry["value"]] = entry
                distinct = sorted(
                    latest_by_value.values(),
                    key=lambda item: (
                        item["filed_date"] or date.min,
                        item["accession"] or "",
                    ),
                )
                for position, entry in enumerate(distinct):
                    fact_type = (
                        FinancialFactType.RESTATED
                        if position > 0
                        else FinancialFactType.REPORTED
                    )
                    facts.append(
                        FinancialFact(
                            id=_fact_id(
                                run.id,
                                definition.metric,
                                entry["period_start"],
                                entry["period_end"],
                                entry["accession"],
                                entry["value"],
                            ),
                            company=company,
                            ticker=ticker,
                            statement=definition.statement,
                            metric=definition.metric,
                            concept=entry["concept"],
                            period_start=entry["period_start"],
                            period_end=entry["period_end"],
                            fiscal_year=entry["fiscal_year"],
                            fiscal_period=entry["fiscal_period"],
                            form=entry["form"],
                            filed_date=entry["filed_date"],
                            accession=entry["accession"],
                            value=entry["value"],
                            unit=entry["unit"],
                            fact_type=fact_type,
                            source_evidence_id=evidence_id,
                            source_locator=(
                                f"facts.us-gaap.{entry['concept']}.units.{entry['unit']}"
                                f"[{entry['index']}]"
                            ),
                            provider=self.provider_name,
                            provider_version=self.provider_version,
                        )
                    )

        facts.extend(self._derive_free_cash_flow(run, facts, company, ticker, evidence_id))
        return facts

    def _derive_free_cash_flow(
        self,
        run: ResearchRun,
        facts: list[FinancialFact],
        company: str,
        ticker: str,
        evidence_id: str,
    ) -> list[FinancialFact]:
        cash_flow = [
            fact
            for fact in facts
            if fact.metric == "operating_cash_flow" and fact.value is not None
        ]
        capex = [
            fact
            for fact in facts
            if fact.metric == "capital_expenditures" and fact.value is not None
        ]
        derived: list[FinancialFact] = []
        for operating in cash_flow:
            matches = [
                item
                for item in capex
                if item.period_start == operating.period_start
                and item.period_end == operating.period_end
                and item.unit == operating.unit
            ]
            if not matches:
                continue
            investment = max(matches, key=lambda item: item.filed_date or date.min)
            derived.append(
                FinancialFact(
                    id=_fact_id(
                        run.id,
                        "free_cash_flow",
                        operating.id,
                        investment.id,
                    ),
                    company=company,
                    ticker=ticker,
                    statement=FinancialStatement.CASH_FLOW,
                    metric="free_cash_flow",
                    concept="derived:operating_cash_flow-capital_expenditures",
                    period_start=operating.period_start,
                    period_end=operating.period_end,
                    fiscal_year=operating.fiscal_year,
                    fiscal_period=operating.fiscal_period,
                    form=operating.form,
                    filed_date=max(
                        item
                        for item in (operating.filed_date, investment.filed_date)
                        if item is not None
                    ),
                    accession=operating.accession,
                    value=operating.value - investment.value,
                    unit=operating.unit,
                    fact_type=FinancialFactType.DERIVED,
                    source_evidence_id=evidence_id,
                    source_locator="derived from input_fact_ids",
                    formula="operating_cash_flow - capital_expenditures",
                    input_fact_ids=[operating.id, investment.id],
                    provider=self.provider_name,
                    provider_version=self.provider_version,
                )
            )
        if derived:
            return derived
        return [
            FinancialFact(
                id=_fact_id(run.id, "free_cash_flow", "missing", run.as_of_date),
                company=company,
                ticker=ticker,
                statement=FinancialStatement.CASH_FLOW,
                metric="free_cash_flow",
                concept="derived:operating_cash_flow-capital_expenditures",
                unit="USD",
                fact_type=FinancialFactType.MISSING,
                source_evidence_id=evidence_id,
                source_locator="derived from operating_cash_flow and capital_expenditures",
                provider=self.provider_name,
                provider_version=self.provider_version,
            )
        ]

    def extract(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
    ) -> FilingFactsResult:
        cik, ticker, registry_name = self._resolve_company(identifier or run.subject)
        url = COMPANY_FACTS_URL.format(cik=cik)
        payload, raw = self._get_json(url)
        company = str(payload.get("entityName") or registry_name).strip()
        if ticker.startswith("CIK"):
            try:
                ticker = TickerResolver().resolve(company).ticker
            except KeyError:
                pass
        digest = hashlib.sha256(raw).hexdigest()
        evidence_id = f"sec-companyfacts-{cik}-{digest[:12]}"
        relative_raw = f"sources/{evidence_id}.json"
        relative_text = f"sources/{evidence_id}.txt"
        atomic_write_bytes(runs_dir() / run.id / relative_raw, raw)
        atomic_write_text(
            runs_dir() / run.id / relative_text,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        evidence = Evidence(
            id=evidence_id,
            title=f"{company} SEC Company Facts",
            kind=EvidenceKind.FILING,
            source_url=url,
            excerpt=(
                f"Official SEC Company Facts response for {company} / CIK {cik}; "
                "individual values retain JSON source locators."
            ),
            source_hash=digest,
            publisher="U.S. Securities and Exchange Commission",
            content_type="application/json",
            local_path=relative_raw,
            status=EvidenceStatus.CAPTURED,
        )
        try:
            facts = self._facts(
                run,
                payload,
                company=company,
                ticker=ticker,
                evidence_id=evidence_id,
            )
        except ValueError as error:
            raise FilingFactsValidationError(str(error), evidence=evidence) from error
        return FilingFactsResult(
            evidence=evidence,
            facts=facts,
        )
