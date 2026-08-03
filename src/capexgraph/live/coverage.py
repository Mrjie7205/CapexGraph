from __future__ import annotations

import math

from capexgraph.domain import (
    LiveChannel,
    LiveCoverageMetrics,
    LiveMatchStatus,
    LiveSignalVersion,
    SignalObservation,
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    fraction = position - lower
    return round(
        ordered[lower] * (1 - fraction) + ordered[upper] * fraction,
        3,
    )


def calculate_live_coverage(
    signals: list[LiveSignalVersion],
    observations: list[SignalObservation],
) -> LiveCoverageMetrics:
    by_id = {item.id: item for item in observations}
    delays: list[float] = []
    freshest: dict[str, object] = {
        LiveChannel.MCP.value: None,
        LiveChannel.WEBSOCKET.value: None,
        LiveChannel.FIXTURE.value: None,
    }
    for observation in observations:
        key = observation.channel.value
        current = freshest[key]
        if current is None or observation.observed_at > current:
            freshest[key] = observation.observed_at
    for signal in signals:
        arrivals: dict[LiveChannel, object] = {}
        for observation_id in signal.observation_ids:
            observation = by_id.get(observation_id)
            if observation is None:
                continue
            current = arrivals.get(observation.channel)
            if current is None or observation.observed_at < current:
                arrivals[observation.channel] = observation.observed_at
        if LiveChannel.MCP in arrivals and LiveChannel.WEBSOCKET in arrivals:
            delays.append(
                abs(
                    (
                        arrivals[LiveChannel.MCP]
                        - arrivals[LiveChannel.WEBSOCKET]
                    ).total_seconds()
                )
            )
    total = len(signals)
    matched = sum(item.match_status == LiveMatchStatus.MATCHED for item in signals)
    divergent = sum(
        item.match_status == LiveMatchStatus.DIVERGENT for item in signals
    )
    mcp_only = sum(item.channels == [LiveChannel.MCP] for item in signals)
    websocket_only = sum(
        item.channels == [LiveChannel.WEBSOCKET] for item in signals
    )
    fixture_only = sum(item.channels == [LiveChannel.FIXTURE] for item in signals)
    overlap = sum(
        LiveChannel.MCP in item.channels and LiveChannel.WEBSOCKET in item.channels
        for item in signals
    )
    return LiveCoverageMetrics(
        total_signals=total,
        matched=matched,
        divergent=divergent,
        mcp_only=mcp_only,
        websocket_only=websocket_only,
        fixture_only=fixture_only,
        overlap_ratio=round(overlap / total, 4) if total else 0,
        delivery_delay_p50_seconds=_percentile(delays, 0.5),
        delivery_delay_p95_seconds=_percentile(delays, 0.95),
        freshest_by_channel=freshest,
    )
