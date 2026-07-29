from __future__ import annotations

import csv
import os
import re
from importlib.resources import files
from pathlib import Path

from capexgraph.domain import TickerIdentity


def canonical_ticker(value: str) -> str:
    ticker = value.strip().upper()
    replacements = {
        ".SS": ".SH",
        ".SHG": ".SH",
        ".SHE": ".SZ",
        ".KS": ".KO",
    }
    for old, new in replacements.items():
        if ticker.endswith(old):
            ticker = f"{ticker[:-len(old)]}{new}"
    if ticker.isdigit() and len(ticker) == 6:
        if ticker.startswith(("4", "8", "92")):
            return f"{ticker}.BJ"
        if ticker.startswith(("0", "3")):
            return f"{ticker}.SZ"
        if ticker.startswith(("5", "6", "9")):
            return f"{ticker}.SH"
    return ticker


def _read_registry(path: Path) -> list[TickerIdentity]:
    if not path.is_file():
        return []
    identities: list[TickerIdentity] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            identities.append(
                TickerIdentity(
                    ticker=canonical_ticker(row["ticker"]),
                    name=row["name"].strip(),
                    market=row["market"].strip(),
                    exchange=row["exchange"].strip(),
                    currency=row["currency"].strip(),
                    aliases=[item.strip() for item in row.get("aliases", "").split("|") if item],
                    source_url=row.get("source_url") or None,
                )
            )
    return identities


class TickerResolver:
    """Resolve canonical ticker identities without letting a model invent company names."""

    def __init__(self, extra_registry: Path | None = None) -> None:
        bundled = files("capexgraph.fixtures").joinpath("ticker_registry.csv")
        identities = _read_registry(Path(str(bundled)))
        configured = extra_registry or (
            Path(os.environ["CAPEXGRAPH_TICKER_FILE"])
            if os.getenv("CAPEXGRAPH_TICKER_FILE")
            else None
        )
        if configured:
            identities.extend(_read_registry(configured))
        self._by_ticker = {identity.ticker: identity for identity in identities}
        self._by_name: dict[str, TickerIdentity] = {}
        for identity in identities:
            for name in [identity.name, *identity.aliases]:
                self._by_name[name.strip().casefold()] = identity

    def resolve(self, query: str) -> TickerIdentity:
        ticker = canonical_ticker(query)
        if ticker in self._by_ticker:
            return self._by_ticker[ticker]
        named = self._by_name.get(query.strip().casefold())
        if named is not None:
            return named
        if ticker.endswith((".SH", ".SZ", ".BJ")) and ticker[:6].isdigit():
            exchange = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}[ticker[-2:]]
            return TickerIdentity(
                ticker=ticker,
                name=ticker,
                market="CN",
                exchange=exchange,
                currency="CNY",
            )
        if ticker.endswith((".KO", ".KQ")) and ticker[:-3].isdigit():
            return TickerIdentity(
                ticker=ticker,
                name=ticker,
                market="KR",
                exchange="KRX" if ticker.endswith(".KO") else "KOSDAQ",
                currency="KRW",
            )
        if ticker.endswith(".US") and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}\.US", ticker):
            return TickerIdentity(
                ticker=ticker,
                name=ticker,
                market="US",
                exchange="US",
                currency="USD",
            )
        if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}", ticker):
            return TickerIdentity(
                ticker=ticker,
                name=ticker,
                market="US",
                exchange="US",
                currency="USD",
            )
        raise KeyError(f"Ticker identity not found: {query}")
