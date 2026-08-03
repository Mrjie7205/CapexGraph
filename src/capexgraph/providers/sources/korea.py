from __future__ import annotations

import html
import os
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from capexgraph.config import load_project_env
from capexgraph.domain import (
    CoverageLevel,
    EvidenceKind,
    OfficialSourceCapability,
    ResearchRun,
    SourceAuthority,
    SourceSuggestion,
    SourceSuggestionStatus,
)
from capexgraph.providers.sources.base import (
    canonicalize_source_url,
    source_suggestion_id,
)

OPEN_DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
KIND_SEARCH_URL = "https://kind.krx.co.kr/disclosure/details.do"
OPEN_DART_CORP_CODES = {
    "005930": "00126380",
    "005930.KO": "00126380",
    "SAMSUNG ELECTRONICS": "00126380",
    "000660": "00164779",
    "000660.KO": "00164779",
    "SK HYNIX": "00164779",
}


def _strip_html(value: object) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


class OpenDartSourceProvider:
    provider_name = "opendart-disclosures"
    provider_version = "1"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        load_project_env()
        self._api_key = (api_key or os.getenv("OPENDART_API_KEY", "")).strip()
        if not self._api_key:
            raise RuntimeError(
                "OPENDART_API_KEY is required for the official OpenDART provider."
            )
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["KR"],
            official_domains=["opendart.fss.or.kr", "dart.fss.or.kr"],
            authentication="OPENDART_API_KEY",
            discovery=CoverageLevel.COMPLETE,
            original_documents=CoverageLevel.COMPLETE,
            history=CoverageLevel.PARTIAL,
            license="Official OpenDART API; keep the user's key and downloaded files local.",
            notes=[
                "The official list API documents disclosure history from 2015 onward.",
                "KIND remains a separate supplemental exchange channel.",
            ],
        )

    @staticmethod
    def _corp_code(identifier: str) -> str:
        normalized = identifier.strip().upper()
        if normalized.isdigit() and len(normalized) == 8:
            return normalized
        code = OPEN_DART_CORP_CODES.get(normalized)
        if code is None:
            raise KeyError(
                "OpenDART issuer is not in the local mapping; provide an 8-digit corp_code."
            )
        return code

    def discover(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        query = (identifier or run.subject).strip()
        corp_code = self._corp_code(query)
        end = date.today()
        start = end - timedelta(days=365)
        response = self.client.get(
            OPEN_DART_LIST_URL,
            params={
                "crtfc_key": self._api_key,
                "corp_code": corp_code,
                "bgn_de": start.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "page_count": str(max(1, min(limit, 100))),
                "sort": "date",
                "sort_mth": "desc",
            },
            headers={"User-Agent": "CapexGraph/0.5"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("OpenDART returned an unexpected payload.")
        status = str(payload.get("status") or "")
        if status == "013":
            return []
        if status != "000":
            raise RuntimeError(
                "OpenDART returned a provider error; check key, issuer, and call limit."
            )
        filters = [item.casefold() for item in forms if item.strip()]
        suggestions: list[SourceSuggestion] = []
        for item in payload.get("list", []):
            if not isinstance(item, dict):
                continue
            title = _strip_html(item.get("report_nm"))
            if filters and not any(value in title.casefold() for value in filters):
                continue
            receipt = str(item.get("rcept_no") or "")
            receipt_date = str(item.get("rcept_dt") or "")
            if not receipt or len(receipt_date) != 8:
                continue
            published = datetime.strptime(receipt_date, "%Y%m%d").date()
            url = canonicalize_source_url(
                f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
            )
            ticker = str(item.get("stock_code") or query).strip()
            if ticker.isdigit() and len(ticker) == 6:
                ticker = f"{ticker}.KO"
            suggestions.append(
                SourceSuggestion(
                    id=source_suggestion_id(run.id, url, prefix="opendart"),
                    run_id=run.id,
                    title=title,
                    url=url,
                    canonical_url=url,
                    kind=EvidenceKind.FILING,
                    publisher="Financial Supervisory Service OpenDART",
                    authority=SourceAuthority.REGULATOR,
                    reason=f"Official OpenDART disclosure discovered for corp_code {corp_code}.",
                    provider=self.provider_name,
                    provider_version=self.provider_version,
                    status=SourceSuggestionStatus.SUGGESTED,
                    published_at=published,
                    metadata={
                        "jurisdiction": "KR",
                        "corp_code": corp_code,
                        "ticker": ticker.upper(),
                        "company_name": _strip_html(item.get("corp_name")) or ticker,
                        "announcement_id": receipt,
                        "announcement_type": title,
                        "published_datetime": datetime.combine(
                            published,
                            datetime.min.time(),
                            UTC,
                        ).isoformat(),
                        "original_document_url": url,
                        "filer_name": _strip_html(item.get("flr_nm")),
                        "revision_marker": _strip_html(item.get("rm")),
                        "source_provider": self.provider_name,
                    },
                )
            )
            if len(suggestions) >= max(1, min(limit, 100)):
                break
        return suggestions


class KindSourceProvider:
    provider_name = "kind-krx-disclosures"
    provider_version = "1"

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["KR"],
            official_domains=["kind.krx.co.kr"],
            authentication="none; public exchange website",
            discovery=CoverageLevel.PARTIAL,
            original_documents=CoverageLevel.PARTIAL,
            history=CoverageLevel.FORWARD_ONLY,
            license="Public KRX disclosure pages; respect KIND terms and rate limits.",
            notes=[
                "KIND supplements OpenDART; it does not overwrite OpenDART observations.",
                "HTML changes surface as an explicit parser error.",
            ],
        )

    def _records(self, identifier: str, limit: int) -> list[dict[str, Any]]:
        response = self.client.post(
            KIND_SEARCH_URL,
            data={
                "method": "searchDetailsSub",
                "currentPageSize": str(max(1, min(limit, 100))),
                "pageIndex": "1",
                "textCrpNm": identifier,
            },
            headers={
                "User-Agent": "Mozilla/5.0 CapexGraph/0.5",
                "Referer": "https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain",
            },
        )
        response.raise_for_status()
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            items = payload.get("list") or payload.get("data") or []
            return [item for item in items if isinstance(item, dict)]

        body = response.text
        records: list[dict[str, Any]] = []
        pattern = re.compile(
            r"<a[^>]+href=[\"'][^\"']*acptno=(\d+)[^\"']*[\"'][^>]*>(.*?)</a>",
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(body):
            nearby = body[max(0, match.start() - 500) : match.end() + 500]
            date_match = re.search(r"20\d{2}[-./]\d{2}[-./]\d{2}", nearby)
            records.append(
                {
                    "announcement_id": match.group(1),
                    "title": _strip_html(match.group(2)),
                    "published_at": date_match.group(0) if date_match else date.today().isoformat(),
                    "company_name": identifier,
                    "ticker": identifier,
                }
            )
        return records

    def discover(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        query = (identifier or run.subject).strip()
        filters = [item.casefold() for item in forms if item.strip()]
        suggestions: list[SourceSuggestion] = []
        for item in self._records(query, limit):
            receipt = str(
                item.get("announcement_id")
                or item.get("acptno")
                or item.get("rcept_no")
                or ""
            )
            title = _strip_html(item.get("title") or item.get("report_nm"))
            if not receipt or not title:
                continue
            if filters and not any(value in title.casefold() for value in filters):
                continue
            published_raw = str(item.get("published_at") or item.get("rcept_dt") or "")
            normalized_date = published_raw.replace(".", "-").replace("/", "-")[:10]
            published = date.fromisoformat(normalized_date)
            url = canonicalize_source_url(
                "https://kind.krx.co.kr/common/disclsviewer.do"
                f"?method=search&acptno={receipt}"
            )
            ticker = str(item.get("ticker") or query).strip().upper()
            if ticker.isdigit() and len(ticker) == 6:
                ticker = f"{ticker}.KO"
            suggestions.append(
                SourceSuggestion(
                    id=source_suggestion_id(run.id, url, prefix="kind"),
                    run_id=run.id,
                    title=title,
                    url=url,
                    canonical_url=url,
                    kind=EvidenceKind.COMPANY_DISCLOSURE,
                    publisher="Korea Exchange KIND",
                    authority=SourceAuthority.REGULATOR,
                    reason=f"Official KIND/KRX disclosure discovered for {ticker}.",
                    provider=self.provider_name,
                    provider_version=self.provider_version,
                    status=SourceSuggestionStatus.SUGGESTED,
                    published_at=published,
                    metadata={
                        "jurisdiction": "KR",
                        "ticker": ticker,
                        "company_name": _strip_html(item.get("company_name")) or ticker,
                        "announcement_id": receipt,
                        "announcement_type": title,
                        "published_datetime": datetime.combine(
                            published,
                            datetime.min.time(),
                            UTC,
                        ).isoformat(),
                        "original_document_url": url,
                        "source_provider": self.provider_name,
                    },
                )
            )
            if len(suggestions) >= max(1, min(limit, 100)):
                break
        return suggestions


def korea_source_capabilities() -> list[OfficialSourceCapability]:
    return [OpenDartSourceProvider.capability(), KindSourceProvider.capability()]
