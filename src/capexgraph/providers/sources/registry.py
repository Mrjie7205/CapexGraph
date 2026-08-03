from __future__ import annotations

import os

import httpx

from capexgraph.config import load_project_env
from capexgraph.domain import CoverageLevel, OfficialSourceCapability
from capexgraph.providers.sources.base import SourceDiscoveryProvider
from capexgraph.providers.sources.china import (
    BseSourceProvider,
    CninfoSourceProvider,
    SseSourceProvider,
    SzseSourceProvider,
    china_source_capabilities,
)
from capexgraph.providers.sources.korea import (
    KindSourceProvider,
    OpenDartSourceProvider,
    korea_source_capabilities,
)
from capexgraph.providers.sources.sec import SecEdgarSourceProvider


def build_source_provider(
    name: str,
    *,
    client: httpx.Client | None = None,
) -> SourceDiscoveryProvider:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in {"sec", "edgar", "sec-edgar-submissions"}:
        return SecEdgarSourceProvider(client=client)
    if normalized in {"cninfo", "cninfo-announcements"}:
        return CninfoSourceProvider(client=client)
    if normalized in {"sse", "sse-announcements"}:
        return SseSourceProvider(client=client)
    if normalized in {"szse", "szse-announcements"}:
        return SzseSourceProvider(client=client)
    if normalized in {"bse", "bse-announcements"}:
        return BseSourceProvider(client=client)
    if normalized in {"opendart", "opendart-disclosures"}:
        load_project_env()
        return OpenDartSourceProvider(
            os.getenv("OPENDART_API_KEY"),
            client=client,
        )
    if normalized in {"kind", "kind-krx", "kind-krx-disclosures"}:
        return KindSourceProvider(client=client)
    raise ValueError(
        "Unknown source provider. Choose sec, cninfo, sse, szse, bse, opendart, or kind."
    )


def official_source_capabilities() -> list[OfficialSourceCapability]:
    sec = OfficialSourceCapability(
        provider="sec-edgar-submissions",
        provider_version="2",
        markets=["US"],
        official_domains=["sec.gov", "data.sec.gov"],
        authentication="identified User-Agent with real contact information",
        discovery=CoverageLevel.COMPLETE,
        original_documents=CoverageLevel.COMPLETE,
        history=CoverageLevel.PARTIAL,
        license="Public U.S. filings; comply with SEC fair-access policy.",
        notes=["Historical submissions shards require a separate bounded backfill."],
    )
    return [sec, *china_source_capabilities(), *korea_source_capabilities()]
