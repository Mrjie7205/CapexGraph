from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from capexgraph.domain import (
    EvidenceKind,
    ResearchRun,
    SourceSuggestion,
    SourceSuggestionStatus,
)
from capexgraph.providers.sources.base import (
    canonicalize_source_url,
    classify_source_authority,
    source_suggestion_id,
)


class ManualOfficialUrlProvider:
    """Turn a user-supplied public URL into a reviewable suggestion."""

    provider_name = "manual-official-url"
    provider_version = "1"

    def suggest(
        self,
        run: ResearchRun,
        *,
        url: str,
        title: str,
        kind: EvidenceKind,
        publisher: str | None = None,
        published_at: date | None = None,
        issuer_domains: Sequence[str] = (),
        reason: str | None = None,
    ) -> SourceSuggestion:
        canonical_url = canonicalize_source_url(url)
        authority = classify_source_authority(
            canonical_url,
            issuer_domains=issuer_domains,
        )
        authority_reason = {
            "regulator": "URL uses a recognized regulator domain.",
            "issuer": "URL matches an issuer domain supplied for this run.",
            "other": "User supplied this public URL; official ownership is not verified.",
        }[authority.value]
        return SourceSuggestion(
            id=source_suggestion_id(run.id, canonical_url, prefix="manual"),
            run_id=run.id,
            title=title,
            url=canonical_url,
            canonical_url=canonical_url,
            kind=kind,
            publisher=publisher,
            authority=authority,
            reason=reason or authority_reason,
            provider=self.provider_name,
            provider_version=self.provider_version,
            status=SourceSuggestionStatus.SUGGESTED,
            published_at=published_at,
            metadata={"issuer_domains": list(issuer_domains)},
        )
