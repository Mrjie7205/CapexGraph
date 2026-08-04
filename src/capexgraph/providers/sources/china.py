from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

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

SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _text(value: object) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _published(value: object) -> tuple[date, datetime]:
    if isinstance(value, (int, float)):
        moment = datetime.fromtimestamp(float(value) / 1000, SHANGHAI)
        return moment.date(), moment.astimezone(UTC)
    normalized = str(value or "").strip().replace("/", "-")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(normalized[:19], pattern).replace(tzinfo=SHANGHAI)
            return parsed.date(), parsed.astimezone(UTC)
        except ValueError:
            continue
    raise ValueError(f"Unsupported official announcement date: {value}")


def _ticker_market(identifier: str) -> tuple[str, str]:
    normalized = identifier.strip().upper()
    if normalized.endswith(".SH") or normalized.startswith(("6", "5")):
        return normalized.removesuffix(".SH"), "SSE"
    if normalized.endswith(".BJ") or normalized.startswith(("4", "8", "9")):
        return normalized.removesuffix(".BJ"), "BSE"
    return normalized.removesuffix(".SZ"), "SZSE"


class _ChinaAnnouncementProvider:
    provider_name = "china-official"
    provider_version = "1"
    publisher = "中国官方信息披露平台"
    official_market = "CN"

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        raise NotImplementedError

    def _records(
        self,
        identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def discover(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        query = (identifier or run.subject).strip()
        requested = max(1, min(limit, 100))
        records = self._records(query, limit=requested)
        filters = [item.casefold() for item in forms if item.strip()]
        suggestions: list[SourceSuggestion] = []
        for record in records:
            title = _text(record.get("title"))
            if not title or filters and not any(item in title.casefold() for item in filters):
                continue
            url = canonicalize_source_url(str(record["url"]))
            published_date, known_at = _published(record.get("published_at"))
            ticker = str(record.get("ticker") or query).upper()
            external_id = str(record.get("external_id") or "").strip()
            if not external_id:
                external_id = source_suggestion_id(run.id, url, prefix="announcement")
            suggestions.append(
                SourceSuggestion(
                    id=source_suggestion_id(run.id, url, prefix=self.provider_name),
                    run_id=run.id,
                    title=title,
                    url=url,
                    canonical_url=url,
                    kind=EvidenceKind.COMPANY_DISCLOSURE,
                    publisher=self.publisher,
                    authority=SourceAuthority.REGULATOR,
                    reason=(
                        f"Official {self.provider_name} disclosure discovered for {ticker}."
                    ),
                    provider=self.provider_name,
                    provider_version=self.provider_version,
                    status=SourceSuggestionStatus.SUGGESTED,
                    published_at=published_date,
                    metadata={
                        "jurisdiction": "CN",
                        "ticker": ticker,
                        "company_name": _text(record.get("company_name")) or ticker,
                        "announcement_id": external_id,
                        "announcement_type": _text(record.get("announcement_type")),
                        "report_period": _text(record.get("report_period")),
                        "published_datetime": known_at.isoformat(),
                        "original_document_url": url,
                        "source_provider": self.provider_name,
                        **dict(record.get("metadata") or {}),
                    },
                )
            )
            if len(suggestions) >= requested:
                break
        return suggestions


class CninfoSourceProvider(_ChinaAnnouncementProvider):
    provider_name = "cninfo-announcements"
    provider_version = "1"
    publisher = "巨潮资讯网"
    endpoint = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    identity_endpoint = "https://www.cninfo.com.cn/new/information/topSearch/query"

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN"],
            official_domains=["cninfo.com.cn", "static.cninfo.com.cn"],
            authentication="none; public website query with anti-abuse controls",
            discovery=CoverageLevel.PARTIAL,
            original_documents=CoverageLevel.COMPLETE,
            history=CoverageLevel.PARTIAL,
            license="Public official disclosures; respect website terms and rate limits.",
            notes=[
                "Discovery is best-effort and never replaces captured, hash-verified evidence.",
                "Raw responses remain local and are not committed or redistributed.",
            ],
        )

    def _records(self, identifier: str, *, limit: int) -> list[dict[str, Any]]:
        code, exchange = _ticker_market(identifier)
        column = {"SSE": "sse", "SZSE": "szse", "BSE": "bj"}[exchange]
        end = datetime.now(SHANGHAI).date()
        start = end - timedelta(days=365)
        headers = {
            "User-Agent": "Mozilla/5.0 CapexGraph/0.5",
            "Referer": "https://www.cninfo.com.cn/",
        }
        try:
            identity_response = self.client.post(
                self.identity_endpoint,
                params={"keyWord": code, "maxNum": "10"},
                headers=headers,
            )
            identity_response.raise_for_status()
            identities = identity_response.json()
            official_identity = next(
                (
                    item
                    for item in identities
                    if isinstance(item, dict)
                    and str(item.get("code") or "").strip() == code
                    and str(item.get("orgId") or "").strip()
                ),
                None,
            )
            if official_identity is None:
                raise RuntimeError(f"CNINFO did not resolve an official orgId for {code}.")
            org_id = str(official_identity["orgId"]).strip()
            response = self.client.post(
                self.endpoint,
                data={
                    "pageNum": "1",
                    "pageSize": str(limit),
                    "column": column,
                    "tabName": "fulltext",
                    "plate": "",
                    "stock": f"{code},{org_id}",
                    "searchkey": "",
                    "secid": "",
                    "category": "",
                    "trade": "",
                    "seDate": f"{start.isoformat()}~{end.isoformat()}",
                    "sortName": "",
                    "sortType": "",
                    "isHLtitle": "true",
                },
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise RuntimeError(f"CNINFO request failed ({type(error).__name__}).") from None
        response.raise_for_status()
        payload = response.json()
        announcements = payload.get("announcements", []) if isinstance(payload, dict) else []
        records: list[dict[str, Any]] = []
        for item in announcements if isinstance(announcements, list) else []:
            if not isinstance(item, dict) or not item.get("adjunctUrl"):
                continue
            ticker = str(item.get("secCode") or code)
            suffix = ".SH" if exchange == "SSE" else ".BJ" if exchange == "BSE" else ".SZ"
            records.append(
                {
                    "external_id": item.get("announcementId"),
                    "ticker": f"{ticker}{suffix}",
                    "company_name": item.get("secName"),
                    "title": item.get("announcementTitle"),
                    "published_at": item.get("announcementTime"),
                    "url": urljoin(
                        "https://static.cninfo.com.cn/",
                        str(item["adjunctUrl"]).lstrip("/"),
                    ),
                    "announcement_type": item.get("announcementTypeName"),
                    "metadata": {"exchange": exchange},
                }
            )
        return records


class SseSourceProvider(_ChinaAnnouncementProvider):
    provider_name = "sse-announcements"
    provider_version = "1"
    publisher = "上海证券交易所"
    endpoint = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN"],
            official_domains=["sse.com.cn"],
            authentication="none; public website query",
            discovery=CoverageLevel.PARTIAL,
            original_documents=CoverageLevel.COMPLETE,
            history=CoverageLevel.PARTIAL,
            license="Public exchange disclosures; respect SSE terms and rate limits.",
            notes=["Shanghai-listed securities only."],
        )

    def _records(self, identifier: str, *, limit: int) -> list[dict[str, Any]]:
        code, exchange = _ticker_market(identifier)
        if exchange != "SSE":
            raise ValueError("SSE provider requires a Shanghai-listed ticker")
        response = self.client.get(
            self.endpoint,
            params={
                "isPagination": "true",
                "productId": code,
                "pageHelp.pageSize": str(limit),
                "pageHelp.pageNo": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.endPage": "1",
            },
            headers={
                "User-Agent": "Mozilla/5.0 CapexGraph/0.5",
                "Referer": f"https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?productId={code}",
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("result") or payload.get("pageHelp", {}).get("data") or []
        records: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url = item.get("URL") or item.get("url") or item.get("BULLETIN_URL")
            if not url:
                continue
            records.append(
                {
                    "external_id": item.get("BULLETIN_ID") or item.get("bulletinId"),
                    "ticker": f"{code}.SH",
                    "company_name": item.get("SECURITY_NAME") or item.get("securityName"),
                    "title": item.get("TITLE") or item.get("title"),
                    "published_at": item.get("SSEDATE") or item.get("publishDate"),
                    "url": urljoin("https://www.sse.com.cn/", str(url)),
                    "announcement_type": item.get("BULLETIN_TYPE"),
                    "metadata": {"exchange": "SSE"},
                }
            )
        return records


class SzseSourceProvider(_ChinaAnnouncementProvider):
    provider_name = "szse-announcements"
    provider_version = "1"
    publisher = "深圳证券交易所"
    endpoint = "https://www.szse.cn/api/disc/announcement/annList"

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN"],
            official_domains=["szse.cn"],
            authentication="none; public website query",
            discovery=CoverageLevel.PARTIAL,
            original_documents=CoverageLevel.COMPLETE,
            history=CoverageLevel.PARTIAL,
            license="Public exchange disclosures; respect SZSE terms and rate limits.",
            notes=["Shenzhen-listed securities only."],
        )

    def _records(self, identifier: str, *, limit: int) -> list[dict[str, Any]]:
        code, exchange = _ticker_market(identifier)
        if exchange != "SZSE":
            raise ValueError("SZSE provider requires a Shenzhen-listed ticker")
        response = self.client.post(
            self.endpoint,
            json={
                "seDate": [
                    (datetime.now(SHANGHAI).date() - timedelta(days=365)).isoformat(),
                    datetime.now(SHANGHAI).date().isoformat(),
                ],
                "stock": [code],
                "channelCode": ["listedNotice_disc"],
                "pageSize": limit,
                "pageNum": 1,
            },
            headers={
                "User-Agent": "Mozilla/5.0 CapexGraph/0.5",
                "Referer": "https://www.szse.cn/disclosure/listed/notice/",
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data") or payload.get("announcements") or []
        records: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url = item.get("attachPath") or item.get("url") or item.get("attachUrl")
            if not url:
                continue
            records.append(
                {
                    "external_id": item.get("id") or item.get("announcementId"),
                    "ticker": f"{code}.SZ",
                    "company_name": item.get("secName") or item.get("companyName"),
                    "title": item.get("title") or item.get("announcementTitle"),
                    "published_at": item.get("publishTime") or item.get("publishDate"),
                    "url": urljoin("https://disc.static.szse.cn/", str(url)),
                    "announcement_type": item.get("categoryName"),
                    "metadata": {"exchange": "SZSE"},
                }
            )
        return records


class BseSourceProvider(_ChinaAnnouncementProvider):
    provider_name = "bse-announcements"
    provider_version = "1"
    publisher = "北京证券交易所"
    endpoint = "https://www.bse.cn/disclosureInfoController/companyAnnouncement.do"

    @classmethod
    def capability(cls) -> OfficialSourceCapability:
        return OfficialSourceCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN"],
            official_domains=["bse.cn"],
            authentication="none; public website query",
            discovery=CoverageLevel.PARTIAL,
            original_documents=CoverageLevel.COMPLETE,
            history=CoverageLevel.PARTIAL,
            license="Public exchange disclosures; respect BSE terms and rate limits.",
            notes=["Beijing Stock Exchange listed-company announcements only."],
        )

    def _records(self, identifier: str, *, limit: int) -> list[dict[str, Any]]:
        code, exchange = _ticker_market(identifier)
        if exchange != "BSE":
            raise ValueError("BSE provider requires a Beijing-listed ticker")
        response = self.client.post(
            self.endpoint,
            data={"companyCode": code, "page": "0", "pageSize": str(limit)},
            headers={
                "User-Agent": "Mozilla/5.0 CapexGraph/0.5",
                "Referer": "https://www.bse.cn/disclosure/announcement.html",
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = (
            payload.get("listInfo", {}).get("content")
            or payload.get("content")
            or payload.get("list")
            or []
        )
        records: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url = item.get("destFilePath") or item.get("url") or item.get("filePath")
            if not url:
                continue
            records.append(
                {
                    "external_id": item.get("announcementId") or item.get("id"),
                    "ticker": f"{code}.BJ",
                    "company_name": item.get("companyName") or item.get("xxfcbj"),
                    "title": item.get("disclosureTitle") or item.get("title"),
                    "published_at": item.get("publishDate") or item.get("publishTime"),
                    "url": urljoin("https://www.bse.cn/", str(url)),
                    "announcement_type": item.get("disclosureType"),
                    "metadata": {"exchange": "BSE"},
                }
            )
        return records


def china_source_capabilities() -> list[OfficialSourceCapability]:
    return [
        CninfoSourceProvider.capability(),
        SseSourceProvider.capability(),
        SzseSourceProvider.capability(),
        BseSourceProvider.capability(),
    ]
