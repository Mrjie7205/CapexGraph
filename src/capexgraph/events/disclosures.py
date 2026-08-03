from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    SourceSuggestion,
)

SUPPORTED_PROVIDERS = frozenset(
    {
        "cninfo-announcements",
        "sse-announcements",
        "szse-announcements",
        "bse-announcements",
        "opendart-disclosures",
        "kind-krx-disclosures",
    }
)


def _parse_datetime(value: object, fallback: date) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
        except ValueError:
            pass
    return datetime.combine(fallback, datetime.min.time(), UTC)


def _parse_date(value: object) -> date | None:
    if value in {None, ""}:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def classify_disclosure(title: str, announcement_type: str = "") -> CorporateEventType:
    text = f"{title} {announcement_type}".casefold()
    mappings = (
        (
            CorporateEventType.FINANCIAL_REPORT,
            ("年度报告", "季度报告", "半年度报告", "사업보고서", "분기보고서", "반기보고서"),
        ),
        (
            CorporateEventType.EARNINGS,
            ("业绩预告", "业绩快报", "经营业绩", "잠정실적", "영업실적", "실적공시"),
        ),
        (CorporateEventType.GUIDANCE, ("指引", "盈利预测", "전망", "가이던스")),
        (CorporateEventType.DIVIDEND, ("分红", "权益分派", "利润分配", "배당")),
        (CorporateEventType.SPLIT, ("股份拆分", "股票分割", "주식분할")),
        (CorporateEventType.LOCKUP_EXPIRY, ("解禁", "限售股", "보호예수")),
        (CorporateEventType.INVESTOR_DAY, ("投资者日", "业绩说明会", "기업설명회")),
        (
            CorporateEventType.CAPEX_MILESTONE,
            ("资本开支", "投资项目", "扩建", "시설투자", "신규시설투자"),
        ),
        (
            CorporateEventType.PRODUCTION_MILESTONE,
            ("投产", "量产", "产能", "生产线", "양산", "생산능력"),
        ),
    )
    for event_type, terms in mappings:
        if any(term.casefold() in text for term in terms):
            return event_type
    return CorporateEventType.REGULATORY_FILING


class OfficialDisclosureEventMapper:
    provider_name = "official-disclosure-event-mapper"
    provider_version = "1"

    def supports(self, suggestion: SourceSuggestion) -> bool:
        return (
            suggestion.provider in SUPPORTED_PROVIDERS
            and suggestion.metadata.get("jurisdiction") in {"CN", "KR"}
            and bool(suggestion.metadata.get("announcement_id"))
        )

    def map(self, suggestion: SourceSuggestion) -> dict[str, Any]:
        if not self.supports(suggestion):
            raise ValueError("Source suggestion is not a supported official disclosure")
        if suggestion.published_at is None:
            raise ValueError("Official disclosure requires published_at")
        metadata = suggestion.metadata
        jurisdiction = str(metadata["jurisdiction"])
        ticker = str(metadata.get("ticker") or "").strip().upper() or None
        external_id = str(metadata["announcement_id"])
        announcement_type = str(metadata.get("announcement_type") or "")
        title = suggestion.title
        text = f"{title} {announcement_type}".casefold()
        expected_date = _parse_date(metadata.get("expected_date"))
        effective_date = _parse_date(metadata.get("effective_date"))
        cancelled = any(item in text for item in ("取消", "终止", "撤回", "철회", "취소"))
        revised = any(item in text for item in ("更正", "修订", "更新", "정정", "변경"))
        if cancelled:
            status = CorporateEventStatus.CANCELLED
        elif revised:
            status = CorporateEventStatus.REVISED
        elif expected_date is not None and any(item in text for item in ("预约", "将于", "예정")):
            status = CorporateEventStatus.SCHEDULED
        else:
            status = CorporateEventStatus.OCCURRED
        known_at = _parse_datetime(
            metadata.get("published_datetime"),
            suggestion.published_at,
        )
        observed_at = suggestion.captured_at or suggestion.updated_at or suggestion.discovered_at
        if observed_at < known_at:
            observed_at = known_at
        entity_identity = (
            str(metadata.get("corp_code") or "").strip()
            or ticker
            or str(metadata.get("company_name") or external_id)
        )
        stable_metadata = {
            key: metadata.get(key)
            for key in (
                "jurisdiction",
                "ticker",
                "company_name",
                "announcement_id",
                "announcement_type",
                "report_period",
                "published_datetime",
                "original_document_url",
                "corp_code",
                "exchange",
                "revision_marker",
            )
            if metadata.get(key) not in {None, ""}
        }
        stable_metadata["source_provider"] = suggestion.provider
        stable_metadata["source_provider_version"] = suggestion.provider_version
        return {
            "event_key": f"{jurisdiction.lower()}:{suggestion.provider}:{external_id}",
            "run_id": suggestion.run_id,
            "entity_id": f"{jurisdiction.lower()}-{entity_identity}",
            "ticker": ticker,
            "entity_name": str(metadata.get("company_name") or ticker or entity_identity),
            "market": jurisdiction,
            "event_type": classify_disclosure(title, announcement_type),
            "status": status,
            "title": title,
            "description": (
                f"Official {jurisdiction} disclosure published by {suggestion.publisher}."
            ),
            "announced_date": suggestion.published_at,
            "expected_date": expected_date,
            "effective_date": effective_date or suggestion.published_at,
            "occurred_date": (
                None if status == CorporateEventStatus.SCHEDULED else suggestion.published_at
            ),
            "cancelled_date": suggestion.published_at if cancelled else None,
            "known_at": known_at,
            "observed_at": observed_at,
            "source_suggestion_id": suggestion.id,
            "evidence_id": suggestion.evidence_id,
            "source_url": suggestion.final_url or suggestion.url,
            "source_hash": suggestion.content_hash,
            "provider": self.provider_name,
            "provider_version": self.provider_version,
            "external_id": external_id,
            "revision_reason": (
                "captured_evidence_linked"
                if suggestion.evidence_id
                else "official_metadata_discovered"
            ),
            "metadata": stable_metadata,
        }
