from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from capexgraph.domain import (
    DataQualityStatus,
    MainlineAssessment,
    MainlinePolicy,
    MainlineState,
    MainlineStateEvent,
    MonitorJob,
    MonitorJobStatus,
    ProposalHumanStatus,
    ThemeDailyMetric,
    ThemeResearchProposal,
)
from capexgraph.monitoring.metrics import ThemeMetricService
from capexgraph.monitoring.store import MainlineStore
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.themes.service import ThemeRegistryService


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def conservative_experimental_policy() -> MainlinePolicy:
    semantic = {
        "name": "conservative-mainline",
        "version": 1,
        "effective_from": "2026-08-03",
        "weights": {
            "relative_strength": 0.25,
            "breadth": 0.20,
            "participation": 0.20,
            "persistence": 0.20,
            "stability": 0.10,
            "cohesion": 0.05,
        },
        "thresholds": {"confirmed": 70, "emerging": 58, "fragile": 48},
        "min_coverage_ratio": 0.60,
        "min_sample_count": 2,
        "experimental": True,
    }
    policy_hash = _hash(semantic)
    return MainlinePolicy(
        id=f"mainline-policy-{policy_hash[:20]}",
        name=semantic["name"],
        version=semantic["version"],
        effective_from=date.fromisoformat(semantic["effective_from"]),
        known_at=datetime(2026, 8, 3, tzinfo=UTC),
        weights=semantic["weights"],
        thresholds=semantic["thresholds"],
        min_coverage_ratio=semantic["min_coverage_ratio"],
        min_sample_count=semantic["min_sample_count"],
        experimental=True,
        policy_hash=policy_hash,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


class MainlineService:
    def __init__(
        self,
        *,
        store: MainlineStore | None = None,
        theme_service: ThemeRegistryService | None = None,
        metric_service: ThemeMetricService | None = None,
    ) -> None:
        self.store = store or MainlineStore()
        self.theme_service = theme_service or ThemeRegistryService()
        self.metric_service = metric_service or ThemeMetricService(
            mainline_store=self.store,
            theme_store=self.theme_service.store,
        )

    def ensure_default_policy(self) -> MainlinePolicy:
        policy = conservative_experimental_policy()
        existing = self.store.get_policy(policy.id)
        return existing or self.store.save_policy(policy)

    def assess(
        self,
        metric: ThemeDailyMetric,
        *,
        policy: MainlinePolicy | None = None,
    ) -> MainlineAssessment:
        active_policy = policy or self.ensure_default_policy()
        if metric.as_of_date < active_policy.effective_from:
            raise ValueError(
                f"Policy {active_policy.id} was not effective on {metric.as_of_date.isoformat()}"
            )
        previous = self.store.latest_assessment(metric.theme_id, before=metric.as_of_date)
        blockers: list[str] = []
        if metric.coverage_ratio < active_policy.min_coverage_ratio:
            blockers.append(
                f"coverage {metric.coverage_ratio:.0%} is below "
                f"{active_policy.min_coverage_ratio:.0%}"
            )
        if metric.sample_count < active_policy.min_sample_count:
            blockers.append(
                f"sample count {metric.sample_count} is below {active_policy.min_sample_count}"
            )
        if metric.quality_status == DataQualityStatus.FAIL:
            blockers.append("market-data quality failed")

        components = {
            "relative_strength": _clamp(
                50 + (metric.relative_strength_20d or 0.0) * 250
            ),
            "breadth": (metric.breadth_above_20d or 0.0) * 100,
            "participation": (metric.positive_participation_20d or 0.0) * 100,
            "persistence": (metric.persistence_ratio or 0.0) * 100,
            "stability": _clamp(100 - (metric.annualized_volatility or 1.0) * 100),
            "cohesion": _clamp(100 - (metric.dispersion_20d or 0.2) * 500),
        }
        total_weight = sum(active_policy.weights.values())
        score = sum(
            components.get(name, 0.0) * weight
            for name, weight in active_policy.weights.items()
        ) / total_weight
        if blockers:
            state = MainlineState.INSUFFICIENT
            score_value: float | None = None
        elif (
            score >= active_policy.thresholds["confirmed"]
            and (metric.relative_strength_20d or 0.0) > 0
        ):
            state = MainlineState.CONFIRMED
            score_value = score
        elif score >= active_policy.thresholds["emerging"]:
            state = MainlineState.EMERGING
            score_value = score
        elif (
            previous is not None
            and previous.state in {MainlineState.CONFIRMED, MainlineState.EMERGING}
            and score >= active_policy.thresholds["fragile"]
        ):
            state = MainlineState.FRAGILE
            score_value = score
        elif previous is not None and previous.state in {
            MainlineState.CONFIRMED,
            MainlineState.EMERGING,
            MainlineState.FRAGILE,
        }:
            state = MainlineState.EXITED
            score_value = score
        else:
            state = MainlineState.WATCH
            score_value = score
        previous_state = previous.state if previous else None
        reasons = [
            f"20-session relative strength: {(metric.relative_strength_20d or 0):.2%}",
            f"breadth above 20-session average: {(metric.breadth_above_20d or 0):.0%}",
            f"positive participation: {(metric.positive_participation_20d or 0):.0%}",
            f"point-in-time coverage: {metric.coverage_ratio:.0%}",
        ]
        input_hash = _hash(
            {
                "metric": metric.input_hash,
                "policy": active_policy.policy_hash,
                "previous_state": previous_state,
            }
        )
        assessment = MainlineAssessment(
            id=f"mainline-assessment-{input_hash[:24]}",
            theme_id=metric.theme_id,
            metric_id=metric.id,
            policy_id=active_policy.id,
            as_of_date=metric.as_of_date,
            state=state,
            previous_state=previous_state,
            score=score_value,
            changed=previous_state != state,
            reasons=reasons,
            blockers=blockers,
            component_scores=components,
            input_hash=input_hash,
        )
        return self.store.save_assessment(assessment)

    def _record_transition(
        self,
        assessment: MainlineAssessment,
    ) -> MainlineStateEvent | None:
        if not assessment.changed:
            return None
        event = MainlineStateEvent(
            id=f"mainline-event-{assessment.id.removeprefix('mainline-assessment-')}",
            theme_id=assessment.theme_id,
            assessment_id=assessment.id,
            as_of_date=assessment.as_of_date,
            from_state=assessment.previous_state,
            to_state=assessment.state,
        )
        return self.store.save_state_event(event)

    def _propose(self, assessment: MainlineAssessment) -> ThemeResearchProposal | None:
        action: str | None = None
        if assessment.changed and assessment.state in {
            MainlineState.EMERGING,
            MainlineState.CONFIRMED,
        }:
            action = "theme_scan"
        elif assessment.changed and assessment.state in {
            MainlineState.FRAGILE,
            MainlineState.EXITED,
        }:
            action = "reevaluate_candidates"
        if action is None:
            return None
        proposal_hash = _hash(
            {"assessment_id": assessment.id, "action": action}
        )
        proposal = ThemeResearchProposal(
            id=f"theme-proposal-{proposal_hash[:24]}",
            theme_id=assessment.theme_id,
            assessment_id=assessment.id,
            action=action,
            human_status=ProposalHumanStatus.PENDING,
            auto_execute=False,
            reason=(
                f"Mainline state changed from "
                f"{assessment.previous_state.value if assessment.previous_state else 'none'} "
                f"to {assessment.state.value}; explicit confirmation is required."
            ),
        )
        return self.store.save_proposal(proposal)

    def run_daily(
        self,
        theme_id: str,
        *,
        market: str,
        as_of_date: date,
        provider: str,
        policy_id: str | None = None,
        weighting: str = "equal",
    ) -> MonitorJob:
        policy = self.store.get_policy(policy_id) if policy_id else self.ensure_default_policy()
        if policy is None:
            raise KeyError(f"Mainline policy not found: {policy_id}")
        job_hash = _hash(
            {
                "theme_id": theme_id,
                "market": market.upper(),
                "as_of_date": as_of_date,
                "policy_id": policy.id,
            }
        )
        job_id = f"monitor-job-{job_hash[:24]}"
        existing_job = self.store.get_job(job_id)
        if existing_job is not None and existing_job.status in {
            MonitorJobStatus.SUCCESS,
            MonitorJobStatus.PARTIAL,
        }:
            return existing_job
        job = MonitorJob(
            id=job_id,
            theme_id=theme_id,
            market=market.upper(),
            as_of_date=as_of_date,
            policy_id=policy.id,
            status=MonitorJobStatus.RUNNING,
            steps={
                "theme_snapshot": "pending",
                "market_metrics": "pending",
                "mainline_assessment": "pending",
                "research_proposal": "pending",
            },
            started_at=datetime.now(UTC),
        )
        self.store.save_job(job)
        try:
            snapshot = self.theme_service.snapshot(
                theme_id,
                as_of_date=as_of_date,
                market=market,
            )
            job.steps["theme_snapshot"] = "completed"
            self.store.save_job(job)
            metric = self.metric_service.calculate(
                snapshot,
                market=market,
                provider=provider,
                weighting=weighting,
            )
            job.steps["market_metrics"] = "completed"
            self.store.save_job(job)
            assessment = self.assess(metric, policy=policy)
            job.assessment_id = assessment.id
            job.steps["mainline_assessment"] = "completed"
            self._record_transition(assessment)
            proposal = self._propose(assessment)
            job.proposal_id = proposal.id if proposal else None
            job.steps["research_proposal"] = "completed" if proposal else "not_required"
            job.status = (
                MonitorJobStatus.PARTIAL
                if metric.quality_status != DataQualityStatus.PASS
                or assessment.state == MainlineState.INSUFFICIENT
                else MonitorJobStatus.SUCCESS
            )
            job.completed_at = datetime.now(UTC)
            artifact = runs_dir() / "_monitoring" / theme_id / f"{job.id}.json"
            job.artifact_path = artifact.relative_to(runs_dir()).as_posix()
            atomic_write_json(
                artifact,
                {
                    "job": job.model_dump(mode="json"),
                    "snapshot": snapshot.model_dump(mode="json"),
                    "metric": metric.model_dump(mode="json"),
                    "assessment": assessment.model_dump(mode="json"),
                    "proposal": proposal.model_dump(mode="json") if proposal else None,
                    "cost_notice": "No model call was made by the daily monitor.",
                },
            )
        except Exception as error:
            job.status = MonitorJobStatus.FAILED
            job.error = f"{type(error).__name__}: {error}"
            job.completed_at = datetime.now(UTC)
            for key, value in job.steps.items():
                if value == "pending":
                    job.steps[key] = "blocked"
                    break
            self.store.save_job(job)
            raise
        return self.store.save_job(job)

    def decide_proposal(
        self,
        proposal_id: str,
        *,
        accepted: bool,
    ) -> ThemeResearchProposal:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Theme research proposal not found: {proposal_id}")
        if proposal.human_status != ProposalHumanStatus.PENDING:
            raise ValueError("Theme research proposal has already been decided")
        proposal.human_status = (
            ProposalHumanStatus.ACCEPTED if accepted else ProposalHumanStatus.REJECTED
        )
        return self.store.save_proposal(proposal)

    def run_batch(
        self,
        *,
        market: str,
        as_of_date: date,
        provider: str,
        theme_ids: list[str] | None = None,
        weighting: str = "equal",
    ) -> list[MonitorJob]:
        """Run every eligible theme independently so one failure cannot hide the rest."""

        normalized_market = market.upper()
        selected = set(theme_ids or [])
        definitions = [
            item
            for item in self.theme_service.list_definitions()
            if normalized_market in item.markets
            and (not selected or item.theme_id in selected)
        ]
        jobs: list[MonitorJob] = []
        for definition in definitions:
            try:
                jobs.append(
                    self.run_daily(
                        definition.theme_id,
                        market=normalized_market,
                        as_of_date=as_of_date,
                        provider=provider,
                        weighting=weighting,
                    )
                )
            except Exception:
                failed = next(
                    (
                        item
                        for item in self.store.list_jobs()
                        if item.theme_id == definition.theme_id
                        and item.market == normalized_market
                        and item.as_of_date == as_of_date
                    ),
                    None,
                )
                if failed is not None:
                    jobs.append(failed)
        return jobs
