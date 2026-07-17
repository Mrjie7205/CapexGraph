from __future__ import annotations

from capexgraph.domain import RunMode, RunStatus, StepStatus
from capexgraph.runtime import RunStore, WorkflowExecutor
from capexgraph.workflows import create_run


def test_executor_checkpoints_every_step(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "A股半导体硅片", "CN")

    completed = WorkflowExecutor().execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    assert all(step.status == StepStatus.COMPLETED for step in completed.pipeline)
    checkpoints = RunStore().list_checkpoints(run.id)
    assert len(checkpoints) == len(completed.pipeline)
    assert all(checkpoint.output["runtime_only"] is True for checkpoint in checkpoints)
    assert (tmp_path / run.id / "checkpoints" / "graph.json").is_file()


def test_executor_retries_a_transient_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "AI数据中心电力", "CN")
    calls = 0

    def flaky_handler(_run, _step):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary provider timeout")
        return {"message": "provider recovered", "runtime_only": True}

    completed = WorkflowExecutor(
        handlers={"census": flaky_handler},
        max_attempts=2,
    ).execute(run.id)

    assert completed.status == RunStatus.NEEDS_REVIEW
    census = next(step for step in completed.pipeline if step.key == "census")
    assert census.status == StepStatus.COMPLETED
    assert census.attempts == 2
    assert calls == 2


def test_resume_skips_completed_checkpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.ANCHOR, "兆易创新", "CN")
    intake_calls = 0

    def intake_handler(_run, _step):
        nonlocal intake_calls
        intake_calls += 1
        return {"message": "identity resolved"}

    def failing_handler(_run, _step):
        raise RuntimeError("source unavailable")

    failed = WorkflowExecutor(
        handlers={"intake": intake_handler, "cause": failing_handler},
        max_attempts=1,
    ).execute(run.id)
    assert failed.status == RunStatus.FAILED
    assert intake_calls == 1

    resumed = WorkflowExecutor(
        handlers={"intake": intake_handler},
        max_attempts=1,
    ).execute(run.id, retry_failed=True)

    assert resumed.status == RunStatus.NEEDS_REVIEW
    assert intake_calls == 1
    assert all(step.status == StepStatus.COMPLETED for step in resumed.pipeline)


def test_executor_can_stop_at_a_named_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "先进封装", "CN")

    paused = WorkflowExecutor().execute(run.id, until="graph")

    assert paused.status == RunStatus.NEEDS_REVIEW
    graph_index = next(index for index, step in enumerate(paused.pipeline) if step.key == "graph")
    assert all(step.status == StepStatus.COMPLETED for step in paused.pipeline[: graph_index + 1])
    assert all(step.status == StepStatus.PENDING for step in paused.pipeline[graph_index + 1 :])


def test_executor_rejects_an_unknown_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "先进封装", "CN")

    try:
        WorkflowExecutor().execute(run.id, until="typo-step")
    except ValueError as error:
        assert "Unknown workflow step" in str(error)
    else:
        raise AssertionError("Unknown checkpoint should fail before execution")
