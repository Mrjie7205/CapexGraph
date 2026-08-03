"""Deterministic research tools for evidence, identity, market data, and reporting."""

from importlib import import_module

from capexgraph.tools.evidence import (
    EvidenceCollector,
    EvidencePack,
    EvidenceSourceRequest,
    attach_collected_document,
    collect_evidence_for_run,
    collect_evidence_pack,
    read_run_evidence_text,
    review_run_evidence,
)
from capexgraph.tools.identity import TickerResolver

__all__ = [
    "EvidenceCollector",
    "EvidencePack",
    "EvidenceSourceRequest",
    "EodhdProvider",
    "TickerResolver",
    "YahooChartProvider",
    "attach_collected_document",
    "calculate_market_snapshot",
    "build_market_provider",
    "capture_market_snapshot",
    "collect_evidence_for_run",
    "collect_evidence_pack",
    "read_run_evidence_text",
    "review_run_evidence",
]

_MARKET_EXPORTS = {
    "EodhdProvider",
    "YahooChartProvider",
    "build_market_provider",
    "calculate_market_snapshot",
    "capture_market_snapshot",
}


def __getattr__(name: str):
    if name in _MARKET_EXPORTS:
        return getattr(import_module("capexgraph.tools.market"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
