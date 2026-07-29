from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    SourceSuggestion,
)

PERIODIC_REPORT_FORMS = frozenset({"10-K", "10-Q", "20-F", "40-F"})


def parse_sec_acceptance(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


class SecFilingEventMapper:
    provider_name = "sec-edgar-event-mapper"
    provider_version = "1"
    supported_source_provider = "sec-edgar-submissions"

    def supports(self, suggestion: SourceSuggestion) -> bool:
        metadata = suggestion.metadata
        return (
            suggestion.provider == self.supported_source_provider
            and bool(metadata.get("cik"))
            and bool(metadata.get("accession"))
            and bool(metadata.get("form"))
        )

    def map(self, suggestion: SourceSuggestion) -> dict[str, Any]:
        if not self.supports(suggestion):
            raise ValueError("Source suggestion is not a supported SEC filing")
        metadata = suggestion.metadata
        cik = str(metadata["cik"]).zfill(10)
        accession = str(metadata["accession"])
        form = str(metadata["form"]).upper()
        base_form = form.removesuffix("/A")
        filing_date = suggestion.published_at
        if filing_date is None:
            raise ValueError("SEC filing event requires filing_date")
        known_at = parse_sec_acceptance(
            str(metadata.get("acceptance_datetime") or "")
        ) or datetime.combine(filing_date, datetime.min.time(), UTC)
        observed_at = (
            suggestion.captured_at
            or suggestion.updated_at
            or suggestion.discovered_at
        )
        event_type = (
            CorporateEventType.FINANCIAL_REPORT
            if base_form in PERIODIC_REPORT_FORMS
            else CorporateEventType.REGULATORY_FILING
        )
        stable_metadata = {
            key: metadata.get(key)
            for key in (
                "cik",
                "ticker",
                "company_name",
                "form",
                "filing_date",
                "report_date",
                "acceptance_datetime",
                "accession",
                "primary_document",
                "items",
                "is_xbrl",
                "is_inline_xbrl",
            )
            if metadata.get(key) not in {None, ""}
        }
        stable_metadata["source_provider"] = suggestion.provider
        stable_metadata["source_provider_version"] = suggestion.provider_version
        return {
            "event_key": f"sec:{cik}:{accession}",
            "run_id": suggestion.run_id,
            "entity_id": f"sec-cik-{cik}",
            "ticker": str(metadata.get("ticker") or "").strip().upper() or None,
            "entity_name": str(metadata.get("company_name") or f"SEC CIK {cik}"),
            "market": "US",
            "event_type": event_type,
            "status": CorporateEventStatus.OCCURRED,
            "title": suggestion.title,
            "description": (
                f"Official SEC {form} filing accepted for "
                f"{metadata.get('company_name') or cik}."
            ),
            "announced_date": filing_date,
            "expected_date": None,
            "effective_date": filing_date,
            "occurred_date": filing_date,
            "cancelled_date": None,
            "known_at": known_at,
            "observed_at": observed_at,
            "source_suggestion_id": suggestion.id,
            "evidence_id": suggestion.evidence_id,
            "source_url": suggestion.final_url or suggestion.url,
            "source_hash": suggestion.content_hash,
            "provider": self.provider_name,
            "provider_version": self.provider_version,
            "external_id": accession,
            "revision_reason": (
                "captured_evidence_linked"
                if suggestion.evidence_id
                else "official_metadata_discovered"
            ),
            "metadata": stable_metadata,
        }
