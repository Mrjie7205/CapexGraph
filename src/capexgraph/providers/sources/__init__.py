"""Official-source discovery providers."""

from capexgraph.providers.sources.base import (
    SourceDiscoveryProvider,
    canonicalize_source_url,
    classify_source_authority,
)
from capexgraph.providers.sources.china import (
    BseSourceProvider,
    CninfoSourceProvider,
    SseSourceProvider,
    SzseSourceProvider,
)
from capexgraph.providers.sources.korea import KindSourceProvider, OpenDartSourceProvider
from capexgraph.providers.sources.manual import ManualOfficialUrlProvider
from capexgraph.providers.sources.registry import (
    build_source_provider,
    official_source_capabilities,
)
from capexgraph.providers.sources.sec import SecEdgarSourceProvider

__all__ = [
    "ManualOfficialUrlProvider",
    "BseSourceProvider",
    "CninfoSourceProvider",
    "KindSourceProvider",
    "OpenDartSourceProvider",
    "SecEdgarSourceProvider",
    "SseSourceProvider",
    "SourceDiscoveryProvider",
    "SzseSourceProvider",
    "build_source_provider",
    "canonicalize_source_url",
    "classify_source_authority",
    "official_source_capabilities",
]
