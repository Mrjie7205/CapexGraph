from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time

from capexgraph.domain import (
    CoverageLevel,
    ThemeDefinition,
    ThemeMembership,
    ThemeSource,
    ThemeSourceKind,
    ThemeUniverseMember,
    ThemeUniverseSnapshot,
)
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.themes.importers import ThemeFixtureImportResult
from capexgraph.themes.store import ThemeRegistryStore


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class ThemeRegistryService:
    def __init__(self, store: ThemeRegistryStore | None = None) -> None:
        self.store = store or ThemeRegistryStore()

    def persist_import(self, result: ThemeFixtureImportResult) -> ThemeDefinition:
        existing = self.store.find_definition_hash(
            result.definition.theme_id,
            result.definition.definition_hash,
        )
        definition = existing or self.store.save_definition(result.definition)
        for source in result.sources:
            self.store.save_source(source)
        self.store.save_memberships(result.memberships)
        return definition

    def register_definition(
        self,
        *,
        theme_id: str,
        name: str,
        valid_from: date,
        known_at: datetime,
        aliases: list[str] | None = None,
        description: str = "",
        markets: list[str] | None = None,
        benchmark_tickers: dict[str, str] | None = None,
        valid_to: date | None = None,
        metadata: dict | None = None,
    ) -> ThemeDefinition:
        semantic = {
            "theme_id": theme_id,
            "name": name,
            "aliases": aliases or [],
            "description": description,
            "markets": markets or [],
            "benchmark_tickers": benchmark_tickers or {},
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
        definition_hash = _hash(semantic)
        existing = self.store.find_definition_hash(theme_id, definition_hash)
        if existing is not None:
            return existing
        latest = self.store.latest_definition(theme_id)
        version = latest.version + 1 if latest else 1
        return self.store.save_definition(
            ThemeDefinition(
                id=f"theme-def-{definition_hash[:20]}",
                theme_id=theme_id,
                version=version,
                name=name,
                aliases=aliases or [],
                description=description,
                markets=[item.upper() for item in (markets or [])],
                benchmark_tickers={
                    key.upper(): value.upper()
                    for key, value in (benchmark_tickers or {}).items()
                },
                valid_from=valid_from,
                valid_to=valid_to,
                known_at=known_at,
                definition_hash=definition_hash,
                metadata=metadata or {},
            )
        )

    def snapshot(
        self,
        theme_id: str,
        *,
        as_of_date: date,
        knowledge_cutoff: datetime | None = None,
        market: str | None = None,
    ) -> ThemeUniverseSnapshot:
        cutoff = knowledge_cutoff or datetime.combine(as_of_date, time.max, UTC)
        if cutoff.tzinfo is None:
            raise ValueError("knowledge_cutoff must include a timezone")
        cutoff = cutoff.astimezone(UTC)
        definition = self.store.latest_definition(
            theme_id,
            as_of_date=as_of_date,
            knowledge_cutoff=cutoff,
        )
        if definition is None:
            raise KeyError(
                f"No theme definition for {theme_id} was knowable on {as_of_date.isoformat()}"
            )
        memberships = self.store.list_memberships(
            theme_id,
            as_of_date=as_of_date,
            knowledge_cutoff=cutoff,
            market=market.upper() if market else None,
        )
        latest_by_source_ticker: dict[tuple[str, str], ThemeMembership] = {}
        for membership in memberships:
            key = (membership.source_id, membership.ticker)
            previous = latest_by_source_ticker.get(key)
            if previous is None or membership.known_at > previous.known_at:
                latest_by_source_ticker[key] = membership
        sources = {
            source.id: source
            for source in self.store.list_sources(
                theme_id,
                market=market.upper() if market else None,
            )
            if source.observed_at <= cutoff
        }
        grouped: dict[str, list[ThemeMembership]] = {}
        for membership in latest_by_source_ticker.values():
            if membership.source_id in sources:
                grouped.setdefault(membership.ticker, []).append(membership)

        members: list[ThemeUniverseMember] = []
        for ticker, records in sorted(grouped.items()):
            recognition = max(
                (
                    item.recognition_score
                    for item in records
                    if sources[item.source_id].kind != ThemeSourceKind.EVIDENCE_GRAPH
                ),
                default=0.0,
            )
            exposure_values = [
                item.exposure_score
                for item in records
                if sources[item.source_id].kind == ThemeSourceKind.EVIDENCE_GRAPH
                and item.exposure_score is not None
            ]
            weights = [
                item.membership_weight
                for item in records
                if item.membership_weight is not None
            ]
            members.append(
                ThemeUniverseMember(
                    ticker=ticker,
                    entity_name=records[0].entity_name,
                    market=records[0].market,
                    exchange=records[0].exchange,
                    roles=sorted({item.role for item in records}, key=lambda item: item.value),
                    source_ids=sorted({item.source_id for item in records}),
                    recognition_score=recognition,
                    exposure_score=max(exposure_values) if exposure_values else None,
                    weight=max(weights) if weights else None,
                )
            )
        used_source_ids = sorted(
            {source_id for member in members for source_id in member.source_ids}
        )
        relevant_sources = list(sources.values())
        missing_sources = [
            source.id
            for source in relevant_sources
            if source.coverage in {CoverageLevel.BLOCKED, CoverageLevel.UNSUPPORTED}
        ]
        partial = bool(missing_sources) or any(
            source.coverage != CoverageLevel.COMPLETE for source in relevant_sources
        )
        semantic = {
            "theme_id": theme_id,
            "definition_id": definition.id,
            "as_of_date": as_of_date,
            "knowledge_cutoff": cutoff,
            "members": [item.model_dump(mode="json") for item in members],
            "source_ids": used_source_ids,
            "partial": partial,
            "missing_sources": missing_sources,
        }
        content_hash = _hash(semantic)
        snapshot = ThemeUniverseSnapshot(
            id=f"theme-snapshot-{content_hash[:24]}",
            theme_id=theme_id,
            definition_id=definition.id,
            as_of_date=as_of_date,
            knowledge_cutoff=cutoff,
            members=members,
            source_ids=used_source_ids,
            partial=partial,
            missing_sources=missing_sources,
            content_hash=content_hash,
        )
        self.store.save_snapshot(snapshot)
        path = runs_dir() / "_themes" / theme_id / "snapshots" / f"{snapshot.id}.json"
        atomic_write_json(path, snapshot.model_dump(mode="json"))
        return snapshot

    def list_definitions(self) -> list[ThemeDefinition]:
        return self.store.list_definitions(latest_only=True)

    def list_memberships(
        self,
        theme_id: str,
        *,
        as_of_date: date,
        knowledge_cutoff: datetime | None = None,
        market: str | None = None,
    ) -> list[ThemeMembership]:
        cutoff = knowledge_cutoff or datetime.combine(as_of_date, time.max, UTC)
        return self.store.list_memberships(
            theme_id,
            as_of_date=as_of_date,
            knowledge_cutoff=cutoff,
            market=market,
        )

    def list_sources(self, theme_id: str) -> list[ThemeSource]:
        return self.store.list_sources(theme_id)
