from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from capexgraph.domain import (
    LiveAlertDelivery,
    LiveChannel,
    LiveDeadLetter,
    LiveMatchStatus,
    LiveProviderCheckpoint,
    LiveProviderHealth,
    LiveSignalVersion,
    SignalObservation,
)
from capexgraph.live.base import LiveEventBatch, LiveEventSource
from capexgraph.live.rules import LiveRuleEngine
from capexgraph.live.store import LiveSignalStore
from capexgraph.runtime import RunStore


class LiveIngestionResult(BaseModel):
    batch: LiveEventBatch
    signals: list[LiveSignalVersion] = Field(default_factory=list)
    created_versions: int = Field(ge=0)
    duplicate_observations: int = Field(ge=0)


class LiveSignalService:
    def __init__(self, store: LiveSignalStore | None = None) -> None:
        self.store = store or LiveSignalStore()

    def _graph_node_aliases(self) -> dict[str, list[str]]:
        aliases: dict[str, list[str]] = {}
        for run in RunStore(self.store.db_path).list_runs(limit=500):
            for node in run.nodes:
                aliases.setdefault(node.id, [])
                aliases[node.id].extend(
                    item
                    for item in (node.label, node.ticker or "")
                    if item and item not in aliases[node.id]
                )
        return aliases

    @staticmethod
    def _signal_key(observation: SignalObservation) -> str:
        digest = hashlib.sha256(observation.event_key.encode("utf-8")).hexdigest()[:24]
        return f"live:{digest}"

    @staticmethod
    def _version_hash(payload: dict[str, Any]) -> str:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def ingest_observation(
        self,
        observation: SignalObservation,
    ) -> tuple[LiveSignalVersion, bool]:
        existing_observation = self.store.get_observation(observation.id)
        if existing_observation is not None:
            existing_signal = self.store.signal_for_observation(observation.id)
            if existing_signal is not None:
                return existing_signal, False
        persisted = self.store.save_observation(observation)
        signal_key = self._signal_key(persisted)
        latest = self.store.latest_signal(signal_key)
        observation_ids = set(latest.observation_ids if latest else ())
        observation_ids.add(persisted.id)
        observations = self.store.observations_by_ids(sorted(observation_ids))
        channels = sorted({item.channel for item in observations}, key=lambda item: item.value)
        content_hashes = {item.content_hash for item in observations}
        if len(channels) == 1:
            match_status = LiveMatchStatus.SINGLE_CHANNEL
        elif len(content_hashes) == 1:
            match_status = LiveMatchStatus.MATCHED
        else:
            match_status = LiveMatchStatus.DIVERGENT
        latest_observation = max(
            observations,
            key=lambda item: (item.observed_at, item.id),
        )
        semantic = {
            "signal_key": signal_key,
            "category": latest_observation.category.value,
            "title": latest_observation.title,
            "observation_ids": sorted(observation_ids),
            "channels": [item.value for item in channels],
            "match_status": match_status.value,
            "verification_state": (
                latest.verification_state.value if latest else "signal_only"
            ),
        }
        version_hash = self._version_hash(semantic)
        if latest is not None and latest.version_hash == version_hash:
            return latest, False
        if latest is None:
            revision_reason = "first_observation"
        elif persisted.channel in latest.channels:
            revision_reason = "channel_revision_observed"
        else:
            revision_reason = "channel_observation_added"
        version = latest.version + 1 if latest else 1
        signal_id = hashlib.sha256(
            f"{signal_key}:{version_hash}".encode()
        ).hexdigest()[:24]
        signal = LiveSignalVersion(
            id=f"live-signal-{signal_id}",
            signal_key=signal_key,
            version=version,
            version_hash=version_hash,
            category=latest_observation.category,
            title=latest_observation.title,
            published_at=min(item.published_at for item in observations),
            first_observed_at=min(item.observed_at for item in observations),
            last_observed_at=max(item.observed_at for item in observations),
            observation_ids=sorted(observation_ids),
            channels=channels,
            match_status=match_status,
            verification_state=(
                latest.verification_state if latest else "signal_only"
            ),
            revision_reason=revision_reason,
            metadata={
                "observation_count": len(observations),
                "channel_count": len(channels),
                "content_variant_count": len(content_hashes),
                "category_values": sorted(
                    {item.category.value for item in observations}
                ),
            },
        )
        persisted_signal = self.store.save_signal(signal)
        settings = self.store.get_settings()
        assessment = LiveRuleEngine(
            settings,
            graph_nodes=self._graph_node_aliases(),
        ).assess(
            persisted_signal,
            observations,
        )
        if assessment.should_alert and settings.cooldown_seconds:
            cutoff = assessment.created_at - timedelta(
                seconds=settings.cooldown_seconds
            )
            normalized_title = persisted_signal.title.casefold().strip()
            duplicate_recent = any(
                alert.signal_key != persisted_signal.signal_key
                and alert.created_at >= cutoff
                and (
                    recent := self.store.latest_signal(alert.signal_key)
                ) is not None
                and recent.title.casefold().strip() == normalized_title
                for alert in self.store.list_alerts(limit=200)
            )
            if duplicate_recent:
                assessment = assessment.model_copy(
                    update={
                        "should_alert": False,
                        "rationale": [
                            *assessment.rationale,
                            "suppressed_by_title_cooldown",
                        ],
                    }
                )
        self.store.save_assessment(assessment)
        if assessment.should_alert:
            self.store.create_alert(
                LiveAlertDelivery(
                    signal_key=persisted_signal.signal_key,
                    signal_version_id=persisted_signal.id,
                    score=assessment.total_score,
                    created_at=assessment.created_at,
                    updated_at=assessment.created_at,
                )
            )
        return persisted_signal, True

    def ingest_payload(
        self,
        payload: dict[str, Any],
        *,
        provider: str,
        provider_version: str,
        channel: LiveChannel,
        stream: str,
        observed_at: datetime | None = None,
    ) -> LiveSignalVersion | None:
        normalized = {
            **payload,
            "provider": provider,
            "provider_version": provider_version,
            "channel": channel,
            "stream": stream,
            "observed_at": observed_at or payload.get("observed_at") or datetime.now(UTC),
        }
        try:
            observation = SignalObservation.model_validate(normalized)
        except ValidationError as error:
            raw = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
            payload_hash = hashlib.sha256(raw).hexdigest()
            messages = [
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors(include_input=False)
            ]
            dead_id = hashlib.sha256(
                f"{provider}:{channel.value}:{stream}:{payload_hash}".encode()
            ).hexdigest()[:24]
            self.store.save_dead_letter(
                LiveDeadLetter(
                    id=f"live-dead-{dead_id}",
                    provider=provider,
                    channel=channel,
                    stream=stream,
                    observed_at=observed_at or datetime.now(UTC),
                    payload_hash=payload_hash,
                    error="; ".join(messages),
                    metadata={"validation_error_count": len(messages)},
                )
            )
            return None
        return self.ingest_observation(observation)[0]

    def poll_source(
        self,
        source: LiveEventSource,
        *,
        limit: int = 100,
    ) -> LiveIngestionResult:
        descriptor = source.descriptor
        checkpoint = self.store.get_checkpoint(
            descriptor.provider,
            descriptor.channel,
            descriptor.stream,
        )
        try:
            batch = source.read(checkpoint, limit=limit)
        except Exception as error:
            degraded = LiveProviderCheckpoint(
                provider=descriptor.provider,
                provider_version=descriptor.provider_version,
                channel=descriptor.channel,
                stream=descriptor.stream,
                cursor=checkpoint.cursor if checkpoint else "",
                last_external_id=checkpoint.last_external_id if checkpoint else None,
                last_published_at=(
                    checkpoint.last_published_at if checkpoint else None
                ),
                last_observed_at=checkpoint.last_observed_at if checkpoint else None,
                health=LiveProviderHealth.DEGRADED,
                calls_used=checkpoint.calls_used if checkpoint else 0,
                call_budget=checkpoint.call_budget if checkpoint else None,
                budget_date=checkpoint.budget_date if checkpoint else None,
                error=f"{type(error).__name__}: source read failed",
                metadata={"source_key": descriptor.key},
            )
            self.store.save_checkpoint(degraded)
            raise

        signals: list[LiveSignalVersion] = []
        created_versions = 0
        duplicate_observations = 0
        for observation in batch.observations:
            signal, created = self.ingest_observation(observation)
            signals.append(signal)
            if created:
                created_versions += 1
            else:
                duplicate_observations += 1
        self.store.save_checkpoint(batch.checkpoint)
        return LiveIngestionResult(
            batch=batch,
            signals=signals,
            created_versions=created_versions,
            duplicate_observations=duplicate_observations,
        )
