from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from capexgraph.domain import (
    PipelineStep,
    ResearchRun,
    RunStatus,
    StepCheckpoint,
    StepStatus,
)
from capexgraph.runtime.artifacts import atomic_write_text
from capexgraph.runtime.store import RunStore, runs_dir

StepHandler = Callable[[ResearchRun, PipelineStep], dict[str, Any]]


def scaffold_handler(run: ResearchRun, step: PipelineStep) -> dict[str, Any]:
    """A deterministic M2 handler proving execution semantics without fake research."""
    return {
        "message": f"Runtime checkpoint completed for {step.key}",
        "runtime_only": True,
        "subject": run.subject,
    }


class WorkflowExecutor:
    def __init__(
        self,
        *,
        store: RunStore | None = None,
        handlers: dict[str, StepHandler] | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.store = store or RunStore()
        self.handlers = handlers or {}
        self.max_attempts = max(1, max_attempts)

    def execute(
        self,
        run_id: str,
        *,
        until: str | None = None,
        retry_failed: bool = False,
    ) -> ResearchRun:
        run = self.store.load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        if run.status == RunStatus.CANCELLED:
            raise ValueError("Cancelled runs cannot be executed")
        if run.status == RunStatus.COMPLETED:
            return run
        if until is not None and until not in {step.key for step in run.pipeline}:
            raise ValueError(f"Unknown workflow step: {until}")

        if retry_failed:
            for step in run.pipeline:
                if step.status == StepStatus.FAILED:
                    step.status = StepStatus.PENDING
                    step.error = ""

        run.status = RunStatus.RUNNING
        self._persist(run)

        for step in run.pipeline:
            if step.status == StepStatus.COMPLETED:
                if until == step.key:
                    run.status = RunStatus.NEEDS_REVIEW
                    return self._persist(run)
                continue

            attempts_this_execution = 0
            while attempts_this_execution < self.max_attempts:
                attempts_this_execution += 1
                step.attempts += 1
                step.status = StepStatus.RUNNING
                step.started_at = datetime.now(UTC)
                step.completed_at = None
                step.error = ""
                self._checkpoint(run, step)
                self._persist(run)

                handler = self.handlers.get(step.key, scaffold_handler)
                try:
                    output = handler(run, step) or {}
                except Exception as error:  # noqa: BLE001 - errors become checkpoint state
                    step.status = StepStatus.FAILED
                    step.error = f"{type(error).__name__}: {error}"
                    step.message = "Step execution failed"
                    self._checkpoint(run, step, error=step.error)
                    self._persist(run)
                    if attempts_this_execution >= self.max_attempts:
                        run.status = RunStatus.FAILED
                        return self._persist(run)
                    step.status = StepStatus.PENDING
                    continue

                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(UTC)
                step.message = str(output.get("message", "Step completed"))
                self._checkpoint(run, step, output=output)
                self._persist(run)
                break

            if until == step.key:
                run.status = RunStatus.NEEDS_REVIEW
                return self._persist(run)

        run.status = RunStatus.NEEDS_REVIEW
        return self._persist(run)

    def _persist(self, run: ResearchRun) -> ResearchRun:
        run.updated_at = datetime.now(UTC)
        self.store.save_run(run)
        run_dir = runs_dir() / run.id
        atomic_write_text(run_dir / "state.json", run.model_dump_json(indent=2))
        return run

    def _checkpoint(
        self,
        run: ResearchRun,
        step: PipelineStep,
        *,
        output: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        checkpoint = StepCheckpoint(
            run_id=run.id,
            step_key=step.key,
            status=step.status,
            attempt=step.attempts,
            started_at=step.started_at,
            completed_at=step.completed_at,
            message=step.message,
            error=error,
            output=output or {},
        )
        self.store.save_checkpoint(checkpoint)
        checkpoint_dir = runs_dir() / run.id / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self._safe_checkpoint_path(checkpoint_dir, step.key)
        atomic_write_text(
            checkpoint_path,
            json.dumps(checkpoint.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _safe_checkpoint_path(checkpoint_dir: Path, step_key: str) -> Path:
        safe_key = "".join(
            character
            for character in step_key
            if character.isalnum() or character in "-_"
        )
        if not safe_key:
            raise ValueError("Invalid checkpoint step key")
        return checkpoint_dir / f"{safe_key}.json"
