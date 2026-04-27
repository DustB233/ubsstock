import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from china_outbound_analyzer.services.adapters.base import (
    FinancialMetricRecord,
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
    ValuationRecord,
)

logger = logging.getLogger(__name__)

YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_SOURCE_NAME = "Yahoo Finance"


class YahooFinanceAdapterError(Exception):
    pass


class YahooFinanceRetryableError(YahooFinanceAdapterError):
    pass


@dataclass(frozen=True)
class YahooChartPayload:
    provider_symbol: str
    currency: str | None
    exchange_name: str | None
    exchange_timezone: str | None
    regular_market_price: float | None
    regular_market_time: int | None
    previous_close: float | None
    data: dict[str, Any]


class YahooFinanceMarketDataAdapter(MarketDataAdapter):
    def __init__(
        self,
        timeout_seconds: float = 12.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"user-agent": "Mozilla/5.0 (compatible; ChinaOutboundAnalyzer/0.1)"},
        )

    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        provider_symbol = normalize_yahoo_symbol(symbol)
        logger.info(
            "Fetching Yahoo Finance price history for %s via %s between %s and %s",
            symbol,
            provider_symbol,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        payload = await self._fetch_chart(
            provider_symbol=provider_symbol,
            params={
                "interval": "1d",
                "includePrePost": "false",
                "events": "div,splits,capitalGains",
                "period1": self._unix_timestamp(start_date),
                "period2": self._unix_timestamp(end_date + timedelta(days=1)),
            },
        )
        return self._extract_price_history(symbol, payload, start_date, end_date)

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        provider_symbol = normalize_yahoo_symbol(symbol)
        payload = await self._fetch_chart(
            provider_symbol=provider_symbol,
            params={
                "interval": "1d",
                "range": "5d",
                "includePrePost": "false",
                "events": "div,splits,capitalGains",
            },
        )
        latest_row = self._extract_latest_row(symbol, payload)
        if latest_row is None:
            return None

        snapshot_time = payload.regular_market_time
        as_of = (
            datetime.fromtimestamp(snapshot_time, tz=UTC)
            if snapshot_time is not None
            else datetime.now(UTC)
        )
        return LatestPriceSnapshotRecord(
            symbol=symbol,
            trading_date=latest_row.trading_date,
            as_of=as_of,
            close=payload.regular_market_price or latest_row.close,
            volume=latest_row.volume,
            currency=payload.currency,
            source_name=YAHOO_SOURCE_NAME,
            source_url=build_yahoo_history_url(provider_symbol),
            raw_payload={
                "provider_symbol": provider_symbol,
                "exchange_name": payload.exchange_name,
                "exchange_timezone": payload.exchange_timezone,
                "previous_close": payload.previous_close,
            },
        )

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        raise NotImplementedError("YahooFinanceMarketDataAdapter only supports price history for now.")

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        raise NotImplementedError("YahooFinanceMarketDataAdapter only supports price history for now.")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _fetch_chart(
        self,
        provider_symbol: str,
        params: dict[str, str | int],
    ) -> YahooChartPayload:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.TransportError, YahooFinanceRetryableError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(
                    f"{YAHOO_CHART_BASE_URL}/{provider_symbol}",
                    params=params,
                )
                if response.status_code >= 500 or response.status_code == 429:
                    raise YahooFinanceRetryableError(
                        f"Yahoo Finance retryable status {response.status_code} for {provider_symbol}"
                    )
                response.raise_for_status()
                payload = response.json()
                chart_payload = payload.get("chart", {})
                if chart_payload.get("error") is not None:
                    raise YahooFinanceAdapterError(
                        f"Yahoo Finance returned an error for {provider_symbol}: "
                        f"{chart_payload['error']}"
                    )

                result = chart_payload.get("result") or []
                if not result:
                    raise YahooFinanceAdapterError(
                        f"Yahoo Finance returned no result rows for {provider_symbol}"
                    )

                meta = result[0].get("meta", {})
                logger.info(
                    "Received Yahoo Finance payload for %s with %s timestamps",
                    provider_symbol,
                    len(result[0].get("timestamp") or []),
                )
                return YahooChartPayload(
                    provider_symbol=provider_symbol,
                    currency=meta.get("currency"),
                    exchange_name=meta.get("exchangeName"),
                    exchange_timezone=meta.get("exchangeTimezoneName"),
                    regular_market_price=meta.get("regularMarketPrice"),
                    regular_market_time=meta.get("regularMarketTime"),
                    previous_close=meta.get("previousClose"),
                    data=result[0],
                )

    def _extract_price_history(
        self,
        symbol: str,
        payload: YahooChartPayload,
        start_date: date,
        end_date: date,
    ) -> list[HistoricalPriceRecord]:
        timestamps = payload.data.get("timestamp") or []
        indicators = payload.data.get("indicators", {})
        quote = (indicators.get("quote") or [{}])[0]
        adjclose = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []

        records: list[HistoricalPriceRecord] = []
        for index, timestamp in enumerate(timestamps):
            trading_date = datetime.fromtimestamp(timestamp, tz=UTC).date()
            if trading_date < start_date or trading_date > end_date:
                continue

            close = _value_at(quote.get("close"), index)
            if close is None:
                continue

            records.append(
                HistoricalPriceRecord(
                    symbol=symbol,
                    trading_date=trading_date,
                    open=_value_at(quote.get("open"), index),
                    high=_value_at(quote.get("high"), index),
                    low=_value_at(quote.get("low"), index),
                    close=close,
                    adjusted_close=_value_at(adjclose, index) or close,
                    volume=_int_value_at(quote.get("volume"), index),
                    currency=payload.currency,
                    source_name=YAHOO_SOURCE_NAME,
                    source_url=build_yahoo_history_url(payload.provider_symbol),
                    raw_payload={
                        "provider_symbol": payload.provider_symbol,
                        "exchange_name": payload.exchange_name,
                        "exchange_timezone": payload.exchange_timezone,
                    },
                )
            )

        if not records:
            raise YahooFinanceAdapterError(f"No usable historical prices were returned for {symbol}")

        return records

    def _extract_latest_row(
        self,
        symbol: str,
        payload: YahooChartPayload,
    ) -> HistoricalPriceRecord | None:
        records = self._extract_price_history(
            symbol=symbol,
            payload=payload,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
        )
        return records[-1] if records else None

    @staticmethod
    def _unix_timestamp(value: date) -> int:
        return int(datetime.combine(value, time.min, tzinfo=UTC).timestamp())


def normalize_yahoo_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SH"):
        return f"{normalized[:-3]}.SS"
    return normalized


def build_yahoo_history_url(provider_symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{provider_symbol}/history"


def _value_at(values: list[Any] | None, index: int) -> float | None:
    if values is None or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    return float(value)


def _int_value_at(values: list[Any] | None, index: int) -> int | None:
    value = _value_at(values, index)
    return int(value) if value is not None else None
