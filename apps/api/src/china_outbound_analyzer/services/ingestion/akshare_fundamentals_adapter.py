from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from china_outbound_analyzer.services.adapters.base import (
    FinancialMetricRecord,
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
    ValuationRecord,
)

logger = logging.getLogger(__name__)

A_SHARE_VALUATION_SOURCE_NAME = "Baidu Valuation via AkShare"
A_SHARE_VALUATION_SOURCE_URL = "https://gushitong.baidu.com"
A_SHARE_COMPANY_INFO_SOURCE_NAME = "Eastmoney Company Snapshot via AkShare"
A_SHARE_COMPANY_INFO_SOURCE_URL = "https://quote.eastmoney.com"
A_SHARE_FINANCIAL_SOURCE_NAME = "Eastmoney A-share Financials via AkShare"
A_SHARE_FINANCIAL_SOURCE_URL = "https://emweb.securities.eastmoney.com"
HK_VALUATION_SOURCE_NAME = "Eastmoney HK Indicator via AkShare"
HK_VALUATION_SOURCE_URL = "https://quote.eastmoney.com/hk/"
HK_FINANCIAL_SOURCE_NAME = "Eastmoney HK Financials via AkShare"
HK_FINANCIAL_SOURCE_URL = "https://emweb.securities.eastmoney.com"


@dataclass(frozen=True)
class SymbolMeta:
    composite_symbol: str
    raw_code: str
    market: str


class AkshareFundamentalsAdapter(MarketDataAdapter):
    def __init__(self, *, timeout_seconds: float = 20.0, max_retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(max_retries, 0)

    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise NotImplementedError("AkShare fundamentals adapter does not provide price history.")

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError("AkShare fundamentals adapter does not provide price snapshots.")

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        meta = normalize_symbol(symbol)
        if meta.market == "a_share":
            return await self._fetch_a_share_valuation(meta)
        return await self._fetch_hk_valuation(meta)

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        meta = normalize_symbol(symbol)
        if meta.market == "a_share":
            return await self._fetch_a_share_financials(meta)
        return await self._fetch_hk_financials(meta)

    async def _fetch_a_share_valuation(self, meta: SymbolMeta) -> ValuationRecord | None:
        company_info = await self._call_akshare(
            "stock_individual_info_em",
            symbol=meta.raw_code,
        )
        pe_series = await self._call_akshare(
            "stock_zh_valuation_baidu",
            symbol=meta.raw_code,
            indicator="市盈率(TTM)",
            period="近一年",
        )
        pb_series = await self._call_akshare(
            "stock_zh_valuation_baidu",
            symbol=meta.raw_code,
            indicator="市净率",
            period="近一年",
        )
        market_cap_series = await self._call_akshare(
            "stock_zh_valuation_baidu",
            symbol=meta.raw_code,
            indicator="总市值",
            period="近一年",
        )

        company_info_map = dataframe_key_value_map(company_info)
        market_cap_value = _coerce_float(company_info_map.get("总市值"))
        market_cap_as_of_date, series_market_cap = latest_valuation_point(market_cap_series)
        if market_cap_value is None:
            market_cap_value = series_market_cap * 100_000_000 if series_market_cap is not None else None

        pe_as_of_date, pe_ttm = latest_valuation_point(pe_series)
        pb_as_of_date, pb = latest_valuation_point(pb_series)
        as_of_date_candidates = [
            candidate
            for candidate in [pe_as_of_date, pb_as_of_date, market_cap_as_of_date]
            if candidate is not None
        ]
        as_of_date = max(as_of_date_candidates) if as_of_date_candidates else date.today()

        if market_cap_value is None and pe_ttm is None and pb is None:
            return None

        return ValuationRecord(
            symbol=meta.composite_symbol,
            as_of_date=as_of_date,
            currency="CNY",
            market_cap=market_cap_value,
            pe_ttm=pe_ttm,
            pb=pb,
            source_name=A_SHARE_VALUATION_SOURCE_NAME,
            source_url=A_SHARE_VALUATION_SOURCE_URL,
            raw_payload={
                "company_snapshot": {
                    "source_name": A_SHARE_COMPANY_INFO_SOURCE_NAME,
                    "source_url": A_SHARE_COMPANY_INFO_SOURCE_URL,
                    "total_market_cap": market_cap_value,
                    "currency": "CNY",
                },
                "valuation_series": {
                    "pe_ttm": {"as_of_date": pe_as_of_date.isoformat() if pe_as_of_date else None, "value": pe_ttm},
                    "pb": {"as_of_date": pb_as_of_date.isoformat() if pb_as_of_date else None, "value": pb},
                    "market_cap": {
                        "as_of_date": market_cap_as_of_date.isoformat() if market_cap_as_of_date else None,
                        "value": series_market_cap,
                        "unit": "100m_cny",
                    },
                },
            },
        )

    async def _fetch_hk_valuation(self, meta: SymbolMeta) -> ValuationRecord | None:
        frame = await self._call_akshare(
            "stock_hk_financial_indicator_em",
            symbol=meta.raw_code.zfill(5),
        )
        rows = dataframe_to_dict_rows(frame)
        if not rows:
            return None

        row = rows[0]
        market_cap = _first_float(row, ["总市值(港元)", "总市值"])
        pe_ttm = _first_float(row, ["市盈率", "市盈率(TTM)"])
        pb = _first_float(row, ["市净率"])
        dividend_yield = _first_ratio(row, ["股息率TTM(%)", "股息率(%)"])
        as_of_date = _first_date(row, ["REPORT_DATE", "UPDATE_DATE", "TRADE_DATE", "DATE"]) or date.today()

        if market_cap is None and pe_ttm is None and pb is None and dividend_yield is None:
            return None

        return ValuationRecord(
            symbol=meta.composite_symbol,
            as_of_date=as_of_date,
            currency="HKD",
            market_cap=market_cap,
            pe_ttm=pe_ttm,
            pb=pb,
            dividend_yield=dividend_yield,
            source_name=HK_VALUATION_SOURCE_NAME,
            source_url=HK_VALUATION_SOURCE_URL,
            raw_payload={
                "snapshot_currency": "HKD",
                "market_cap_key": "总市值(港元)",
                "dividend_yield_key": "股息率TTM(%)",
                "snapshot_as_of_date": as_of_date.isoformat(),
                "row": row,
            },
        )

    async def _fetch_a_share_financials(self, meta: SymbolMeta) -> list[FinancialMetricRecord]:
        frame = await self._call_akshare(
            "stock_financial_analysis_indicator_em",
            symbol=meta.composite_symbol,
            indicator="按报告期",
        )
        rows = dataframe_to_dict_rows(frame)
        results: list[FinancialMetricRecord] = []
        for row in rows:
            report_date = _coerce_date(row.get("REPORT_DATE"))
            if report_date is None:
                continue
            period_type, fiscal_period, period_start = infer_period(report_date)
            debt_to_equity = debt_to_equity_from_asset_ratio(row.get("ZCFZL"))
            results.append(
                FinancialMetricRecord(
                    symbol=meta.composite_symbol,
                    period_type=period_type,
                    fiscal_year=report_date.year,
                    fiscal_period=fiscal_period,
                    period_start=period_start,
                    period_end=report_date,
                    report_date=_coerce_date(row.get("NOTICE_DATE")) or report_date,
                    currency=_string_or_default(row.get("CURRENCY"), "CNY"),
                    revenue=_coerce_float(row.get("TOTALOPERATEREVE")),
                    net_profit=_coerce_float(row.get("PARENTNETPROFIT")),
                    gross_margin=_percent_to_ratio(row.get("XSMLL")),
                    operating_margin=_first_ratio(
                        row,
                        [
                            "YYLRL",
                            "YYLRR",
                            "OPERATING_MARGIN",
                            "营业利润率(%)",
                            "营业利润率",
                        ],
                    ),
                    roe=_percent_to_ratio(row.get("ROEJQ")),
                    roa=_percent_to_ratio(row.get("ZZCJLL")),
                    debt_to_equity=debt_to_equity,
                    overseas_revenue_ratio=_first_ratio(
                        row,
                        [
                            "境外营业收入占比(%)",
                            "境外营业收入占比",
                            "境外收入占比(%)",
                            "境外收入占比",
                            "海外收入占比(%)",
                            "海外收入占比",
                        ],
                    ),
                    revenue_growth_yoy=_percent_to_ratio(row.get("TOTALOPERATEREVETZ")),
                    net_profit_growth_yoy=_percent_to_ratio(row.get("PARENTNETPROFITTZ")),
                    source_name=A_SHARE_FINANCIAL_SOURCE_NAME,
                    source_url=A_SHARE_FINANCIAL_SOURCE_URL,
                    raw_payload={
                        "report_type": row.get("REPORT_TYPE"),
                        "report_name": row.get("REPORT_DATE_NAME"),
                        "update_date": (_coerce_date(row.get("UPDATE_DATE")) or report_date).isoformat(),
                        "asset_liability_ratio_percent": _coerce_float(row.get("ZCFZL")),
                        "net_margin_percent": _coerce_float(row.get("XSJLL")),
                    },
                )
            )
        return results

    async def _fetch_hk_financials(self, meta: SymbolMeta) -> list[FinancialMetricRecord]:
        frame = await self._call_akshare(
            "stock_financial_hk_analysis_indicator_em",
            symbol=meta.raw_code.zfill(5),
            indicator="报告期",
        )
        rows = dataframe_to_dict_rows(frame)
        results: list[FinancialMetricRecord] = []
        for row in rows:
            report_date = _coerce_date(row.get("REPORT_DATE"))
            if report_date is None:
                continue
            period_type, fiscal_period, period_start = infer_period(report_date)
            debt_to_equity = debt_to_equity_from_asset_ratio(row.get("DEBT_ASSET_RATIO"))
            results.append(
                FinancialMetricRecord(
                    symbol=meta.composite_symbol,
                    period_type=period_type,
                    fiscal_year=report_date.year,
                    fiscal_period=fiscal_period,
                    period_start=period_start,
                    period_end=report_date,
                    report_date=report_date,
                    currency=_string_or_default(row.get("CURRENCY"), "HKD"),
                    revenue=_coerce_float(row.get("OPERATE_INCOME")),
                    net_profit=_coerce_float(row.get("HOLDER_PROFIT")),
                    gross_margin=_percent_to_ratio(row.get("GROSS_PROFIT_RATIO")),
                    operating_margin=_first_ratio(
                        row,
                        [
                            "OPERATE_PROFIT_RATIO",
                            "OPERATING_MARGIN",
                            "营业利润率(%)",
                            "营业利润率",
                        ],
                    ),
                    roe=_percent_to_ratio(row.get("ROE_AVG")),
                    roa=_percent_to_ratio(row.get("ROA")),
                    debt_to_equity=debt_to_equity,
                    overseas_revenue_ratio=_first_ratio(
                        row,
                        [
                            "OVERSEAS_REVENUE_RATIO",
                            "境外营业收入占比(%)",
                            "境外营业收入占比",
                            "海外收入占比(%)",
                            "海外收入占比",
                        ],
                    ),
                    revenue_growth_yoy=_percent_to_ratio(row.get("OPERATE_INCOME_YOY")),
                    net_profit_growth_yoy=_percent_to_ratio(row.get("HOLDER_PROFIT_YOY")),
                    source_name=HK_FINANCIAL_SOURCE_NAME,
                    source_url=HK_FINANCIAL_SOURCE_URL,
                    raw_payload={
                        "date_type_code": row.get("DATE_TYPE_CODE"),
                        "debt_asset_ratio_percent": _coerce_float(row.get("DEBT_ASSET_RATIO")),
                        "net_profit_ratio_percent": _coerce_float(row.get("NET_PROFIT_RATIO")),
                    },
                )
            )
        return results

    async def _call_akshare(self, function_name: str, **kwargs: Any) -> Any:
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                logger.info("Calling AkShare %s with %s", function_name, kwargs)
                function = self._resolve_function(function_name)
                return await asyncio.wait_for(
                    asyncio.to_thread(function, **kwargs),
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:  # pragma: no cover - exercised against live provider
                last_error = exc
                logger.warning(
                    "AkShare %s failed on attempt %s/%s: %s",
                    function_name,
                    attempt,
                    attempts,
                    exc,
                )
        assert last_error is not None
        raise last_error

    @staticmethod
    def _resolve_function(function_name: str):
        import akshare as ak  # noqa: PLC0415

        return getattr(ak, function_name)


def normalize_symbol(symbol: str) -> SymbolMeta:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SZ") or normalized.endswith(".SH"):
        return SymbolMeta(
            composite_symbol=normalized,
            raw_code=normalized.split(".", 1)[0],
            market="a_share",
        )
    if normalized.endswith(".HK"):
        return SymbolMeta(
            composite_symbol=normalized,
            raw_code=normalized.split(".", 1)[0].zfill(5),
            market="hk",
        )
    raise ValueError(f"Unsupported fundamentals symbol: {symbol}")


def dataframe_to_dict_rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    return list(frame.to_dict(orient="records"))


def dataframe_key_value_map(frame: Any) -> dict[str, Any]:
    rows = dataframe_to_dict_rows(frame)
    if not rows:
        return {}
    if {"item", "value"} <= set(rows[0].keys()):
        return {str(row["item"]): row.get("value") for row in rows}
    return {}


def latest_valuation_point(frame: Any) -> tuple[date | None, float | None]:
    rows = dataframe_to_dict_rows(frame)
    if not rows:
        return (None, None)
    latest_row = rows[-1]
    return (_coerce_date(latest_row.get("date")), _coerce_float(latest_row.get("value")))


def infer_period(report_date: date) -> tuple[str, str, date]:
    if report_date.month == 12 and report_date.day == 31:
        return ("ANNUAL", "FY", date(report_date.year, 1, 1))
    if report_date.month == 9 and report_date.day == 30:
        return ("QUARTERLY", "Q3", date(report_date.year, 1, 1))
    if report_date.month == 6 and report_date.day == 30:
        return ("QUARTERLY", "H1", date(report_date.year, 1, 1))
    if report_date.month == 3 and report_date.day == 31:
        return ("QUARTERLY", "Q1", date(report_date.year, 1, 1))
    quarter = ((report_date.month - 1) // 3) + 1
    period_start_month = (quarter - 1) * 3 + 1
    return ("QUARTERLY", f"Q{quarter}", date(report_date.year, period_start_month, 1))


def debt_to_equity_from_asset_ratio(value: Any) -> float | None:
    ratio = _percent_to_ratio(value)
    if ratio is None or ratio >= 1:
        return None
    return round(ratio / max(1 - ratio, 1e-9), 6)


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if " " in text:
        text = text.split(" ", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() in {"", "--", "None", "nan"}:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _percent_to_ratio(value: Any) -> float | None:
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    return round(numeric / 100, 6)


def _string_or_default(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _first_value(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in {None, "", "--"}:
            return row[key]
    return None


def _first_float(row: dict[str, Any], keys: list[str]) -> float | None:
    return _coerce_float(_first_value(row, keys))


def _first_ratio(row: dict[str, Any], keys: list[str]) -> float | None:
    return _percent_to_ratio(_first_value(row, keys))


def _first_date(row: dict[str, Any], keys: list[str]) -> date | None:
    return _coerce_date(_first_value(row, keys))
