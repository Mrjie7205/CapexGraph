"""Research-agent workflows built on the durable run engine."""

from capexgraph.research.anchor import build_anchor_executor, build_anchor_handlers
from capexgraph.research.theme import build_executor_for_run as build_theme_executor
from capexgraph.research.theme import build_theme_handlers


def build_executor_for_run(run, *, provider=None, max_attempts=2):
    if run.mode.value == "anchor":
        return build_anchor_executor(run, provider=provider, max_attempts=max_attempts)
    return build_theme_executor(run, provider=provider, max_attempts=max_attempts)


__all__ = ["build_anchor_handlers", "build_executor_for_run", "build_theme_handlers"]
