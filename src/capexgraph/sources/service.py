from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from capexgraph.domain import (
    EvidenceKind,
    SourceSuggestion,
    SourceSuggestionStatus,
)
from capexgraph.providers.sources import (
    ManualOfficialUrlProvider,
    SecEdgarSourceProvider,
    SourceDiscoveryProvider,
    canonicalize_source_url,
)
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.sources.store import SourceSuggestionStore
from capexgraph.tools.evidence import (
    EvidenceCollector,
    EvidenceSourceRequest,
    attach_collected_document,
)
from capexgraph.workflows import load_run, save_run


class SourceCaptureError(RuntimeError):
    """Capture failed after the failure state was persisted."""


def _now() -> datetime:
    return datetime.now(UTC)


class SourceDiscoveryService:
    def __init__(self, store: SourceSuggestionStore | None = None) -> None:
        self.store = store or SourceSuggestionStore()

    @staticmethod
    def _run(run_id: str):
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        return run

    @staticmethod
    def _record_provider(run, provider: SourceDiscoveryProvider) -> None:
        providers = run.manifest.setdefault("source_discovery_providers", [])
        identity = {
            "name": provider.provider_name,
            "version": provider.provider_version,
        }
        if identity not in providers:
            providers.append(identity)
        save_run(run)

    def _write_queue_artifact(self, run_id: str) -> None:
        atomic_write_json(
            runs_dir() / run_id / "sources.json",
            [item.model_dump(mode="json") for item in self.store.list(run_id)],
        )

    def discover(
        self,
        run_id: str,
        *,
        provider: SourceDiscoveryProvider | None = None,
        identifier: str | None = None,
        forms: Sequence[str] = (),
        limit: int = 10,
    ) -> list[SourceSuggestion]:
        run = self._run(run_id)
        active_provider = provider or SecEdgarSourceProvider()
        try:
            suggestions = active_provider.discover(
                run,
                identifier=identifier,
                forms=forms,
                limit=limit,
            )
        except Exception as error:
            failures = run.manifest.setdefault("source_discovery_errors", [])
            failures.append(
                {
                    "provider": active_provider.provider_name,
                    "version": active_provider.provider_version,
                    "at": _now().isoformat(),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            save_run(run)
            raise
        persisted = [self.store.add(suggestion) for suggestion in suggestions]
        self._record_provider(run, active_provider)
        self._write_queue_artifact(run_id)
        return persisted

    def suggest_url(
        self,
        run_id: str,
        *,
        url: str,
        title: str,
        kind: EvidenceKind,
        publisher: str | None = None,
        published_at: date | None = None,
        issuer_domains: Sequence[str] = (),
        reason: str | None = None,
    ) -> SourceSuggestion:
        run = self._run(run_id)
        provider = ManualOfficialUrlProvider()
        suggestion = provider.suggest(
            run,
            url=url,
            title=title,
            kind=kind,
            publisher=publisher,
            published_at=published_at,
            issuer_domains=issuer_domains,
            reason=reason,
        )
        persisted = self.store.add(suggestion)
        self._record_provider(run, provider)
        self._write_queue_artifact(run_id)
        return persisted

    def list(
        self,
        run_id: str,
        *,
        status: SourceSuggestionStatus | None = None,
    ) -> list[SourceSuggestion]:
        self._run(run_id)
        return self.store.list(run_id, status=status)

    def _get_for_run(self, run_id: str, suggestion_id: str) -> SourceSuggestion:
        self._run(run_id)
        suggestion = self.store.get(suggestion_id)
        if suggestion is None or suggestion.run_id != run_id:
            raise KeyError(f"Source suggestion not found: {suggestion_id}")
        return suggestion

    def dismiss(self, run_id: str, suggestion_id: str) -> SourceSuggestion:
        suggestion = self._get_for_run(run_id, suggestion_id)
        if suggestion.status == SourceSuggestionStatus.CAPTURED:
            raise ValueError("Captured source suggestions cannot be dismissed")
        suggestion.status = SourceSuggestionStatus.DISMISSED
        suggestion.updated_at = _now()
        suggestion.error = ""
        saved = self.store.save(suggestion)
        self._write_queue_artifact(run_id)
        return saved

    def capture(
        self,
        run_id: str,
        suggestion_id: str,
        *,
        collector: EvidenceCollector | None = None,
        retry: bool = False,
    ) -> SourceSuggestion:
        run = self._run(run_id)
        suggestion = self._get_for_run(run_id, suggestion_id)
        allowed = {
            SourceSuggestionStatus.SUGGESTED,
            SourceSuggestionStatus.SELECTED,
            SourceSuggestionStatus.CAPTURE_FAILED,
        }
        if retry:
            allowed.add(SourceSuggestionStatus.DUPLICATE)
        if suggestion.status not in allowed:
            raise ValueError(
                f"Source suggestion cannot be captured from status {suggestion.status.value}"
            )

        suggestion.status = SourceSuggestionStatus.SELECTED
        suggestion.selected_at = suggestion.selected_at or _now()
        suggestion.updated_at = _now()
        suggestion.error = ""
        self.store.save(suggestion)
        self._write_queue_artifact(run_id)
        suggestion.status = SourceSuggestionStatus.CAPTURE_PENDING
        suggestion.updated_at = _now()
        self.store.save(suggestion)
        self._write_queue_artifact(run_id)

        try:
            document = (collector or EvidenceCollector()).collect(
                run_id,
                EvidenceSourceRequest(
                    id=suggestion.id,
                    title=suggestion.title,
                    kind=suggestion.kind,
                    url=suggestion.url,
                    published_at=suggestion.published_at,
                    publisher=suggestion.publisher,
                ),
            )
            final_url = canonicalize_source_url(str(document.evidence.source_url))
            same_url = self.store.find_by_url(run_id, final_url)
            if (
                same_url is not None
                and same_url.id != suggestion.id
                and same_url.evidence_id is not None
            ):
                suggestion.status = SourceSuggestionStatus.DUPLICATE
                suggestion.evidence_id = same_url.evidence_id
                suggestion.duplicate_of = same_url.id
            else:
                duplicate_evidence = next(
                    (
                        evidence
                        for evidence in run.evidence
                        if evidence.source_hash == document.evidence.source_hash
                    ),
                    None,
                )
                duplicate_suggestion = self.store.find_by_content_hash(
                    run_id,
                    document.evidence.source_hash or "",
                    exclude_id=suggestion.id,
                )
                if duplicate_evidence is not None:
                    suggestion.status = SourceSuggestionStatus.DUPLICATE
                    suggestion.evidence_id = duplicate_evidence.id
                    suggestion.duplicate_of = (
                        duplicate_suggestion.id if duplicate_suggestion else duplicate_evidence.id
                    )
                else:
                    attach_collected_document(run_id, document)
                    suggestion.status = SourceSuggestionStatus.CAPTURED
                    suggestion.evidence_id = document.evidence.id
                    suggestion.captured_at = _now()
            suggestion.final_url = document.evidence.source_url
            suggestion.content_hash = document.evidence.source_hash
            if same_url is None or same_url.id == suggestion.id:
                suggestion.canonical_url = final_url
            suggestion.updated_at = _now()
            suggestion.error = ""
            saved = self.store.save(suggestion)
            self._write_queue_artifact(run_id)
            from capexgraph.events import EventCalendarService

            try:
                EventCalendarService(source_store=self.store).ingest_suggestions(
                    run_id,
                    [saved],
                )
            except Exception as event_error:
                refreshed_run = self._run(run_id)
                refreshed_run.manifest.setdefault("event_calendar_errors", []).append(
                    {
                        "suggestion_id": saved.id,
                        "error": f"{type(event_error).__name__}: {event_error}",
                        "observed_at": _now().isoformat(),
                    }
                )
                save_run(refreshed_run)
            return saved
        except Exception as error:
            suggestion.status = SourceSuggestionStatus.CAPTURE_FAILED
            suggestion.updated_at = _now()
            suggestion.error = f"{type(error).__name__}: {error}"
            self.store.save(suggestion)
            self._write_queue_artifact(run_id)
            raise SourceCaptureError(suggestion.error) from error

    def retry(
        self,
        run_id: str,
        suggestion_id: str,
        *,
        collector: EvidenceCollector | None = None,
    ) -> SourceSuggestion:
        return self.capture(
            run_id,
            suggestion_id,
            collector=collector,
            retry=True,
        )
