from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from capexgraph.domain import (
    CoverageLevel,
    ThemeDefinition,
    ThemeMembership,
    ThemeMembershipRole,
    ThemeSource,
    ThemeSourceKind,
)


@dataclass(frozen=True)
class ThemeFixtureImportResult:
    definition: ThemeDefinition
    sources: list[ThemeSource]
    memberships: list[ThemeMembership]


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _aware_datetime(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("theme import timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _date(value: str | date | None) -> date | None:
    if value in {None, ""}:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def import_theme_json(payload: bytes | str | dict[str, Any]) -> ThemeFixtureImportResult:
    if isinstance(payload, bytes):
        document = json.loads(payload.decode("utf-8"))
    elif isinstance(payload, str):
        document = json.loads(payload)
    else:
        document = payload
    if not isinstance(document, dict):
        raise ValueError("theme import must be a JSON object")
    theme = document.get("theme")
    raw_sources = document.get("sources")
    if not isinstance(theme, dict) or not isinstance(raw_sources, list):
        raise ValueError("theme import requires theme and sources")

    theme_id = str(theme["theme_id"]).strip()
    known_at = _aware_datetime(theme["known_at"])
    definition_semantic = {
        key: theme.get(key)
        for key in (
            "theme_id",
            "name",
            "aliases",
            "description",
            "markets",
            "benchmark_tickers",
            "valid_from",
            "valid_to",
        )
    }
    definition_hash = _canonical_hash(definition_semantic)
    definition = ThemeDefinition(
        id=str(theme.get("id") or f"theme-def-{definition_hash[:20]}"),
        theme_id=theme_id,
        version=int(theme.get("version", 1)),
        name=str(theme["name"]),
        aliases=[str(item) for item in theme.get("aliases", [])],
        description=str(theme.get("description", "")),
        markets=[str(item).upper() for item in theme.get("markets", [])],
        benchmark_tickers={
            str(key).upper(): str(value).upper()
            for key, value in dict(theme.get("benchmark_tickers", {})).items()
        },
        valid_from=_date(theme["valid_from"]),
        valid_to=_date(theme.get("valid_to")),
        known_at=known_at,
        created_at=_aware_datetime(theme.get("created_at", theme["known_at"])),
        definition_hash=definition_hash,
        metadata=dict(theme.get("metadata", {})),
    )

    sources: list[ThemeSource] = []
    memberships: list[ThemeMembership] = []
    for source_index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, dict):
            raise ValueError("theme source must be an object")
        raw_members = raw_source.get("memberships", [])
        if not isinstance(raw_members, list):
            raise ValueError("source memberships must be an array")
        kind = ThemeSourceKind(str(raw_source["kind"]))
        observed_at = _aware_datetime(raw_source["observed_at"])
        source_semantic = {
            key: raw_source.get(key)
            for key in (
                "name",
                "kind",
                "provider",
                "provider_version",
                "market",
                "source_url",
                "license",
                "coverage",
                "observed_at",
                "memberships",
            )
        }
        source_hash = _canonical_hash(source_semantic)
        source_id = str(
            raw_source.get("id")
            or f"theme-source-{theme_id}-{source_index + 1}-{source_hash[:12]}"
        )
        source = ThemeSource(
            id=source_id,
            theme_id=theme_id,
            kind=kind,
            name=str(raw_source["name"]),
            provider=str(raw_source["provider"]),
            provider_version=str(raw_source.get("provider_version", "1")),
            market=str(raw_source["market"]).upper(),
            source_url=raw_source.get("source_url"),
            license=str(raw_source.get("license", "User-provided local import")),
            coverage=CoverageLevel(str(raw_source.get("coverage", "partial"))),
            observed_at=observed_at,
            content_hash=source_hash,
            metadata=dict(raw_source.get("metadata", {})),
        )
        sources.append(source)
        for raw_member in raw_members:
            if not isinstance(raw_member, dict):
                raise ValueError("theme membership must be an object")
            if (
                kind != ThemeSourceKind.EVIDENCE_GRAPH
                and raw_member.get("exposure_score") is not None
            ):
                raise ValueError(
                    "index, ETF, vendor, and manual membership cannot set exposure_score"
                )
            ticker = str(raw_member["ticker"]).strip().upper()
            valid_from = _date(raw_member["valid_from"])
            member_known_at = _aware_datetime(raw_member.get("known_at", observed_at))
            member_semantic = {
                **raw_member,
                "theme_id": theme_id,
                "source_id": source_id,
            }
            member_hash = _canonical_hash(member_semantic)
            memberships.append(
                ThemeMembership(
                    id=str(raw_member.get("id") or f"membership-{member_hash[:24]}"),
                    theme_id=theme_id,
                    source_id=source_id,
                    ticker=ticker,
                    entity_name=str(raw_member.get("entity_name") or ticker),
                    market=str(raw_member.get("market") or source.market).upper(),
                    exchange=str(raw_member["exchange"]).upper(),
                    role=ThemeMembershipRole(str(raw_member.get("role", "core"))),
                    valid_from=valid_from,
                    valid_to=_date(raw_member.get("valid_to")),
                    known_at=member_known_at,
                    observed_at=_aware_datetime(raw_member.get("observed_at", observed_at)),
                    membership_weight=raw_member.get("membership_weight"),
                    recognition_score=(
                        0.0
                        if kind == ThemeSourceKind.EVIDENCE_GRAPH
                        else float(raw_member.get("recognition_score", 1.0))
                    ),
                    exposure_score=(
                        raw_member.get("exposure_score")
                        if kind == ThemeSourceKind.EVIDENCE_GRAPH
                        else None
                    ),
                    source_hash=member_hash,
                    metadata=dict(raw_member.get("metadata", {})),
                )
            )
    return ThemeFixtureImportResult(
        definition=definition,
        sources=sources,
        memberships=memberships,
    )


def import_theme_csv(
    payload: bytes | str,
    *,
    theme: dict[str, Any],
    source: dict[str, Any],
) -> ThemeFixtureImportResult:
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    rows = list(csv.DictReader(io.StringIO(text)))
    normalized_source = {**source, "memberships": rows}
    return import_theme_json({"theme": theme, "sources": [normalized_source]})


def load_frozen_theme_fixture(
    name: str = "theme_memory_semiconductors_multimarket.json",
) -> ThemeFixtureImportResult:
    path = files("capexgraph.fixtures").joinpath(name)
    return import_theme_json(Path(str(path)).read_bytes())
