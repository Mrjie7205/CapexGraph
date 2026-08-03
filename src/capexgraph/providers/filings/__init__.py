"""Official filing-fact provider contracts and built-in adapters."""

from capexgraph.providers.filings.base import (
    FilingFactsProvider,
    FilingFactsResult,
    FilingFactsValidationError,
)
from capexgraph.providers.filings.opendart import OpenDartFinancialFactsProvider
from capexgraph.providers.filings.sec import SecCompanyFactsProvider

__all__ = [
    "FilingFactsProvider",
    "FilingFactsResult",
    "FilingFactsValidationError",
    "OpenDartFinancialFactsProvider",
    "SecCompanyFactsProvider",
]
