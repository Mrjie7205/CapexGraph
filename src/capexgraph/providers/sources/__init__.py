"""Official-source discovery providers."""

from capexgraph.providers.sources.base import (
    SourceDiscoveryProvider,
    canonicalize_source_url,
    classify_source_authority,
)
from capexgraph.providers.sources.manual import ManualOfficialUrlProvider
from capexgraph.providers.sources.sec import SecEdgarSourceProvider

__all__ = [
    "ManualOfficialUrlProvider",
    "SecEdgarSourceProvider",
    "SourceDiscoveryProvider",
    "canonicalize_source_url",
    "classify_source_authority",
]
