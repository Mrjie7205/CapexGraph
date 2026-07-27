from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from capexgraph.domain import ResearchRun, SourceAuthority, SourceSuggestion

REGULATOR_DOMAINS = frozenset(
    {
        "sec.gov",
        "www.sec.gov",
        "data.sec.gov",
    }
)
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = frozenset({"gclid", "fbclid"})


def canonicalize_source_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Source URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("Source URLs cannot contain credentials")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        hostname = f"{hostname}:{port}"
    path = parsed.path or "/"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    return urlunsplit((scheme, hostname, path, urlencode(sorted(query_items)), ""))


def source_domain(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname:
        raise ValueError("Source URL has no hostname")
    return parsed.hostname.lower().rstrip(".")


def classify_source_authority(
    value: str,
    *,
    issuer_domains: Sequence[str] = (),
) -> SourceAuthority:
    domain = source_domain(value)
    if domain in REGULATOR_DOMAINS or domain.endswith(".sec.gov"):
        return SourceAuthority.REGULATOR
    normalized_issuers = {
        item.lower().removeprefix("www.").rstrip(".") for item in issuer_domains if item.strip()
    }
    comparable = domain.removeprefix("www.")
    if any(comparable == item or comparable.endswith(f".{item}") for item in normalized_issuers):
        return SourceAuthority.ISSUER
    return SourceAuthority.OTHER


def source_suggestion_id(run_id: str, canonical_url: str, prefix: str = "source") -> str:
    digest = hashlib.sha256(f"{run_id}:{canonical_url}".encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


class SourceDiscoveryProvider(Protocol):
    provider_name: str
    provider_version: str

    def discover(
        self,
        run: ResearchRun,
        *,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        """Return untrusted source suggestions; never captured evidence."""
        ...
