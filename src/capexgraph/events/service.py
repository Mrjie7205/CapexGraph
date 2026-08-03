from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from capexgraph.domain import (
    CorporateEventStatus,
    CorporateEventType,
    CorporateEventVersion,
    ProposalHumanStatus,
    SourceSuggestion,
    ThemeResearchProposal,
)
from capexgraph.events.disclosures import OfficialDisclosureEventMapper
from capexgraph.events.sec import SecFilingEventMapper
from capexgraph.events.store import EventCalendarStore
from capexgraph.providers.sources import SourceDiscoveryProvider
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.sources.store import SourceSuggestionStore
from capexgraph.workflows import load_run, save_run


class EventCalendarService:
    def __init__(
        self,
        *,
        store: EventCalendarStore | None = None,
        source_store: SourceSuggestionStore | None = None,
        sec_mapper: SecFilingEventMapper | None = None,
        disclosure_mapper: OfficialDisclosureEventMapper | None = None,
    ) -> None:
        self.store = store or EventCalendarStore(
            source_store.db_path if source_store is not None else None
        )
        self.source_store = source_store or SourceSuggestionStore(self.store.db_path)
        self.sec_mapper = sec_mapper or SecFilingEventMapper()
        self.disclosure_mapper = disclosure_mapper or OfficialDisclosureEventMapper()

    @staticmethod
    def _run(run_id: str):
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        return run

    @staticmethod
    def _version_hash(draft: dict[str, Any]) -> str:
        semantic = {
            key: value
            for key, value in draft.items()
            if key not in {"observed_at", "revision_reason"}
        }
        raw = json.dumps(semantic, ensure_ascii=False, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    def _persist_draft(self, draft: dict[str, Any]) -> CorporateEventVersion:
        version_hash = self._version_hash(draft)
        existing = self.store.find_version_hash(
            draft["run_id"],
            draft["event_key"],
            version_hash,
        )
        if existing is not None:
            return existing
        latest = self.store.latest_for_key(draft["run_id"], draft["event_key"])
        version = (latest.version + 1) if latest else 1
        digest = hashlib.sha256(
            f"{draft['run_id']}:{draft['event_key']}:{version_hash}".encode()
        ).hexdigest()[:24]
        event = CorporateEventVersion(
            id=f"event-{digest}",
            version=version,
            version_hash=version_hash,
            **draft,
        )
        return self.store.save(event)

    def ingest_suggestions(
        self,
        run_id: str,
        suggestions: list[SourceSuggestion],
    ) -> list[CorporateEventVersion]:
        self._run(run_id)
        events: list[CorporateEventVersion] = []
        for suggestion in suggestions:
            if suggestion.run_id != run_id:
                continue
            mapper = next(
                (
                    item
                    for item in (self.sec_mapper, self.disclosure_mapper)
                    if item.supports(suggestion)
                ),
                None,
            )
            if mapper is not None:
                events.append(self._persist_draft(mapper.map(suggestion)))
        if events:
            self._propose_linked_research(events)
            self._write_artifact(run_id)
        return events

    def _propose_linked_research(
        self,
        events: list[CorporateEventVersion],
    ) -> list[ThemeResearchProposal]:
        """Link official events to known theme members without executing a model."""

        from capexgraph.monitoring.store import MainlineStore
        from capexgraph.themes.store import ThemeRegistryStore

        theme_store = ThemeRegistryStore(self.store.db_path)
        mainline_store = MainlineStore(self.store.db_path)
        definitions = theme_store.list_definitions(latest_only=True)
        created: list[ThemeResearchProposal] = []
        for event in events:
            if not event.ticker:
                continue
            event_date = (
                event.effective_date
                or event.expected_date
                or event.announced_date
                or event.observed_at.date()
            )
            for definition in definitions:
                memberships = theme_store.list_memberships(
                    definition.theme_id,
                    as_of_date=event_date,
                    knowledge_cutoff=event.observed_at,
                    market=event.market,
                )
                if not any(item.ticker == event.ticker for item in memberships):
                    continue
                assessment = mainline_store.latest_assessment(definition.theme_id)
                if assessment is None:
                    continue
                existing = next(
                    (
                        item
                        for item in mainline_store.list_proposals(definition.theme_id)
                        if item.assessment_id == assessment.id
                        and item.action == "reevaluate_candidates"
                    ),
                    None,
                )
                if existing is not None:
                    continue
                digest = hashlib.sha256(
                    f"{definition.theme_id}:{assessment.id}:{event.id}".encode()
                ).hexdigest()[:24]
                proposal = ThemeResearchProposal(
                    id=f"theme-proposal-{digest}",
                    theme_id=definition.theme_id,
                    assessment_id=assessment.id,
                    action="reevaluate_candidates",
                    human_status=ProposalHumanStatus.PENDING,
                    auto_execute=False,
                    reason=(
                        f"Official event {event.id} ({event.title}) affects known member "
                        f"{event.ticker}; explicit confirmation is required before re-evaluation."
                    ),
                )
                created.append(mainline_store.save_proposal(proposal))
        return created

    def refresh_from_sources(self, run_id: str) -> list[CorporateEventVersion]:
        self._run(run_id)
        events = self.ingest_suggestions(run_id, self.source_store.list(run_id))
        if not events:
            self._write_artifact(run_id)
        return events

    def discover_sec_filings(
        self,
        run_id: str,
        *,
        provider: SourceDiscoveryProvider | None = None,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[CorporateEventVersion]:
        from capexgraph.sources.service import SourceDiscoveryService

        suggestions = SourceDiscoveryService(store=self.source_store).discover(
            run_id,
            provider=provider,
            identifier=identifier,
            forms=forms,
            limit=limit,
        )
        return self.ingest_suggestions(run_id, suggestions)

    def discover_official(
        self,
        run_id: str,
        *,
        provider: SourceDiscoveryProvider,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[CorporateEventVersion]:
        from capexgraph.sources.service import SourceDiscoveryService

        suggestions = SourceDiscoveryService(store=self.source_store).discover(
            run_id,
            provider=provider,
            identifier=identifier,
            forms=forms,
            limit=limit,
        )
        return self.ingest_suggestions(run_id, suggestions)

    def list(
        self,
        run_id: str,
        *,
        as_of: datetime | None = None,
        latest_only: bool = True,
        ticker: str | None = None,
        event_type: CorporateEventType | None = None,
        status: CorporateEventStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[CorporateEventVersion]:
        self._run(run_id)
        return self.store.list(
            run_id,
            as_of=as_of,
            latest_only=latest_only,
            ticker=ticker,
            event_type=event_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

    def _write_artifact(self, run_id: str) -> None:
        run = self._run(run_id)
        versions = self.store.list(run_id, latest_only=False)
        latest = self.store.list(run_id, latest_only=True)
        generated_at = datetime.now(UTC)
        atomic_write_json(
            runs_dir() / run_id / "events.json",
            {
                "run_id": run_id,
                "generated_at": generated_at.isoformat(),
                "latest": [item.model_dump(mode="json") for item in latest],
                "versions": [item.model_dump(mode="json") for item in versions],
            },
        )
        providers = sorted(
            {(item.provider, item.provider_version) for item in versions}
        )
        run.manifest["event_calendar"] = {
            "latest_count": len(latest),
            "version_count": len(versions),
            "updated_at": generated_at.isoformat(),
            "providers": [
                {"name": name, "version": version}
                for name, version in providers
            ],
            "artifact": "events.json",
        }
        save_run(run)
