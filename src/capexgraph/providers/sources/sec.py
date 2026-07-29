from __future__ import annotations

import os
from collections.abc import Sequence

import httpx

from capexgraph.config import load_project_env
from capexgraph.domain import (
    EvidenceKind,
    ResearchRun,
    SourceAuthority,
    SourceSuggestion,
    SourceSuggestionStatus,
)
from capexgraph.providers.sources.base import (
    canonicalize_source_url,
    source_suggestion_id,
)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
DEFAULT_FORMS = ("10-K", "10-Q", "8-K", "20-F", "6-K")
DEFAULT_SEC_USER_AGENT = (
    "CapexGraph research github.com/Mrjie7205/CapexGraph "
    "(configure CAPEXGRAPH_SEC_USER_AGENT with contact information)"
)


class SecEdgarSourceProvider:
    """Discover recent official SEC filing documents through EDGAR submissions."""

    provider_name = "sec-edgar-submissions"
    provider_version = "2"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        load_project_env()
        self.client = client or httpx.Client(timeout=30)
        self.user_agent = (
            user_agent or os.getenv("CAPEXGRAPH_SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        ).strip()

    def _get_json(self, url: str) -> dict:
        response = self.client.get(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
        )
        raise_for_sec_status(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("SEC returned an unexpected JSON payload")
        return payload

    def _resolve_company(self, identifier: str) -> tuple[str, str, str]:
        normalized = identifier.strip()
        if normalized.isdigit() and len(normalized) <= 10:
            cik = normalized.zfill(10)
            return cik, normalized, normalized

        payload = self._get_json(COMPANY_TICKERS_URL)
        candidates = [item for item in payload.values() if isinstance(item, dict)]
        query = normalized.casefold()
        exact = [
            item
            for item in candidates
            if str(item.get("ticker", "")).casefold() == query
            or str(item.get("title", "")).casefold() == query
        ]
        if len(exact) != 1:
            raise KeyError(
                f"SEC issuer could not be resolved exactly: {identifier}; "
                "provide a ticker or CIK"
            )
        item = exact[0]
        cik = str(item["cik_str"]).zfill(10)
        return cik, str(item.get("ticker", normalized)).upper(), str(item.get("title", normalized))

    def discover(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        query = (identifier or run.subject).strip()
        cik, ticker, registry_name = self._resolve_company(query)
        payload = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        company_name = str(payload.get("name") or registry_name)
        recent = payload.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            raise ValueError("SEC submissions payload has no recent filings")

        allowed_forms = {item.upper() for item in (forms or DEFAULT_FORMS)}
        accessions = recent.get("accessionNumber", [])
        form_values = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])
        acceptance_datetimes = recent.get("acceptanceDateTime", [])
        items = recent.get("items", [])
        is_xbrl = recent.get("isXBRL", [])
        is_inline_xbrl = recent.get("isInlineXBRL", [])
        primary_descriptions = recent.get("primaryDocDescription", [])
        count = min(
            len(accessions),
            len(form_values),
            len(filing_dates),
            len(report_dates),
            len(primary_documents),
        )
        suggestions: list[SourceSuggestion] = []
        for index in range(count):
            form = str(form_values[index]).upper()
            if form not in allowed_forms:
                continue
            accession = str(accessions[index])
            accession_path = accession.replace("-", "")
            primary_document = str(primary_documents[index]).lstrip("/")
            if not accession_path or not primary_document:
                continue
            url = canonicalize_source_url(
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{primary_document}"
            )
            filing_date = str(filing_dates[index])
            suggestion = SourceSuggestion(
                id=source_suggestion_id(run.id, url, prefix="sec"),
                run_id=run.id,
                title=f"{company_name} {form} filed {filing_date}",
                url=url,
                canonical_url=url,
                kind=EvidenceKind.FILING,
                publisher="U.S. Securities and Exchange Commission",
                authority=SourceAuthority.REGULATOR,
                reason=f"Official EDGAR {form} filing discovered for {ticker} / CIK {cik}.",
                provider=self.provider_name,
                provider_version=self.provider_version,
                status=SourceSuggestionStatus.SUGGESTED,
                published_at=filing_date,
                metadata={
                    "cik": cik,
                    "ticker": ticker,
                    "company_name": company_name,
                    "form": form,
                    "filing_date": filing_date,
                    "report_date": str(report_dates[index]),
                    "acceptance_datetime": _sequence_value(acceptance_datetimes, index),
                    "accession": accession,
                    "primary_document": primary_document,
                    "primary_document_description": _sequence_value(
                        primary_descriptions,
                        index,
                    ),
                    "items": _sequence_value(items, index),
                    "is_xbrl": _sequence_value(is_xbrl, index),
                    "is_inline_xbrl": _sequence_value(is_inline_xbrl, index),
                },
            )
            suggestions.append(suggestion)
            if len(suggestions) >= max(1, min(limit, 100)):
                break
        return suggestions


def _sequence_value(values, index: int):
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def raise_for_sec_status(response: httpx.Response) -> None:
    if response.status_code == 403:
        raise RuntimeError(
            "SEC returned HTTP 403. Set CAPEXGRAPH_SEC_USER_AGENT in .env to identify "
            "the application and include a real contact address."
        )
    response.raise_for_status()
