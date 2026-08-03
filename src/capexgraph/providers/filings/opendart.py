from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
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
from capexgraph.providers.filings.base import FilingFactsResult, FilingFactsValidationError
from capexgraph.providers.sources.korea import OPEN_DART_CORP_CODES
from capexgraph.runtime.artifacts import atomic_write_bytes, atomic_write_text
from capexgraph.runtime.store import runs_dir

OPEN_DART_ACCOUNTS_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

ACCOUNT_MAPPINGS: tuple[
    tuple[str, FinancialStatement, tuple[str, ...]], ...
] = (
    ("revenue", FinancialStatement.INCOME, ("매출액", "영업수익", "수익(매출액)")),
    ("operating_income", FinancialStatement.INCOME, ("영업이익", "영업이익(손실)")),
    ("net_income", FinancialStatement.INCOME, ("당기순이익", "당기순이익(손실)")),
    (
        "operating_cash_flow",
        FinancialStatement.CASH_FLOW,
        ("영업활동으로 인한 현금흐름", "영업활동현금흐름"),
    ),
    (
        "capital_expenditures",
        FinancialStatement.CASH_FLOW,
        ("유형자산의 취득", "유형자산 취득"),
    ),
    (
        "cash_and_equivalents",
        FinancialStatement.BALANCE_SHEET,
        ("현금및현금성자산", "현금 및 현금성자산"),
    ),
    ("debt", FinancialStatement.BALANCE_SHEET, ("부채총계",)),
    (
        "property_plant_equipment",
        FinancialStatement.BALANCE_SHEET,
        ("유형자산",),
    ),
)


def _fact_id(run_id: str, *parts: object) -> str:
    raw = "|".join(str(part or "") for part in (run_id, *parts)).encode()
    return f"fact-{hashlib.sha256(raw).hexdigest()[:24]}"


def _report_period(as_of: date) -> tuple[int, str, str]:
    if as_of.month >= 11:
        return as_of.year, "11014", "Q3"
    if as_of.month >= 8:
        return as_of.year, "11012", "H1"
    if as_of.month >= 5:
        return as_of.year, "11013", "Q1"
    return as_of.year - 1, "11011", "FY"


def _amount(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        parsed = float(text)
    except ValueError:
        return None
    return -parsed if negative else parsed


def _period_end(value: object) -> date | None:
    matches = re.findall(r"(20\d{2})[.\-/](\d{2})[.\-/](\d{2})", str(value or ""))
    if not matches:
        return None
    year, month, day = matches[-1]
    return date(int(year), int(month), int(day))


class OpenDartFinancialFactsProvider:
    """Normalize a conservative account subset from the official OpenDART API."""

    provider_name = "opendart-financial-statements"
    provider_version = "1"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: httpx.Client | None = None,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        load_project_env()
        self._api_key = (api_key or os.getenv("OPENDART_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError("OPENDART_API_KEY is required for OpenDART financial facts.")
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self.max_bytes = max_bytes

    @staticmethod
    def _corp_code(identifier: str) -> str:
        normalized = identifier.strip().upper()
        if normalized.isdigit() and len(normalized) == 8:
            return normalized
        try:
            return OPEN_DART_CORP_CODES[normalized]
        except KeyError as error:
            raise KeyError(
                "OpenDART issuer is not in the local mapping; provide an 8-digit corp_code."
            ) from error

    def extract(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
    ) -> FilingFactsResult:
        query = (identifier or run.subject).strip()
        corp_code = self._corp_code(query)
        business_year, report_code, fiscal_period = _report_period(run.as_of_date)
        response = self.client.get(
            OPEN_DART_ACCOUNTS_URL,
            params={
                "crtfc_key": self._api_key,
                "corp_code": corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
                "fs_div": "CFS",
            },
            headers={"User-Agent": "CapexGraph/0.5", "Accept": "application/json"},
        )
        response.raise_for_status()
        raw = response.content
        if len(raw) > self.max_bytes:
            raise ValueError(f"OpenDART response exceeds {self.max_bytes} bytes")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OpenDART returned an unexpected financial payload.")
        status = str(payload.get("status") or "")
        if status not in {"000", "013"}:
            raise RuntimeError(
                "OpenDART returned a financial provider error; check key, issuer, and quota."
            )

        digest = hashlib.sha256(raw).hexdigest()
        evidence_id = f"opendart-facts-{corp_code}-{digest[:12]}"
        relative_raw = f"sources/{evidence_id}.json"
        relative_text = f"sources/{evidence_id}.txt"
        atomic_write_bytes(runs_dir() / run.id / relative_raw, raw)
        atomic_write_text(
            runs_dir() / run.id / relative_text,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        rows = [item for item in payload.get("list", []) if isinstance(item, dict)]
        company = str(
            next((item.get("corp_name") for item in rows if item.get("corp_name")), query)
        )
        ticker = str(
            next((item.get("stock_code") for item in rows if item.get("stock_code")), query)
        ).upper()
        if ticker.isdigit() and len(ticker) == 6:
            ticker = f"{ticker}.KO"
        evidence = Evidence(
            id=evidence_id,
            title=f"{company} OpenDART financial statements {business_year} {fiscal_period}",
            kind=EvidenceKind.FILING,
            source_url=OPEN_DART_ACCOUNTS_URL,
            excerpt=(
                "Official OpenDART consolidated financial statement response; "
                "each normalized fact retains its account and receipt locator."
            ),
            source_hash=digest,
            publisher="Financial Supervisory Service OpenDART",
            content_type="application/json",
            local_path=relative_raw,
            status=EvidenceStatus.CAPTURED,
        )
        try:
            facts = self._facts(
                run,
                rows,
                company=company,
                ticker=ticker,
                evidence_id=evidence_id,
                fiscal_year=business_year,
                fiscal_period=fiscal_period,
            )
        except ValueError as error:
            raise FilingFactsValidationError(str(error), evidence=evidence) from error
        return FilingFactsResult(evidence=evidence, facts=facts)

    def _facts(
        self,
        run: ResearchRun,
        rows: list[dict[str, Any]],
        *,
        company: str,
        ticker: str,
        evidence_id: str,
        fiscal_year: int,
        fiscal_period: str,
    ) -> list[FinancialFact]:
        facts: list[FinancialFact] = []
        normalized_rows = {
            re.sub(r"\s+", "", str(item.get("account_nm") or "")): item
            for item in rows
        }
        for metric, statement, names in ACCOUNT_MAPPINGS:
            item = next(
                (
                    normalized_rows[re.sub(r"\s+", "", name)]
                    for name in names
                    if re.sub(r"\s+", "", name) in normalized_rows
                ),
                None,
            )
            value = _amount(item.get("thstrm_amount")) if item else None
            concept = str(item.get("account_id") or item.get("account_nm")) if item else names[0]
            period_end = _period_end(item.get("thstrm_dt")) if item else None
            receipt = str(item.get("rcept_no") or "") if item else ""
            filed_date = (
                datetime.strptime(receipt[:8], "%Y%m%d").date()
                if len(receipt) >= 8 and receipt[:8].isdigit()
                else None
            )
            if filed_date and filed_date > run.as_of_date:
                raise ValueError("OpenDART response contains a filing after the run as-of date")
            facts.append(
                FinancialFact(
                    id=_fact_id(run.id, metric, period_end, receipt, value),
                    company=company,
                    ticker=ticker,
                    statement=statement,
                    metric=metric,
                    concept=concept,
                    period_end=period_end,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    form="OpenDART CFS",
                    filed_date=filed_date,
                    accession=receipt or None,
                    value=value,
                    unit="KRW",
                    fact_type=(
                        FinancialFactType.REPORTED
                        if value is not None
                        else FinancialFactType.MISSING
                    ),
                    source_evidence_id=evidence_id,
                    source_locator=(
                        f"list[account_nm={item.get('account_nm')!s}].thstrm_amount"
                        if item
                        else f"missing:{names[0]}"
                    ),
                    provider=self.provider_name,
                    provider_version=self.provider_version,
                )
            )
        return facts
