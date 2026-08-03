from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from capexgraph.domain import (
    CoverageLevel,
    MarketBar,
    MarketBarSet,
    ProviderCapability,
    TickerIdentity,
)
from capexgraph.market.config import MarketSettings
from capexgraph.tools.identity import TickerResolver, canonical_ticker


class MarketProviderError(RuntimeError):
    """A provider failure safe to show without leaking request credentials."""


class MarketProviderConfigurationError(MarketProviderError):
    """Raised when an explicitly selected provider is not configured."""


class UnsupportedMarketError(MarketProviderError):
    """Raised when a provider explicitly does not cover the requested exchange."""


@dataclass(frozen=True)
class MarketFetchResult:
    bar_set: MarketBarSet
    raw_payload: bytes
    expected_sessions: tuple[date, ...] = ()
    suspended_dates: tuple[date, ...] = ()


class MarketDataProvider(Protocol):
    provider_name: str
    provider_version: str

    @classmethod
    def capability(cls) -> ProviderCapability: ...

    def source_url(self, ticker: str) -> str: ...

    def fetch_history(
        self,
        ticker: str,
        *,
        days: int = 400,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketFetchResult: ...


def _identity_timezone(identity: TickerIdentity) -> str:
    return {
        "CN": "Asia/Shanghai",
        "KR": "Asia/Seoul",
        "US": "America/New_York",
    }.get(identity.market, "UTC")


def _build_bar_set(
    *,
    identity: TickerIdentity,
    provider: str,
    provider_version: str,
    source_url: str,
    raw_payload: bytes,
    bars: list[MarketBar],
) -> MarketBarSet:
    return MarketBarSet(
        ticker=identity.ticker,
        market=identity.market,
        exchange=identity.exchange,
        currency=identity.currency,
        timezone=_identity_timezone(identity),
        provider=provider,
        provider_version=provider_version,
        source_url=source_url,
        raw_hash=hashlib.sha256(raw_payload).hexdigest(),
        bars=bars,
    )


def yahoo_symbol(ticker: str) -> str:
    canonical = canonical_ticker(ticker)
    if canonical.endswith(".SH"):
        return f"{canonical[:-3]}.SS"
    if canonical.endswith(".KO"):
        return f"{canonical[:-3]}.KS"
    if canonical.endswith(".US"):
        return canonical[:-3]
    return canonical


class YahooChartProvider:
    """Best-effort, no-key fallback backed by Yahoo's public chart endpoint."""

    provider_name = "yahoo-chart"
    provider_version = "2"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=20, follow_redirects=True)

    @classmethod
    def capability(cls) -> ProviderCapability:
        return ProviderCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN", "US", "KR"],
            exchanges=["SSE", "SZSE", "NASDAQ", "NYSE", "KRX", "KOSDAQ"],
            history=CoverageLevel.PARTIAL,
            adjusted_close=True,
            corporate_actions=CoverageLevel.PARTIAL,
            delisted_securities=CoverageLevel.PARTIAL,
            rate_limit="Undocumented public endpoint; no SLA.",
            license="Public fallback; review Yahoo terms before non-personal deployment.",
            notes=[
                "No API key is required.",
                "Coverage and adjustment semantics are not a production quality baseline.",
            ],
        )

    def source_url(self, ticker: str) -> str:
        symbol = quote(yahoo_symbol(ticker), safe=".^-")
        return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def fetch_history(
        self,
        ticker: str,
        *,
        days: int = 400,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketFetchResult:
        identity = TickerResolver().resolve(ticker)
        effective_end = end_date or datetime.now(UTC).date()
        effective_start = start_date or effective_end - timedelta(days=max(days, 70))
        period1 = int(datetime.combine(effective_start, datetime.min.time(), UTC).timestamp())
        period2 = int(
            datetime.combine(
                effective_end + timedelta(days=1),
                datetime.min.time(),
                UTC,
            ).timestamp()
        )
        try:
            response = self.client.get(
                self.source_url(identity.ticker),
                params={
                    "period1": period1,
                    "period2": period2,
                    "interval": "1d",
                    "events": "div,splits",
                },
                headers={"User-Agent": "Mozilla/5.0 CapexGraph/0.4"},
            )
        except httpx.HTTPError as error:
            raise MarketProviderError(
                f"Yahoo market request failed ({type(error).__name__})."
            ) from None
        if response.status_code >= 400:
            raise MarketProviderError(
                f"Yahoo market request failed with HTTP {response.status_code}."
            )
        try:
            chart = response.json().get("chart", {})
        except (TypeError, ValueError, AttributeError):
            raise MarketProviderError("Yahoo returned an invalid JSON response.") from None
        if chart.get("error"):
            raise MarketProviderError("Yahoo returned a market-data error.")
        results = chart.get("result") or []
        if not results:
            raise MarketProviderError(f"No market history returned for {identity.ticker}.")
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote_data = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjusted = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get(
            "adjclose"
        ) or []
        bars: list[MarketBar] = []
        for index, timestamp in enumerate(timestamps):
            raw_values = {
                key: _sequence_value(quote_data.get(key), index)
                for key in ("open", "high", "low", "close")
            }
            if any(value is None for value in raw_values.values()):
                continue
            bars.append(
                MarketBar(
                    date=datetime.fromtimestamp(timestamp, UTC).date(),
                    **raw_values,
                    adjusted_close=_sequence_value(adjusted, index),
                    volume=_sequence_value(quote_data.get("volume"), index),
                )
            )
        if not bars:
            raise MarketProviderError(f"No valid market bars returned for {identity.ticker}.")
        raw_payload = response.content
        return MarketFetchResult(
            bar_set=_build_bar_set(
                identity=identity,
                provider=self.provider_name,
                provider_version=self.provider_version,
                source_url=self.source_url(identity.ticker),
                raw_payload=raw_payload,
                bars=bars,
            ),
            raw_payload=raw_payload,
        )


def eodhd_symbol(ticker: str) -> str:
    canonical = canonical_ticker(ticker)
    if canonical.endswith(".SH"):
        return f"{canonical[:-3]}.SHG"
    if canonical.endswith(".SZ"):
        return f"{canonical[:-3]}.SHE"
    if canonical.endswith(".BJ"):
        raise UnsupportedMarketError(
            "EODHD coverage for Beijing Stock Exchange is unsupported in CapexGraph."
        )
    if canonical.endswith((".KO", ".KQ", ".US")):
        return canonical
    if "." not in canonical:
        return f"{canonical}.US"
    raise UnsupportedMarketError(f"EODHD market mapping is unsupported for {canonical}.")


class EodhdProvider:
    """Licensed cross-market daily history with credential-safe diagnostics."""

    provider_name = "eodhd"
    provider_version = "1"

    def __init__(
        self,
        api_token: str,
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_token.strip():
            raise MarketProviderConfigurationError(
                "EODHD_API_TOKEN is required when the EODHD provider is selected."
            )
        self._api_token = api_token.strip()
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self.max_attempts = max(1, max_attempts)
        self.sleeper = sleeper

    @classmethod
    def capability(cls) -> ProviderCapability:
        return ProviderCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN", "US", "KR"],
            exchanges=["SHG", "SHE", "US", "KO", "KQ"],
            history=CoverageLevel.PARTIAL,
            adjusted_close=True,
            corporate_actions=CoverageLevel.PARTIAL,
            delisted_securities=CoverageLevel.PARTIAL,
            rate_limit="Depends on the user's EODHD subscription.",
            license="Commercial account data; do not commit or redistribute raw responses.",
            notes=[
                "Raw OHLC is unadjusted; adjusted_close covers splits and dividends.",
                "Volume is split-adjusted.",
                "Actual history depth depends on the account and symbol coverage.",
                "Beijing Stock Exchange is explicitly unsupported.",
            ],
        )

    def source_url(self, ticker: str) -> str:
        symbol = quote(eodhd_symbol(ticker), safe=".-")
        return f"https://eodhd.com/api/eod/{symbol}"

    def _request(self, ticker: str, parameters: dict[str, str]) -> httpx.Response:
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.get(
                    self.source_url(ticker),
                    params={**parameters, "api_token": self._api_token},
                    headers={"User-Agent": "CapexGraph/0.4"},
                )
            except httpx.HTTPError as error:
                if attempt == self.max_attempts:
                    raise MarketProviderError(
                        f"EODHD request failed ({type(error).__name__}) "
                        f"after {attempt} attempts."
                    ) from None
                self.sleeper(0.25 * 2 ** (attempt - 1))
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt == self.max_attempts:
                return response
            self.sleeper(0.25 * 2 ** (attempt - 1))
        raise AssertionError("Unreachable EODHD retry state")

    def fetch_history(
        self,
        ticker: str,
        *,
        days: int = 400,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketFetchResult:
        identity = TickerResolver().resolve(ticker)
        effective_end = end_date or datetime.now(UTC).date()
        effective_start = start_date or effective_end - timedelta(days=max(days, 1))
        response = self._request(
            identity.ticker,
            {
                "fmt": "json",
                "period": "d",
                "order": "a",
                "from": effective_start.isoformat(),
                "to": effective_end.isoformat(),
            },
        )
        if response.status_code >= 400:
            raise MarketProviderError(
                f"EODHD request failed with HTTP {response.status_code}; "
                "check subscription coverage and provider configuration."
            )
        try:
            payload: Any = response.json()
        except ValueError:
            raise MarketProviderError("EODHD returned an invalid JSON response.") from None
        if not isinstance(payload, list):
            raise MarketProviderError(
                "EODHD returned an unexpected response instead of daily history."
            )
        bars: list[MarketBar] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                bars.append(
                    MarketBar(
                        date=item["date"],
                        open=item["open"],
                        high=item["high"],
                        low=item["low"],
                        close=item["close"],
                        adjusted_close=item.get("adjusted_close"),
                        volume=item.get("volume"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not bars:
            raise MarketProviderError(f"No valid market bars returned for {identity.ticker}.")
        raw_payload = response.content
        return MarketFetchResult(
            bar_set=_build_bar_set(
                identity=identity,
                provider=self.provider_name,
                provider_version=self.provider_version,
                source_url=self.source_url(identity.ticker),
                raw_payload=raw_payload,
                bars=bars,
            ),
            raw_payload=raw_payload,
        )


def tushare_symbol(ticker: str) -> str:
    canonical = canonical_ticker(ticker)
    if canonical.endswith((".SH", ".SZ", ".BJ")):
        return canonical
    raise UnsupportedMarketError(
        f"Tushare validation is restricted to A-share symbols; received {canonical}."
    )


class TushareDailyProvider:
    """Optional A-share specialist source used for semantics and cross-provider checks."""

    provider_name = "tushare"
    provider_version = "1"
    endpoint = "https://api.tushare.pro"

    def __init__(
        self,
        api_token: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_token.strip():
            raise MarketProviderConfigurationError(
                "TUSHARE_API_TOKEN is required when the Tushare provider is selected."
            )
        self._api_token = api_token.strip()
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    @classmethod
    def capability(cls) -> ProviderCapability:
        return ProviderCapability(
            provider=cls.provider_name,
            provider_version=cls.provider_version,
            markets=["CN"],
            exchanges=["SSE", "SZSE", "BSE"],
            history=CoverageLevel.PARTIAL,
            adjusted_close=True,
            corporate_actions=CoverageLevel.PARTIAL,
            delisted_securities=CoverageLevel.PARTIAL,
            rate_limit="Depends on the user's Tushare points and API allowance.",
            license="Personal account data; do not commit or redistribute raw responses.",
            notes=[
                "Daily OHLC is combined with adj_factor for a latest-date normalized series.",
                "Volume keeps Tushare's published unit and is not silently converted.",
                "Use as an explicit A-share validation source, never a silent fallback.",
            ],
        )

    def source_url(self, ticker: str) -> str:
        tushare_symbol(ticker)
        return self.endpoint

    def _call(
        self,
        api_name: str,
        *,
        params: dict[str, str],
        fields: str,
    ) -> dict[str, Any]:
        try:
            response = self.client.post(
                self.endpoint,
                json={
                    "api_name": api_name,
                    "token": self._api_token,
                    "params": params,
                    "fields": fields,
                },
                headers={"User-Agent": "CapexGraph/0.4"},
            )
        except httpx.HTTPError as error:
            raise MarketProviderError(
                f"Tushare request failed ({type(error).__name__})."
            ) from None
        if response.status_code >= 400:
            raise MarketProviderError(
                f"Tushare request failed with HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError:
            raise MarketProviderError("Tushare returned invalid JSON.") from None
        if not isinstance(payload, dict) or int(payload.get("code", -1)) != 0:
            raise MarketProviderError(
                "Tushare returned a provider error; check token permissions and rate limits."
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MarketProviderError("Tushare response has no data object.")
        return payload

    @staticmethod
    def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data", {})
        fields = data.get("fields", [])
        items = data.get("items", [])
        if not isinstance(fields, list) or not isinstance(items, list):
            return []
        return [
            dict(zip(fields, item, strict=False))
            for item in items
            if isinstance(item, list)
        ]

    def fetch_history(
        self,
        ticker: str,
        *,
        days: int = 400,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketFetchResult:
        identity = TickerResolver().resolve(ticker)
        symbol = tushare_symbol(identity.ticker)
        effective_end = end_date or datetime.now(UTC).date()
        effective_start = start_date or effective_end - timedelta(days=max(days, 1))
        params = {
            "ts_code": symbol,
            "start_date": effective_start.strftime("%Y%m%d"),
            "end_date": effective_end.strftime("%Y%m%d"),
        }
        daily = self._call(
            "daily",
            params=params,
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
        factors = self._call(
            "adj_factor",
            params=params,
            fields="ts_code,trade_date,adj_factor",
        )
        calendar = self._call(
            "trade_cal",
            params={
                "exchange": "SSE",
                "start_date": params["start_date"],
                "end_date": params["end_date"],
                "is_open": "1",
            },
            fields="exchange,cal_date,is_open",
        )
        try:
            suspensions = self._call(
                "suspend_d",
                params=params,
                fields="ts_code,trade_date,suspend_timing,suspend_type",
            )
        except MarketProviderError:
            suspensions = {"data": {"fields": [], "items": []}}
        factor_by_date = {
            str(item.get("trade_date")): float(item["adj_factor"])
            for item in self._rows(factors)
            if item.get("trade_date") and item.get("adj_factor") not in {None, ""}
        }
        raw_rows = self._rows(daily)
        latest_factor = (
            factor_by_date[max(factor_by_date)] if factor_by_date else 0.0
        )
        bars: list[MarketBar] = []
        for item in raw_rows:
            trade_date = str(item.get("trade_date") or "")
            factor = factor_by_date.get(trade_date)
            try:
                close = float(item["close"])
                bars.append(
                    MarketBar(
                        date=datetime.strptime(trade_date, "%Y%m%d").date(),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=close,
                        adjusted_close=(
                            close * factor / latest_factor
                            if factor is not None and latest_factor > 0
                            else None
                        ),
                        volume=(
                            float(item["vol"])
                            if item.get("vol") not in {None, ""}
                            else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        bars.sort(key=lambda item: item.date)
        if not bars:
            raise MarketProviderError(f"No valid Tushare daily bars returned for {symbol}.")
        raw_payload = json.dumps(
            {
                "daily": daily,
                "adj_factor": factors,
                "trade_cal": calendar,
                "suspend_d": suspensions,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
        return MarketFetchResult(
            bar_set=_build_bar_set(
                identity=identity,
                provider=self.provider_name,
                provider_version=self.provider_version,
                source_url=self.endpoint,
                raw_payload=raw_payload,
                bars=bars,
            ),
            raw_payload=raw_payload,
            expected_sessions=tuple(
                datetime.strptime(str(item["cal_date"]), "%Y%m%d").date()
                for item in self._rows(calendar)
                if item.get("cal_date") and str(item.get("is_open")) in {"1", "1.0"}
            ),
            suspended_dates=tuple(
                datetime.strptime(str(item["trade_date"]), "%Y%m%d").date()
                for item in self._rows(suspensions)
                if item.get("trade_date")
            ),
        )


def _sequence_value(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def build_market_provider(
    name: str | None = None,
    *,
    settings: MarketSettings | None = None,
    client: httpx.Client | None = None,
) -> MarketDataProvider:
    active_settings = settings or MarketSettings.from_environment()
    selected = (name or active_settings.provider).strip().lower()
    aliases = {
        "yahoo": "yahoo",
        "yahoo-chart": "yahoo",
        "eodhd": "eodhd",
        "tushare": "tushare",
    }
    normalized = aliases.get(selected)
    if normalized == "yahoo":
        return YahooChartProvider(client=client)
    if normalized == "eodhd":
        if active_settings.eodhd_api_token is None:
            raise MarketProviderConfigurationError(
                "EODHD_API_TOKEN is required when the EODHD provider is selected."
            )
        return EodhdProvider(active_settings.eodhd_api_token, client=client)
    if normalized == "tushare":
        if active_settings.tushare_api_token is None:
            raise MarketProviderConfigurationError(
                "TUSHARE_API_TOKEN is required when the Tushare provider is selected."
            )
        return TushareDailyProvider(active_settings.tushare_api_token, client=client)
    raise MarketProviderConfigurationError(
        f"Unknown market provider '{selected}'. Choose 'yahoo', 'eodhd', or 'tushare'."
    )


def provider_capabilities() -> list[ProviderCapability]:
    return [
        EodhdProvider.capability(),
        TushareDailyProvider.capability(),
        YahooChartProvider.capability(),
    ]
