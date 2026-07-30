"""Provider-neutral live-signal contracts, fixtures, persistence, and ingestion."""

from capexgraph.live.analysis import LiveImpactAnalyzer, LiveImpactOutput
from capexgraph.live.base import (
    Clock,
    LiveEventBatch,
    LiveEventSource,
    LiveSourceDescriptor,
    SystemClock,
)
from capexgraph.live.bridge import LiveResearchBridge
from capexgraph.live.config import LiveProviderSettings
from capexgraph.live.coverage import calculate_live_coverage
from capexgraph.live.diagnostics import build_live_diagnostics
from capexgraph.live.fixture import (
    FrozenClock,
    FrozenEventFeed,
    load_frozen_dual_channel_feeds,
)
from capexgraph.live.mcp import (
    AdaptivePollPolicy,
    Jin10McpClient,
    Jin10McpSource,
)
from capexgraph.live.rules import LiveRuleEngine
from capexgraph.live.runtime import (
    LiveGatewayRuntime,
    get_live_runtime,
    reload_live_runtime,
)
from capexgraph.live.service import LiveIngestionResult, LiveSignalService
from capexgraph.live.soak import LiveSoakRunner
from capexgraph.live.store import LiveSignalStore
from capexgraph.live.websocket import (
    Jin10WebSocketCodec,
    Jin10WebSocketSource,
    Jin10WebSocketWorker,
)

__all__ = [
    "AdaptivePollPolicy",
    "Clock",
    "FrozenClock",
    "FrozenEventFeed",
    "Jin10McpClient",
    "Jin10McpSource",
    "Jin10WebSocketCodec",
    "Jin10WebSocketSource",
    "Jin10WebSocketWorker",
    "LiveEventBatch",
    "LiveEventSource",
    "LiveGatewayRuntime",
    "LiveImpactAnalyzer",
    "LiveImpactOutput",
    "LiveIngestionResult",
    "LiveProviderSettings",
    "LiveResearchBridge",
    "LiveRuleEngine",
    "LiveSignalService",
    "LiveSignalStore",
    "LiveSoakRunner",
    "LiveSourceDescriptor",
    "SystemClock",
    "calculate_live_coverage",
    "build_live_diagnostics",
    "get_live_runtime",
    "reload_live_runtime",
    "load_frozen_dual_channel_feeds",
]
