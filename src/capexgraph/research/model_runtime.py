from __future__ import annotations

from datetime import UTC, datetime

from capexgraph.domain import ResearchRun, RunMode
from capexgraph.providers import (
    ProviderConfigurationError,
    ProviderName,
    ResearchModel,
    ResearchProviderError,
    redact_provider_secrets,
)
from capexgraph.workflows import load_run, save_run

MODEL_PROVIDER_CHOICES = "fixture, codex_subscription, or openai"


def _latest_run(run: ResearchRun) -> ResearchRun:
    return load_run(run.id) or run


def assert_provider_change_allowed(
    run: ResearchRun,
    requested: ProviderName | str | None,
) -> None:
    if requested is None:
        return
    run = _latest_run(run)
    requested_name = ProviderName(requested).value
    persisted = run.manifest.get("model_provider")
    has_started = any(step.attempts > 0 for step in run.pipeline)
    if has_started and persisted and requested_name != persisted:
        raise ValueError(
            f"Run {run.id} is locked to model provider {persisted}; "
            "create a new run to change provider."
        )


def select_run_provider(
    run: ResearchRun,
    requested: ProviderName | str | None,
) -> ProviderName:
    original = run
    run = _latest_run(run)
    if run.mode not in {RunMode.THEME, RunMode.ANCHOR}:
        raise ValueError(f"{run.mode.value} does not support a research model provider")
    assert_provider_change_allowed(run, requested)
    persisted = run.manifest.get("model_provider")
    selected_value = requested or persisted
    if not selected_value:
        raise ValueError(
            f"{run.mode.value.title()} Scan execution requires --provider "
            f"{MODEL_PROVIDER_CHOICES}"
        )
    selected = ProviderName(selected_value)
    run.manifest["model_provider"] = selected.value
    run.manifest["model_provider_locked"] = True
    run.manifest["model_provider_lock_reason"] = "execution_started"
    run.manifest.setdefault("model_provider_selected_at", datetime.now(UTC).isoformat())
    save_run(run)
    original.manifest = dict(run.manifest)
    return selected


def bind_model_identity(run: ResearchRun, model: ResearchModel) -> ResearchRun:
    original = run
    run = _latest_run(run)
    existing_model = run.manifest.get("model")
    has_started = any(step.attempts > 0 for step in run.pipeline)
    if has_started and existing_model and existing_model != model.model_name:
        raise ValueError(
            f"Run {run.id} is locked to model {existing_model}; "
            "create a new run to change model."
        )
    previous_usage = run.manifest.get("model_usage")
    previous_calls = (
        int(previous_usage.get("calls", 0))
        if isinstance(previous_usage, dict)
        and previous_usage.get("provider") == model.provider_name
        else 0
    )
    if hasattr(model, "call_count"):
        model.call_count = max(int(getattr(model, "call_count", 0)), previous_calls)
    context = dict(getattr(model, "execution_context", {}) or {})
    run.manifest.update(
        {
            "model_provider": model.provider_name,
            "model": model.model_name,
            "model_provider_details": {
                "name": model.provider_name,
                "version": getattr(model, "provider_version", "unknown"),
                "model": model.model_name,
                **context,
            },
            "model_execution_context": context,
            "model_usage": {
                "provider": model.provider_name,
                "calls": int(getattr(model, "call_count", 0)),
            },
            "evidence_policy": model.evidence_policy.value,
            "as_of_date": run.as_of_date.isoformat(),
            "report_language": (
                "zh-CN"
                if any("\u4e00" <= character <= "\u9fff" for character in run.subject)
                else "en"
            ),
        }
    )
    saved = save_run(run)
    original.manifest = dict(saved.manifest)
    return saved


def provider_setup_error(
    error: Exception,
    *,
    provider: ProviderName | str,
) -> ResearchProviderError:
    provider_name = ProviderName(provider).value
    if isinstance(error, ResearchProviderError):
        safe_detail = error.safe_message
        error_type = type(error)
        return error_type(
            f"Provider setup failed: {safe_detail}",
            provider=provider_name,
            retryable=error.retryable,
        )
    return ProviderConfigurationError(
        f"Provider setup failed: {type(error).__name__}: "
        f"{redact_provider_secrets(error)}",
        provider=provider_name,
    )


def record_model_call(run: ResearchRun, model: ResearchModel) -> None:
    run.manifest["model_usage"] = {
        "provider": model.provider_name,
        "calls": int(getattr(model, "call_count", 0)),
    }
