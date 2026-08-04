from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from capexgraph.domain import (
    EvidenceKind,
    EvidenceMode,
    EvidenceStatus,
    ResearchRun,
    SourceSuggestionStatus,
)
from capexgraph.live.store import LiveSignalStore
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.sources.store import SourceSuggestionStore
from capexgraph.tools.evidence import read_run_evidence_text, verify_evidence_hash

MAX_EVIDENCE_CHARACTERS = 24_000
MAX_SOURCE_CHARACTERS = 6_000
MAX_FINANCIAL_CHARACTERS = 12_000
MAX_LIVE_CONTEXT_CHARACTERS = 20_000


class EvidenceCoverage(BaseModel):
    mode: EvidenceMode
    evidence_total: int = 0
    captured: int = 0
    agent_reviewed: int = 0
    reviewed: int = 0
    proposed: int = 0
    rejected: int = 0
    hash_mismatches: int = 0
    suggestions_total: int = 0
    pending_reviews: int = 0
    source_failures: int = 0
    discovery_failures: int = 0
    status: str = "empty"
    strict_ready: bool = False
    autonomous_ready: bool = False
    gaps: list[str] = Field(default_factory=list)


def _read_json(run: ResearchRun, relative_path: str) -> Any:
    path = runs_dir() / run.id / relative_path
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate_evidence_coverage(run: ResearchRun) -> EvidenceCoverage:
    mode = EvidenceMode(run.manifest.get("evidence_mode", EvidenceMode.PARTIAL))
    counts = {status: 0 for status in EvidenceStatus}
    hash_mismatches = 0
    for item in run.evidence:
        counts[item.status] += 1
        if (
            item.status
            in {
                EvidenceStatus.CAPTURED,
                EvidenceStatus.AGENT_REVIEWED,
                EvidenceStatus.REVIEWED,
            }
            and item.local_path
            and not verify_evidence_hash(run, item)
        ):
            hash_mismatches += 1

    try:
        suggestions = SourceSuggestionStore().list(run.id)
    except Exception:  # noqa: BLE001 - coverage remains available if queue storage is unavailable
        suggestions = []
    pending_statuses = {
        SourceSuggestionStatus.SUGGESTED,
        SourceSuggestionStatus.SELECTED,
        SourceSuggestionStatus.CAPTURE_PENDING,
        SourceSuggestionStatus.CAPTURED,
    }
    reviewable_captured = sum(
        item.status == EvidenceStatus.CAPTURED and item.kind != EvidenceKind.MARKET_DATA
        for item in run.evidence
    )
    reviewed_claim_sources = sum(
        evidence_is_reviewed_and_unchanged(run, item)
        and item.kind != EvidenceKind.MARKET_DATA
        for item in run.evidence
    )
    agent_reviewed_claim_sources = sum(
        evidence_is_agent_reviewed_and_unchanged(run, item)
        and item.kind != EvidenceKind.MARKET_DATA
        for item in run.evidence
    )
    pending_reviews = reviewable_captured + sum(
        1
        for suggestion in suggestions
        if suggestion.status in pending_statuses and not suggestion.evidence_id
    )
    source_failures = sum(
        suggestion.status == SourceSuggestionStatus.CAPTURE_FAILED
        for suggestion in suggestions
    )
    discovery_failures = len(run.manifest.get("source_discovery_errors", []))
    reviewed = counts[EvidenceStatus.REVIEWED]
    agent_reviewed = counts[EvidenceStatus.AGENT_REVIEWED]
    captured = counts[EvidenceStatus.CAPTURED]

    gaps: list[str] = []
    if not run.evidence:
        gaps.append("No evidence has been captured for this run.")
    if reviewable_captured:
        gaps.append(f"{reviewable_captured} captured source(s) still require human review.")
    if hash_mismatches:
        gaps.append(f"{hash_mismatches} captured source hash(es) no longer match.")
    if source_failures:
        gaps.append(f"{source_failures} source capture(s) failed.")
    if discovery_failures:
        gaps.append(f"{discovery_failures} source discovery request(s) failed.")

    if reviewed_claim_sources and not hash_mismatches:
        status = "reviewed"
    elif agent_reviewed_claim_sources and not hash_mismatches:
        status = "agent_reviewed"
    elif run.evidence:
        status = "partial"
    elif suggestions:
        status = "suggestions_only"
    else:
        status = "empty"
    return EvidenceCoverage(
        mode=mode,
        evidence_total=len(run.evidence),
        captured=captured,
        agent_reviewed=agent_reviewed,
        reviewed=reviewed,
        proposed=counts[EvidenceStatus.PROPOSED],
        rejected=counts[EvidenceStatus.REJECTED],
        hash_mismatches=hash_mismatches,
        suggestions_total=len(suggestions),
        pending_reviews=pending_reviews,
        source_failures=source_failures,
        discovery_failures=discovery_failures,
        status=status,
        strict_ready=(
            reviewed_claim_sources > 0 or agent_reviewed_claim_sources > 0
        )
        and hash_mismatches == 0,
        autonomous_ready=agent_reviewed_claim_sources > 0 and hash_mismatches == 0,
        gaps=gaps,
    )


def refresh_evidence_coverage(run: ResearchRun) -> EvidenceCoverage:
    coverage = evaluate_evidence_coverage(run)
    payload = coverage.model_dump(mode="json")
    run.manifest["evidence_coverage"] = payload
    atomic_write_json(runs_dir() / run.id / "coverage.json", payload)
    return coverage


def enforce_evidence_preflight(run: ResearchRun, *, curated: bool) -> EvidenceCoverage:
    coverage = refresh_evidence_coverage(run)
    if coverage.mode == EvidenceMode.STRICT and not curated and not coverage.strict_ready:
        raise ValueError(
            "Strict evidence mode requires at least one reviewed, hash-valid source. "
            "Capture and approve an official source, then resume this run."
        )
    return coverage


def evidence_is_reviewed_and_unchanged(run: ResearchRun, item: Any) -> bool:
    return bool(
        item
        and item.status == EvidenceStatus.REVIEWED
        and item.source_hash
        and item.local_path
        and verify_evidence_hash(run, item)
    )


def evidence_is_agent_reviewed_and_unchanged(run: ResearchRun, item: Any) -> bool:
    return bool(
        item
        and item.status == EvidenceStatus.AGENT_REVIEWED
        and item.review
        and item.review.source_hash == item.source_hash
        and item.source_hash
        and item.local_path
        and verify_evidence_hash(run, item)
    )


def _evidence_context(run: ResearchRun) -> list[dict[str, Any]]:
    included: list[dict[str, Any]] = []
    used = 0
    for item in run.evidence:
        if item.status not in {
            EvidenceStatus.CAPTURED,
            EvidenceStatus.AGENT_REVIEWED,
            EvidenceStatus.REVIEWED,
        }:
            continue
        text = item.excerpt
        if item.local_path:
            try:
                text = read_run_evidence_text(run.id, item.id)
            except (KeyError, OSError, ValueError):
                text = item.excerpt
        if item.review and item.review.supporting_quotes:
            reviewed_text = "\n\n".join(item.review.supporting_quotes)
            text = f"{reviewed_text}\n\n{text}"
        remaining = MAX_EVIDENCE_CHARACTERS - used
        if remaining <= 0:
            break
        excerpt = text[: min(MAX_SOURCE_CHARACTERS, remaining)]
        used += len(excerpt)
        included.append(
            {
                "id": item.id,
                "title": item.title,
                "kind": item.kind.value,
                "status": item.status.value,
                "source_url": str(item.source_url) if item.source_url else None,
                "source_hash": item.source_hash,
                "published_at": item.published_at,
                "review": item.review.model_dump(mode="json") if item.review else None,
                "text": excerpt,
                "truncated": len(text) > len(excerpt),
            }
        )
    return included


def _financial_context(run: ResearchRun) -> list[dict[str, Any]]:
    facts_payload = _read_json(run, "financials/facts.json")
    metrics_payload = _read_json(run, "financials/metrics.json")
    items = facts_payload.get("items") or metrics_payload.get("items") or []
    if not isinstance(items, list):
        return []
    bounded: list[dict[str, Any]] = []
    used = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        serialized = json.dumps(item, ensure_ascii=False, default=str)
        if used + len(serialized) > MAX_FINANCIAL_CHARACTERS:
            break
        used += len(serialized)
        bounded.append(item)
    return bounded


def _live_context(run: ResearchRun) -> list[dict[str, Any]]:
    try:
        links = LiveSignalStore().list_run_context_links(run_id=run.id)
    except Exception:  # noqa: BLE001 - ordinary run context remains usable if bridge state fails
        return []
    bounded: list[dict[str, Any]] = []
    used = 0
    for link in reversed(links):
        raw = json.dumps(
            link.context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != link.context_hash:
            bounded.append(
                {
                    "id": link.id,
                    "signal_key": link.signal_key,
                    "context_hash": link.context_hash,
                    "integrity": "failed",
                    "context": None,
                }
            )
            continue
        serialized = raw.decode("utf-8")
        if used + len(serialized) > MAX_LIVE_CONTEXT_CHARACTERS:
            break
        used += len(serialized)
        bounded.append(
            {
                "id": link.id,
                "signal_key": link.signal_key,
                "signal_version_id": link.signal_version_id,
                "context_hash": link.context_hash,
                "integrity": "verified",
                "context": link.context,
            }
        )
    return bounded


def build_research_context(run: ResearchRun) -> dict[str, Any]:
    coverage = refresh_evidence_coverage(run)
    return {
        "evidence_coverage": coverage.model_dump(mode="json"),
        "reviewed_and_captured_sources": _evidence_context(run),
        "financial_facts": _financial_context(run),
        "immutable_live_context": _live_context(run),
    }


def apply_relationship_confidence_gate(
    run: ResearchRun,
    *,
    requested_confidence: str,
    curated: bool,
    claim_label: str,
    human_reviewed_sources: bool | None = None,
    agent_reviewed_sources: bool = False,
    reviewed_sources: bool | None = None,
) -> tuple[str, bool]:
    if human_reviewed_sources is None:
        human_reviewed_sources = bool(reviewed_sources)
    if curated or human_reviewed_sources:
        return requested_confidence, True
    if agent_reviewed_sources:
        return ("medium" if requested_confidence == "high" else requested_confidence), True
    mode = EvidenceMode(run.manifest.get("evidence_mode", EvidenceMode.PARTIAL))
    if mode == EvidenceMode.STRICT and requested_confidence in {"medium", "high"}:
        raise ValueError(
            f"Strict evidence mode blocked {claim_label}: medium/high confidence "
            "requires reviewed evidence."
        )
    return "low", False
