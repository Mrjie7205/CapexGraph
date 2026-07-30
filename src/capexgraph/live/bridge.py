from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

from capexgraph.domain import (
    EvidenceKind,
    EvidenceMode,
    EvidenceStatus,
    LiveAuditEntry,
    LiveEvidenceLink,
    LiveRuleAssessment,
    LiveRunContextLink,
    LiveSignalVersion,
    LiveUserAction,
    LiveVerificationState,
    LiveVerificationTask,
    LiveVerificationTaskStatus,
    ResearchAction,
    ResearchRun,
    RunMode,
    SourceAuthority,
)
from capexgraph.live.store import LiveSignalStore
from capexgraph.providers.errors import redact_provider_secrets
from capexgraph.providers.sources.base import classify_source_authority
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
from capexgraph.sources.store import SourceSuggestionStore
from capexgraph.tools.evidence import (
    EvidenceCollector,
    review_run_evidence,
    verify_evidence_hash,
)
from capexgraph.workflows import create_run, load_run, save_run

OPEN_VERIFICATION_STATES = frozenset(
    {
        LiveVerificationTaskStatus.PENDING,
        LiveVerificationTaskStatus.SOURCE_SUGGESTED,
        LiveVerificationTaskStatus.CAPTURE_PENDING,
        LiveVerificationTaskStatus.CAPTURED,
        LiveVerificationTaskStatus.FAILED,
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _identifier(prefix: str, payload: object, *, length: int = 24) -> str:
    return f"{prefix}-{_hash(payload)[:length]}"


class LiveResearchBridge:
    """Human-gated bridge from secondary live signals into evidence-first research."""

    def __init__(
        self,
        store: LiveSignalStore | None = None,
        *,
        source_service: SourceDiscoveryService | None = None,
        evidence_collector: EvidenceCollector | None = None,
    ) -> None:
        self.store = store or LiveSignalStore()
        self.source_service = source_service or SourceDiscoveryService(
            SourceSuggestionStore(self.store.db_path)
        )
        self.evidence_collector = evidence_collector

    def resolve_signal(self, reference: str) -> LiveSignalVersion:
        signal = self.store.get_signal(reference) or self.store.latest_signal(reference)
        if signal is None:
            raise KeyError(f"Live signal not found: {reference}")
        return signal

    @staticmethod
    def _require_confirmation(confirmed: bool, action: str) -> None:
        if not confirmed:
            raise ValueError(f"{action} requires explicit human confirmation")

    def _audit(
        self,
        *,
        signal_key: str,
        event_type: str,
        object_type: str,
        object_id: str,
        summary: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> LiveAuditEntry:
        return self.store.append_audit(
            LiveAuditEntry(
                signal_key=signal_key,
                event_type=event_type,
                object_type=object_type,
                object_id=object_id,
                actor=actor,
                summary=summary,
                details=details or {},
                occurred_at=occurred_at or _now(),
            )
        )

    def _record_action(
        self,
        signal_key: str,
        action: ResearchAction,
        *,
        identity: str,
        note: str,
        created_at: datetime | None = None,
    ) -> LiveUserAction:
        timestamp = created_at or _now()
        item = LiveUserAction(
            id=_identifier(
                "live-action",
                {"signal_key": signal_key, "action": action.value, "identity": identity},
            ),
            signal_key=signal_key,
            action=action,
            note=note,
            created_at=timestamp,
        )
        return self.store.save_user_action(item)

    def _append_signal_state(
        self,
        signal_key: str,
        state: LiveVerificationState,
        *,
        revision_reason: str,
        bridge_metadata: dict[str, Any],
    ) -> LiveSignalVersion:
        latest = self.store.latest_signal(signal_key)
        if latest is None:
            raise KeyError(f"Live signal not found: {signal_key}")
        transition_at = _now()
        metadata = {
            **latest.metadata,
            "bridge_transition_at": transition_at.isoformat(),
            "bridge": {
                **dict(latest.metadata.get("bridge") or {}),
                **bridge_metadata,
            },
        }
        semantic = {
            "signal_key": latest.signal_key,
            "category": latest.category.value,
            "title": latest.title,
            "observation_ids": latest.observation_ids,
            "channels": [item.value for item in latest.channels],
            "match_status": latest.match_status.value,
            "verification_state": state.value,
            "revision_reason": revision_reason,
            "bridge": metadata["bridge"],
        }
        version_hash = _hash(semantic)
        if latest.version_hash == version_hash:
            return latest
        version = latest.version + 1
        signal = latest.model_copy(
            update={
                "id": _identifier(
                    "live-signal",
                    {
                        "signal_key": signal_key,
                        "version": version,
                        "version_hash": version_hash,
                    },
                ),
                "version": version,
                "version_hash": version_hash,
                "verification_state": state,
                "revision_reason": revision_reason,
                "metadata": metadata,
            }
        )
        persisted = self.store.save_signal(signal)
        assessment = self.store.get_assessment(latest.id)
        if assessment is not None:
            self.store.save_assessment(
                LiveRuleAssessment(
                    **assessment.model_dump(
                        exclude={
                            "id",
                            "signal_version_id",
                            "created_at",
                            "rationale",
                        }
                    ),
                    id=_identifier(
                        "live-rule",
                        {
                            "signal_version_id": persisted.id,
                            "ruleset_hash": assessment.ruleset_hash,
                        },
                    ),
                    signal_version_id=persisted.id,
                    created_at=transition_at,
                    rationale=[
                        *assessment.rationale,
                        f"verification_transition:{state.value}",
                    ],
                )
            )
        self._audit(
            signal_key=signal_key,
            event_type="signal.verification_state_changed",
            object_type="live_signal_version",
            object_id=persisted.id,
            summary=f"Verification state changed to {state.value}.",
            details={
                "previous_version_id": latest.id,
                "verification_state": state.value,
                "revision_reason": revision_reason,
            },
            occurred_at=transition_at,
        )
        return persisted

    def create_verification_task(
        self,
        signal_reference: str,
        *,
        run_id: str | None = None,
        query: str | None = None,
        note: str = "",
        confirmed: bool,
    ) -> LiveVerificationTask:
        self._require_confirmation(confirmed, "Opening an official-source task")
        signal = self.resolve_signal(signal_reference)
        if run_id and load_run(run_id) is None:
            raise KeyError(f"Research run not found: {run_id}")
        existing = self.store.list_verification_tasks(
            signal_key=signal.signal_key,
            statuses=tuple(OPEN_VERIFICATION_STATES),
        )
        if existing:
            task = existing[0]
            if run_id and task.run_id not in {None, run_id}:
                raise ValueError(
                    "An open verification task is already linked to a different research run"
                )
            if run_id and task.run_id is None:
                task = task.model_copy(update={"run_id": run_id, "updated_at": _now()})
                self.store.save_verification_task(task)
            return task
        timestamp = _now()
        task = LiveVerificationTask(
            id=_identifier(
                "live-verify",
                {
                    "signal_key": signal.signal_key,
                    "signal_version_id": signal.id,
                    "created_at": timestamp.isoformat(),
                },
            ),
            signal_key=signal.signal_key,
            signal_version_id=signal.id,
            query=(query or f"{signal.title} official filing announcement").strip(),
            run_id=run_id,
            note=note.strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.store.save_verification_task(task)
        self._append_signal_state(
            signal.signal_key,
            LiveVerificationState.OFFICIAL_SOURCE_PENDING,
            revision_reason="official_source_task_created",
            bridge_metadata={"verification_task_id": task.id},
        )
        self._record_action(
            signal.signal_key,
            ResearchAction.VERIFY,
            identity=task.id,
            note=note or "Official-source verification task opened.",
            created_at=timestamp,
        )
        self._audit(
            signal_key=signal.signal_key,
            event_type="verification_task.created",
            object_type="live_verification_task",
            object_id=task.id,
            actor="human",
            summary="Official-source verification task opened.",
            details={"run_id": run_id, "query": task.query},
            occurred_at=timestamp,
        )
        return task

    def add_official_source(
        self,
        task_id: str,
        *,
        run_id: str | None,
        url: str,
        title: str,
        kind: EvidenceKind,
        publisher: str | None = None,
        published_at: date | None = None,
        issuer_domains: tuple[str, ...] = (),
        reason: str | None = None,
        confirmed: bool,
    ) -> LiveVerificationTask:
        self._require_confirmation(confirmed, "Adding an official-source candidate")
        task = self._task(task_id)
        if task.status not in {
            LiveVerificationTaskStatus.PENDING,
            LiveVerificationTaskStatus.SOURCE_SUGGESTED,
            LiveVerificationTaskStatus.FAILED,
        }:
            raise ValueError(
                f"Verification task cannot accept a source from status {task.status.value}"
            )
        resolved_run_id = run_id or task.run_id
        if not resolved_run_id or load_run(resolved_run_id) is None:
            raise KeyError("A persisted research run is required before adding a source")
        authority = classify_source_authority(url, issuer_domains=issuer_domains)
        if authority not in {SourceAuthority.REGULATOR, SourceAuthority.ISSUER}:
            raise ValueError(
                "Official-source candidates must use a recognized regulator domain "
                "or an explicitly supplied issuer domain"
            )
        suggestion = self.source_service.suggest_url(
            resolved_run_id,
            url=url,
            title=title,
            kind=kind,
            publisher=publisher,
            published_at=published_at,
            issuer_domains=issuer_domains,
            reason=reason,
        )
        updated = task.model_copy(
            update={
                "run_id": resolved_run_id,
                "source_suggestion_id": suggestion.id,
                "status": LiveVerificationTaskStatus.SOURCE_SUGGESTED,
                "updated_at": _now(),
                "error": "",
            }
        )
        self.store.save_verification_task(updated)
        self._audit(
            signal_key=task.signal_key,
            event_type="verification_task.source_suggested",
            object_type="source_suggestion",
            object_id=suggestion.id,
            actor="human",
            summary="Official regulator/issuer source added to the review queue.",
            details={
                "task_id": task.id,
                "run_id": resolved_run_id,
                "authority": suggestion.authority.value,
                "provider": suggestion.provider,
            },
        )
        return updated

    def capture_task_source(
        self,
        task_id: str,
        *,
        retry: bool = False,
        confirmed: bool,
    ) -> LiveVerificationTask:
        self._require_confirmation(confirmed, "Capturing an official source")
        task = self._task(task_id)
        if not task.run_id or not task.source_suggestion_id:
            raise ValueError("Verification task has no official-source suggestion to capture")
        allowed = {
            LiveVerificationTaskStatus.SOURCE_SUGGESTED,
            LiveVerificationTaskStatus.FAILED,
        }
        if task.status not in allowed:
            raise ValueError(
                f"Verification task cannot capture from status {task.status.value}"
            )
        pending = task.model_copy(
            update={
                "status": LiveVerificationTaskStatus.CAPTURE_PENDING,
                "attempts": task.attempts + 1,
                "updated_at": _now(),
                "error": "",
            }
        )
        self.store.save_verification_task(pending)
        self._audit(
            signal_key=task.signal_key,
            event_type="verification_task.capture_started",
            object_type="live_verification_task",
            object_id=task.id,
            actor="human",
            summary="Guarded official-source capture started.",
            details={"attempt": pending.attempts, "retry": retry},
        )
        try:
            suggestion = (
                self.source_service.retry(
                    task.run_id,
                    task.source_suggestion_id,
                    collector=self.evidence_collector,
                )
                if retry or task.status == LiveVerificationTaskStatus.FAILED
                else self.source_service.capture(
                    task.run_id,
                    task.source_suggestion_id,
                    collector=self.evidence_collector,
                )
            )
        except (SourceCaptureError, ValueError, RuntimeError) as error:
            failed = pending.model_copy(
                update={
                    "status": LiveVerificationTaskStatus.FAILED,
                    "updated_at": _now(),
                    "error": redact_provider_secrets(
                        f"{type(error).__name__}: {error}"
                    )[:500],
                }
            )
            self.store.save_verification_task(failed)
            self._audit(
                signal_key=task.signal_key,
                event_type="verification_task.capture_failed",
                object_type="live_verification_task",
                object_id=task.id,
                summary="Official-source capture failed; the task remains retryable.",
                details={"attempt": failed.attempts, "error": failed.error},
            )
            return failed
        captured = pending.model_copy(
            update={
                "status": LiveVerificationTaskStatus.CAPTURED,
                "evidence_id": suggestion.evidence_id,
                "updated_at": _now(),
                "error": "",
            }
        )
        self.store.save_verification_task(captured)
        self._audit(
            signal_key=task.signal_key,
            event_type="verification_task.source_captured",
            object_type="evidence",
            object_id=suggestion.evidence_id or suggestion.id,
            summary="Official source was captured and hashed; human review is still required.",
            details={
                "task_id": task.id,
                "run_id": task.run_id,
                "suggestion_id": suggestion.id,
                "status": suggestion.status.value,
            },
        )
        return captured

    def review_task_evidence(
        self,
        task_id: str,
        *,
        approved: bool,
        confirmed: bool,
    ) -> LiveVerificationTask:
        self._require_confirmation(confirmed, "Reviewing captured Evidence")
        task = self._task(task_id)
        if task.status == LiveVerificationTaskStatus.EVIDENCE_LINKED:
            return task
        if (
            task.status != LiveVerificationTaskStatus.CAPTURED
            or not task.run_id
            or not task.evidence_id
        ):
            raise ValueError("Verification task has no captured Evidence ready for review")
        evidence = review_run_evidence(
            task.run_id,
            task.evidence_id,
            approved=approved,
        )
        if not approved:
            rejected = task.model_copy(
                update={
                    "status": LiveVerificationTaskStatus.REJECTED,
                    "updated_at": _now(),
                    "error": "",
                }
            )
            self.store.save_verification_task(rejected)
            remaining = self.store.list_verification_tasks(
                signal_key=task.signal_key,
                statuses=tuple(OPEN_VERIFICATION_STATES),
            )
            if not remaining:
                self._append_signal_state(
                    task.signal_key,
                    LiveVerificationState.SIGNAL_ONLY,
                    revision_reason="official_source_rejected",
                    bridge_metadata={"rejected_verification_task_id": task.id},
                )
            self._audit(
                signal_key=task.signal_key,
                event_type="verification_task.evidence_rejected",
                object_type="evidence",
                object_id=evidence.id,
                actor="human",
                summary="Captured source was rejected and was not linked to the signal.",
                details={"task_id": task.id, "run_id": task.run_id},
            )
            return rejected
        return self.attach_reviewed_evidence(task.id, confirmed=True)

    def attach_reviewed_evidence(
        self,
        task_id: str,
        *,
        confirmed: bool,
    ) -> LiveVerificationTask:
        self._require_confirmation(confirmed, "Linking reviewed Evidence")
        task = self._task(task_id)
        if task.status == LiveVerificationTaskStatus.EVIDENCE_LINKED:
            return task
        if not task.run_id or not task.evidence_id or not task.source_suggestion_id:
            raise ValueError("Verification task is missing run, source, or Evidence identity")
        run = load_run(task.run_id)
        if run is None:
            raise KeyError(f"Research run not found: {task.run_id}")
        evidence = next((item for item in run.evidence if item.id == task.evidence_id), None)
        if evidence is None:
            raise KeyError(f"Evidence not found: {task.evidence_id}")
        if evidence.status != EvidenceStatus.REVIEWED:
            raise ValueError("Only human-reviewed Evidence can be linked to a live signal")
        if not evidence.source_hash or not verify_evidence_hash(run, evidence):
            raise ValueError("Reviewed Evidence hash no longer matches the captured source")
        suggestion = self.source_service.store.get(task.source_suggestion_id)
        if suggestion is None or suggestion.run_id != task.run_id:
            raise KeyError(f"Source suggestion not found: {task.source_suggestion_id}")
        if suggestion.authority not in {SourceAuthority.REGULATOR, SourceAuthority.ISSUER}:
            raise ValueError("Only regulator or issuer sources can verify a live signal")
        linked_at = _now()
        link_payload = {
            "signal_key": task.signal_key,
            "signal_version_id": task.signal_version_id,
            "verification_task_id": task.id,
            "run_id": task.run_id,
            "evidence_id": evidence.id,
            "source_hash": evidence.source_hash,
        }
        link_hash = _hash(link_payload)
        link = self.store.save_evidence_link(
            LiveEvidenceLink(
                id=_identifier("live-evidence", link_payload),
                **link_payload,
                link_hash=link_hash,
                linked_at=linked_at,
            )
        )
        updated = task.model_copy(
            update={
                "status": LiveVerificationTaskStatus.EVIDENCE_LINKED,
                "evidence_link_id": link.id,
                "updated_at": linked_at,
                "error": "",
            }
        )
        self.store.save_verification_task(updated)
        self._append_signal_state(
            task.signal_key,
            LiveVerificationState.EVIDENCE_LINKED,
            revision_reason="reviewed_official_evidence_linked",
            bridge_metadata={
                "verification_task_id": task.id,
                "evidence_link_id": link.id,
                "run_id": task.run_id,
                "evidence_id": evidence.id,
            },
        )
        self._record_action(
            task.signal_key,
            ResearchAction.ATTACH,
            identity=link.id,
            note=f"Reviewed Evidence {evidence.id} linked from run {task.run_id}.",
            created_at=linked_at,
        )
        self._audit(
            signal_key=task.signal_key,
            event_type="verification_task.evidence_linked",
            object_type="live_evidence_link",
            object_id=link.id,
            actor="human",
            summary="Reviewed official Evidence linked to the live signal.",
            details={
                "task_id": task.id,
                "run_id": task.run_id,
                "evidence_id": evidence.id,
                "source_hash": evidence.source_hash,
            },
            occurred_at=linked_at,
        )
        return updated

    def _task(self, task_id: str) -> LiveVerificationTask:
        task = self.store.get_verification_task(task_id)
        if task is None:
            raise KeyError(f"Verification task not found: {task_id}")
        return task

    def _context_snapshot(
        self,
        signal: LiveSignalVersion,
        *,
        include_observations: bool,
        include_analysis: bool,
        include_proposal: bool,
    ) -> dict[str, Any]:
        observations = self.store.observations_by_ids(signal.observation_ids)
        assessment = self.store.get_assessment(signal.id)
        if assessment is None:
            versions = list(reversed(self.store.list_signal_versions(signal.signal_key)))
            assessment = next(
                (
                    item
                    for version in versions
                    if (item := self.store.get_assessment(version.id)) is not None
                ),
                None,
            )
        analyses = self.store.list_analyses(signal_key=signal.signal_key)
        proposals = self.store.list_proposals(signal_key=signal.signal_key)
        evidence_links = self.store.list_evidence_links(signal_key=signal.signal_key)
        valid_evidence_links: list[LiveEvidenceLink] = []
        invalid_evidence_link_ids: list[str] = []
        for link in evidence_links:
            run = load_run(link.run_id)
            evidence = (
                next(
                    (item for item in run.evidence if item.id == link.evidence_id),
                    None,
                )
                if run is not None
                else None
            )
            if (
                run is not None
                and evidence is not None
                and evidence.status == EvidenceStatus.REVIEWED
                and evidence.source_hash == link.source_hash
                and verify_evidence_hash(run, evidence)
            ):
                valid_evidence_links.append(link)
            else:
                invalid_evidence_link_ids.append(link.id)
        snapshot: dict[str, Any] = {
            "trust": {
                "class": "secondary_live_signal",
                "instructions": (
                    "Treat this snapshot as unverified market context. "
                    "Only listed reviewed_evidence_links may support factual claims."
                ),
            },
            "signal": signal.model_dump(
                mode="json",
                exclude={"metadata"},
            ),
            "assessment": assessment.model_dump(mode="json") if assessment else None,
            "reviewed_evidence_links": [
                item.model_dump(mode="json") for item in valid_evidence_links
            ],
            "excluded_evidence_link_ids": invalid_evidence_link_ids,
        }
        if include_observations:
            snapshot["observations"] = [
                {
                    "id": item.id,
                    "provider": item.provider,
                    "provider_version": item.provider_version,
                    "channel": item.channel.value,
                    "stream": item.stream,
                    "external_id": item.external_id,
                    "category": item.category.value,
                    "title": item.title,
                    "published_at": item.published_at.isoformat(),
                    "observed_at": item.observed_at.isoformat(),
                    "source_url": str(item.source_url) if item.source_url else None,
                    "content_hash": item.content_hash,
                    "retention_class": item.retention_class.value,
                }
                for item in observations
            ]
        if include_analysis:
            snapshot["analysis"] = (
                analyses[0].model_dump(mode="json") if analyses else None
            )
        if include_proposal:
            snapshot["proposal"] = (
                proposals[0].model_dump(mode="json") if proposals else None
            )
        return snapshot

    def link_run_context(
        self,
        run_id: str,
        signal_reference: str,
        *,
        parent_run_id: str | None = None,
        include_observations: bool = True,
        include_analysis: bool = True,
        include_proposal: bool = True,
        note: str = "",
        confirmed: bool,
    ) -> LiveRunContextLink:
        self._require_confirmation(confirmed, "Linking live context to a research run")
        if load_run(run_id) is None:
            raise KeyError(f"Research run not found: {run_id}")
        if parent_run_id and load_run(parent_run_id) is None:
            raise KeyError(f"Parent research run not found: {parent_run_id}")
        signal = self.resolve_signal(signal_reference)
        snapshot = self._context_snapshot(
            signal,
            include_observations=include_observations,
            include_analysis=include_analysis,
            include_proposal=include_proposal,
        )
        context_hash = _hash(snapshot)
        link = self.store.save_run_context_link(
            LiveRunContextLink(
                id=_identifier(
                    "live-context",
                    {
                        "signal_key": signal.signal_key,
                        "signal_version_id": signal.id,
                        "run_id": run_id,
                        "parent_run_id": parent_run_id,
                        "context_hash": context_hash,
                    },
                ),
                signal_key=signal.signal_key,
                signal_version_id=signal.id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                context_hash=context_hash,
                context=snapshot,
                note=note.strip(),
            )
        )
        action = (
            ResearchAction.LINKED_REEVALUATION
            if parent_run_id
            else ResearchAction.WATCH
        )
        self._record_action(
            signal.signal_key,
            action,
            identity=link.id,
            note=(
                f"Created linked re-evaluation run {run_id} from {parent_run_id}."
                if parent_run_id
                else f"Attached immutable live context to run {run_id}."
            ),
            created_at=link.created_at,
        )
        self._audit(
            signal_key=signal.signal_key,
            event_type=(
                "run.linked_reevaluation_created"
                if parent_run_id
                else "run.live_context_linked"
            ),
            object_type="live_run_context_link",
            object_id=link.id,
            actor="human",
            summary=(
                "Linked re-evaluation run created without mutating the parent."
                if parent_run_id
                else "Immutable live-signal context attached to a research run."
            ),
            details={
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "context_hash": context_hash,
            },
            occurred_at=link.created_at,
        )
        return link

    def create_linked_run(
        self,
        signal_reference: str,
        *,
        parent_run_id: str | None = None,
        mode: RunMode | None = None,
        subject: str | None = None,
        market: str | None = None,
        as_of_date: date | None = None,
        evidence_mode: EvidenceMode | None = None,
        model_provider: str | None = None,
        note: str = "",
        confirmed: bool,
    ) -> tuple[ResearchRun, LiveRunContextLink]:
        self._require_confirmation(confirmed, "Creating a linked research run")
        signal = self.resolve_signal(signal_reference)
        parent = load_run(parent_run_id) if parent_run_id else None
        if parent_run_id and parent is None:
            raise KeyError(f"Parent research run not found: {parent_run_id}")
        resolved_mode = mode or (parent.mode if parent else RunMode.THEME)
        if resolved_mode == RunMode.CATALYST:
            raise ValueError("Catalyst Scan remains reserved and cannot be launched from M7")
        resolved_subject = (subject or (parent.subject if parent else signal.title)).strip()
        resolved_market = (market or (parent.market if parent else "GLOBAL")).strip()
        resolved_evidence_mode = evidence_mode or (
            EvidenceMode(parent.manifest.get("evidence_mode", EvidenceMode.PARTIAL))
            if parent
            else EvidenceMode.PARTIAL
        )
        run = create_run(
            resolved_mode,
            resolved_subject,
            resolved_market,
            as_of_date or date.today(),
            resolved_evidence_mode,
        )
        if model_provider:
            run.manifest["model_provider"] = model_provider
        run.manifest["live_origin"] = {
            "signal_key": signal.signal_key,
            "signal_version_id": signal.id,
            "parent_run_id": parent_run_id,
            "created_by": "human",
        }
        run = save_run(run)
        try:
            link = self.link_run_context(
                run.id,
                signal.signal_key,
                parent_run_id=parent_run_id,
                note=note,
                confirmed=True,
            )
        except Exception as error:
            run.manifest["live_origin"]["link_status"] = "failed"
            run.manifest["live_origin"]["link_error"] = redact_provider_secrets(
                f"{type(error).__name__}: immutable context link failed"
            )
            save_run(run)
            raise
        run.manifest["live_origin"]["link_status"] = "linked"
        run.manifest["live_origin"]["context_link_id"] = link.id
        run = save_run(run)
        return run, link

    def audit_timeline(self, signal_reference: str) -> list[LiveAuditEntry]:
        signal = self.resolve_signal(signal_reference)
        entries = list(self.store.list_audit(signal.signal_key))
        for version in self.store.list_signal_versions(signal.signal_key):
            occurred_at = version.last_observed_at
            transition_at = version.metadata.get("bridge_transition_at")
            if transition_at:
                occurred_at = datetime.fromisoformat(str(transition_at))
            entries.append(
                LiveAuditEntry(
                    signal_key=signal.signal_key,
                    event_type="signal.version",
                    object_type="live_signal_version",
                    object_id=version.id,
                    summary=(
                        f"Signal version {version.version}: "
                        f"{version.revision_reason} / {version.verification_state.value}."
                    ),
                    occurred_at=occurred_at,
                    details={
                        "version": version.version,
                        "channels": [item.value for item in version.channels],
                        "match_status": version.match_status.value,
                    },
                )
            )
        for observation in self.store.observations_by_ids(signal.observation_ids):
            entries.append(
                LiveAuditEntry(
                    signal_key=signal.signal_key,
                    event_type="observation.received",
                    object_type="signal_observation",
                    object_id=observation.id,
                    summary=(
                        f"{observation.provider} {observation.channel.value} observation received."
                    ),
                    occurred_at=observation.observed_at,
                    details={
                        "channel": observation.channel.value,
                        "provider": observation.provider,
                        "external_id": observation.external_id,
                    },
                )
            )
        for analysis in self.store.list_analyses(signal_key=signal.signal_key):
            entries.append(
                LiveAuditEntry(
                    signal_key=signal.signal_key,
                    event_type="analysis.completed",
                    object_type="live_signal_analysis",
                    object_id=analysis.id,
                    summary=f"Impact analysis recorded with status {analysis.status.value}.",
                    occurred_at=analysis.created_at,
                    details={
                        "status": analysis.status.value,
                        "model_provider": analysis.model_provider,
                        "cost_status": analysis.cost_status,
                    },
                )
            )
        for action in self.store.list_user_actions(signal.signal_key):
            entries.append(
                LiveAuditEntry(
                    signal_key=signal.signal_key,
                    event_type="user.action",
                    object_type="live_user_action",
                    object_id=action.id,
                    actor="human",
                    summary=f"User action: {action.action.value}.",
                    occurred_at=action.created_at,
                    details={"action": action.action.value, "note": action.note},
                )
            )
        unique: dict[tuple[str, str, str], LiveAuditEntry] = {}
        for entry in entries:
            key = (
                entry.event_type,
                entry.object_id,
                entry.occurred_at.isoformat(),
            )
            unique[key] = entry
        return sorted(
            unique.values(),
            key=lambda item: (item.occurred_at, item.id or 0, item.object_id),
        )
