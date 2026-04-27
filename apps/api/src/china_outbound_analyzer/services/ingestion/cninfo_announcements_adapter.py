from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import unescape
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from china_outbound_analyzer.services.adapters.base import AnnouncementAdapter, AnnouncementRecord

logger = logging.getLogger(__name__)

CNINFO_SOURCE_NAME = "CNInfo Disclosures"
CNINFO_SOURCE_SEARCH_URL = (
    "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"
)
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn/"
CNINFO_MARKET_DATA_URLS = {
    "沪深京": "https://www.cninfo.com.cn/new/data/szse_stock.json",
    "港股": "https://www.cninfo.com.cn/new/data/hke_stock.json",
}
CNINFO_TIMEZONE = ZoneInfo("Asia/Shanghai")

LOW_SIGNAL_ANNOUNCEMENT_PATTERNS = (
    "翌日披露报表",
    "证券变动月报表",
    "股份变动月报表",
    "董事名单及其角色和职能",
    "章程",
)


class CninfoAnnouncementAdapterError(Exception):
    pass


class CninfoAnnouncementRetryableError(CninfoAnnouncementAdapterError):
    pass


@dataclass(frozen=True)
class CninfoSymbolMeta:
    composite_symbol: str
    lookup_code: str
    market_label: str
    column_code: str
    exchange_code: str


class CninfoAnnouncementAdapter(AnnouncementAdapter):
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(max_retries, 1)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ChinaOutboundAnalyzer/0.1)",
                "Referer": CNINFO_SOURCE_SEARCH_URL,
                "Origin": "https://www.cninfo.com.cn",
            },
        )
        self._stock_lookup_cache: dict[str, dict[str, str]] = {}

    async def fetch_announcements(
        self,
        symbol: str,
        limit: int = 20,
        lookback_days: int | None = None,
    ) -> list[AnnouncementRecord]:
        meta = normalize_cninfo_symbol(symbol)
        org_id_map = await self._stock_lookup(meta.market_label)
        org_id = org_id_map.get(meta.lookup_code)
        if not org_id:
            raise CninfoAnnouncementAdapterError(
                f"CNInfo could not resolve orgId for {symbol} ({meta.lookup_code})."
            )

        window_days = max(lookback_days or 365, 1)
        end_date = date.today()
        start_date = end_date - timedelta(days=window_days)
        page_size = min(max(limit, 1), 30)
        pages_to_fetch = max(math.ceil(limit / page_size), 1)

        rows: list[dict[str, Any]] = []
        total_pages = 1
        for page_num in range(1, pages_to_fetch + 1):
            payload = await self._fetch_page(
                meta=meta,
                org_id=org_id,
                page_num=page_num,
                page_size=page_size,
                start_date=start_date,
                end_date=end_date,
            )
            if page_num == 1:
                total_pages = max(int(payload.get("totalpages") or 1), 1)
            rows.extend(payload.get("announcements") or [])
            if page_num >= total_pages or len(rows) >= limit:
                break

        records = [
            normalize_cninfo_announcement_row(
                row=row,
                meta=meta,
                org_id=org_id,
            )
            for row in rows
        ]
        return deduplicate_announcement_records(records, limit=limit)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _stock_lookup(self, market_label: str) -> dict[str, str]:
        cached = self._stock_lookup_cache.get(market_label)
        if cached is not None:
            return cached

        url = CNINFO_MARKET_DATA_URLS[market_label]
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.TransportError, CninfoAnnouncementRetryableError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(url)
                if response.status_code >= 500 or response.status_code == 429:
                    raise CninfoAnnouncementRetryableError(
                        f"CNInfo stock map retryable status {response.status_code} for {market_label}"
                    )
                response.raise_for_status()
                payload = response.json()
                stock_list = payload.get("stockList") or []
                mapping = {
                    str(item.get("code")).strip(): str(item.get("orgId")).strip()
                    for item in stock_list
                    if item.get("code") and item.get("orgId")
                }
                if not mapping:
                    raise CninfoAnnouncementAdapterError(
                        f"CNInfo returned an empty stock map for {market_label}."
                    )
                self._stock_lookup_cache[market_label] = mapping
                return mapping

        raise RuntimeError("CNInfo stock lookup exhausted retries unexpectedly.")

    async def _fetch_page(
        self,
        *,
        meta: CninfoSymbolMeta,
        org_id: str,
        page_num: int,
        page_size: int,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        payload = {
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "column": meta.column_code,
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{meta.lookup_code},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start_date.isoformat()}~{end_date.isoformat()}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.TransportError, CninfoAnnouncementRetryableError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await self._client.post(CNINFO_QUERY_URL, data=payload)
                if response.status_code >= 500 or response.status_code == 429:
                    raise CninfoAnnouncementRetryableError(
                        f"CNInfo announcement query retryable status {response.status_code} for {meta.composite_symbol}"
                    )
                response.raise_for_status()
                json_payload = response.json()
                if "announcements" not in json_payload:
                    raise CninfoAnnouncementAdapterError(
                        f"CNInfo response missing announcements for {meta.composite_symbol}."
                    )
                return json_payload

        raise RuntimeError("CNInfo page fetch exhausted retries unexpectedly.")


def build_cninfo_adapter(
    *,
    timeout_seconds: float,
    max_retries: int,
) -> CninfoAnnouncementAdapter:
    return CninfoAnnouncementAdapter(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


def normalize_cninfo_symbol(symbol: str) -> CninfoSymbolMeta:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SZ"):
        return CninfoSymbolMeta(
            composite_symbol=normalized,
            lookup_code=normalized.split(".", 1)[0],
            market_label="沪深京",
            column_code="szse",
            exchange_code="SZSE",
        )
    if normalized.endswith(".SH"):
        return CninfoSymbolMeta(
            composite_symbol=normalized,
            lookup_code=normalized.split(".", 1)[0],
            market_label="沪深京",
            column_code="szse",
            exchange_code="SSE",
        )
    if normalized.endswith(".HK"):
        return CninfoSymbolMeta(
            composite_symbol=normalized,
            lookup_code=normalized.split(".", 1)[0].zfill(5),
            market_label="港股",
            column_code="hke",
            exchange_code="HKEX",
        )
    raise ValueError(f"CNInfo adapter only supports A-share and HK symbols: {symbol}")


def normalize_cninfo_announcement_row(
    *,
    row: dict[str, Any],
    meta: CninfoSymbolMeta,
    org_id: str,
) -> AnnouncementRecord:
    announcement_id = str(row.get("announcementId") or "").strip()
    title = _clean_text(row.get("announcementTitle")) or _clean_text(row.get("shortTitle"))
    if not announcement_id or not title:
        raise CninfoAnnouncementAdapterError(
            f"CNInfo row for {meta.composite_symbol} is missing announcementId/title."
        )

    published_local = _coerce_local_datetime(row.get("announcementTime"))
    as_of_date = published_local.date() if published_local else None
    published_at = published_local.astimezone(UTC) if published_local else datetime.now(UTC)

    detail_url = build_cninfo_detail_url(
        stock_code=meta.lookup_code,
        announcement_id=announcement_id,
        org_id=str(row.get("orgId") or org_id),
        published_at=published_local,
    )
    attachment_url = build_cninfo_attachment_url(row.get("adjunctUrl"))
    summary = _clean_text(row.get("announcementContent"))
    category = _clean_text(row.get("announcementTypeName"))

    raw_payload = {
        "source_name": CNINFO_SOURCE_NAME,
        "source_url": CNINFO_SOURCE_SEARCH_URL,
        "market_label": meta.market_label,
        "column_code": meta.column_code,
        "exchange_code": meta.exchange_code,
        "detail_url": detail_url,
        "attachment_url": attachment_url,
        "announcement_id": announcement_id,
        "org_id": str(row.get("orgId") or org_id),
        "lookup_symbol": meta.composite_symbol,
        "sec_code": str(row.get("secCode") or meta.lookup_code),
        "sec_name": _clean_text(row.get("secName")),
        "announcement_type": row.get("announcementType"),
        "announcement_type_name": category,
        "adjunct_type": row.get("adjunctType"),
        "adjunct_size": row.get("adjunctSize"),
        "page_column": row.get("pageColumn"),
        "important": row.get("important"),
        "raw_row": row,
    }

    return AnnouncementRecord(
        symbol=meta.composite_symbol,
        title=title,
        url=attachment_url or detail_url,
        published_at=published_at,
        category=category,
        summary=summary,
        external_id=f"cninfo:{announcement_id}",
        provider=CNINFO_SOURCE_NAME,
        exchange=meta.exchange_code,
        language="zh",
        as_of_date=as_of_date,
        source_url=detail_url,
        raw_payload=raw_payload,
    )


def deduplicate_announcement_records(
    records: list[AnnouncementRecord],
    *,
    limit: int | None = None,
) -> list[AnnouncementRecord]:
    ordered = sorted(
        records,
        key=lambda item: (
            _announcement_signal_priority(item.title),
            -(item.published_at.timestamp() if item.published_at else 0.0),
            item.external_id or item.url,
        ),
    )
    deduped: list[AnnouncementRecord] = []
    seen_external_ids: set[str] = set()
    seen_near_keys: set[tuple[str, str | None]] = set()

    for record in ordered:
        if record.external_id and record.external_id in seen_external_ids:
            continue
        near_key = (
            normalize_announcement_title(record.title),
            record.as_of_date.isoformat()
            if record.as_of_date is not None
            else record.published_at.date().isoformat(),
        )
        if near_key in seen_near_keys:
            continue

        if record.external_id:
            seen_external_ids.add(record.external_id)
        seen_near_keys.add(near_key)
        deduped.append(record)
        if limit is not None and len(deduped) >= limit:
            break

    return deduped


def normalize_announcement_title(title: str) -> str:
    cleaned = _clean_text(title) or ""
    cleaned = re.sub(r"^[^:：]{1,48}[:：]\s*", "", cleaned)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", cleaned)
    return cleaned


def build_cninfo_detail_url(
    *,
    stock_code: str,
    announcement_id: str,
    org_id: str,
    published_at: datetime | None,
) -> str:
    query = urlencode(
        {
            "stockCode": stock_code,
            "announcementId": announcement_id,
            "orgId": org_id,
            "announcementTime": (
                published_at.strftime("%Y-%m-%d %H:%M:%S") if published_at is not None else ""
            ),
        }
    )
    return f"https://www.cninfo.com.cn/new/disclosure/detail?{query}"


def build_cninfo_attachment_url(value: Any) -> str | None:
    adjunct_url = str(value or "").strip()
    if not adjunct_url:
        return None
    return f"{CNINFO_STATIC_BASE_URL}{adjunct_url.lstrip('/')}"


def _coerce_local_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000, tz=UTC).astimezone(
                CNINFO_TIMEZONE
            )
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=CNINFO_TIMEZONE)
        return parsed.astimezone(CNINFO_TIMEZONE)
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _announcement_signal_priority(title: str) -> int:
    return 1 if any(pattern in title for pattern in LOW_SIGNAL_ANNOUNCEMENT_PATTERNS) else 0
