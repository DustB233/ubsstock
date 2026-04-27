import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from china_outbound_analyzer.seeds.universe import UNIVERSE, StockUniverseSeed
from china_outbound_analyzer.services.adapters.base import NewsAdapter, NewsRecord

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_SOURCE_NAME = "Google News RSS"
DEFAULT_LOOKBACK_DAYS = 30

ALIAS_OVERRIDES: dict[str, tuple[str, ...]] = {
    "catl": ("CATL", "Contemporary Amperex", "Contemporary Amperex Technology", "宁德时代"),
    "byd": ("BYD", "比亚迪"),
    "sany-heavy": ("Sany Heavy", "Sany", "三一重工"),
    "roborock": ("Roborock", "石头科技"),
    "pop-mart": ("Pop Mart", "泡泡玛特"),
    "miniso": ("Miniso", "名创优品", "MNSO"),
    "xiaomi": ("Xiaomi", "小米", "Xiaomi Group"),
    "zhongji-innolight": ("Zhongji Innolight", "中际旭创", "Innolight"),
    "will-semiconductor": ("Will Semiconductor", "韦尔股份", "OmniVision", "OmniVision Technologies"),
    "beigene": ("BeiGene", "BeiGene Ltd", "百济神州"),
    "microport-robotics": ("MicroPort Robotics", "微创机器人", "MicroPort"),
    "aier-eye-hospital": ("Aier Eye Hospital", "爱尔眼科", "Aier"),
    "siyuan-electric": ("Siyuan Electric", "思源电气"),
    "dongfang-electric": ("Dongfang Electric", "东方电气"),
    "jerry-group": ("Jerry Group", "杰瑞股份", "Jereh"),
}


class GoogleNewsRetryableError(Exception):
    pass


class GoogleNewsRSSAdapter(NewsAdapter):
    def __init__(
        self,
        timeout_seconds: float = 12.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.lookback_days = lookback_days
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"user-agent": "Mozilla/5.0 (compatible; ChinaOutboundAnalyzer/0.1)"},
            follow_redirects=True,
        )

    async def fetch_recent_news(self, symbol: str, limit: int = 20) -> list[NewsRecord]:
        stock = resolve_stock_for_symbol(symbol)
        query = build_google_news_query(stock, lookback_days=self.lookback_days)
        logger.info("Fetching Google News RSS for %s with query %s", symbol, query)

        feed_xml = await self._fetch_feed(query)
        records = parse_google_news_feed(symbol=symbol, query=query, feed_xml=feed_xml)
        deduped_records = deduplicate_news_records(records, limit=limit)
        logger.info(
            "Fetched %s Google News items for %s and retained %s after dedupe",
            len(records),
            symbol,
            len(deduped_records),
        )
        return deduped_records

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _fetch_feed(self, query: str) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, GoogleNewsRetryableError)),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(
                    GOOGLE_NEWS_RSS_URL,
                    params={
                        "q": query,
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    },
                )
                if response.status_code >= 500 or response.status_code == 429:
                    raise GoogleNewsRetryableError(
                        f"Google News RSS retryable status {response.status_code}"
                    )
                response.raise_for_status()
                return response.text


def resolve_stock_for_symbol(symbol: str) -> StockUniverseSeed:
    normalized = symbol.strip().lower()
    for stock in UNIVERSE:
        if stock.slug == normalized:
            return stock
        if any(identifier.composite_symbol.lower() == normalized for identifier in stock.identifiers):
            return stock
    raise ValueError(f"No universe member found for symbol {symbol}")


def build_google_news_query(stock: StockUniverseSeed, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> str:
    aliases = ALIAS_OVERRIDES.get(stock.slug, (stock.company_name, stock.company_name_zh))
    rendered_aliases = " OR ".join(f'"{alias}"' for alias in aliases if alias)
    return f"({rendered_aliases}) when:{lookback_days}d"


def parse_google_news_feed(symbol: str, query: str, feed_xml: str) -> list[NewsRecord]:
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        return []

    feed_link = channel.findtext("link")
    feed_title = channel.findtext("title")
    items = channel.findall("item")
    records: list[NewsRecord] = []

    for item in items:
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        pub_date = item.findtext("pubDate")
        description = item.findtext("description")
        source_node = item.find("source")
        provider = (source_node.text or "").strip() if source_node is not None and source_node.text else None
        source_url = source_node.get("url") if source_node is not None else None

        if not raw_title or not link or not pub_date:
            continue

        published_at = parsedate_to_datetime(pub_date)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        else:
            published_at = published_at.astimezone(UTC)

        title = strip_provider_suffix(raw_title, provider)
        summary = extract_summary(description=description, provider=provider, title=title)
        external_id = guid or stable_external_id(symbol=symbol, title=title, published_at=published_at)

        records.append(
            NewsRecord(
                symbol=symbol,
                title=title,
                url=link,
                published_at=published_at,
                summary=summary,
                external_id=external_id,
                provider=provider or GOOGLE_NEWS_SOURCE_NAME,
                source_url=source_url,
                language="en",
                raw_payload={
                    "symbol": symbol,
                    "query": query,
                    "feed_link": feed_link,
                    "feed_title": feed_title,
                    "raw_title": raw_title,
                    "description_html": description,
                    "guid": guid,
                    "source_name": provider,
                    "source_url": source_url,
                    "aggregator": GOOGLE_NEWS_SOURCE_NAME,
                },
            )
        )

    return records


def deduplicate_news_records(records: list[NewsRecord], limit: int = 20) -> list[NewsRecord]:
    ranked_records = sorted(records, key=lambda item: (item.published_at, news_record_quality(item)), reverse=True)
    kept: list[NewsRecord] = []
    for record in ranked_records:
        if any(is_near_duplicate(record, existing) for existing in kept):
            continue
        kept.append(record)
        if len(kept) >= limit:
            break
    return kept


def is_near_duplicate(left: NewsRecord, right: NewsRecord) -> bool:
    if left.external_id and right.external_id and left.external_id == right.external_id:
        return True
    if left.url == right.url:
        return True

    normalized_left = normalize_title(left.title)
    normalized_right = normalize_title(right.title)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True

    published_gap = abs((left.published_at - right.published_at).total_seconds())
    if published_gap > 72 * 3600:
        return False

    similarity = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    if similarity >= 0.88:
        return True

    left_tokens = title_token_set(normalized_left)
    right_tokens = title_token_set(normalized_right)
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return overlap >= 0.7


def news_record_quality(record: NewsRecord) -> tuple[int, int, int]:
    return (
        1 if record.summary else 0,
        1 if record.source_url else 0,
        len(record.title),
    )


def strip_provider_suffix(raw_title: str, provider: str | None) -> str:
    if provider:
        suffix = f" - {provider}"
        if raw_title.endswith(suffix):
            return raw_title[: -len(suffix)].strip()
    return raw_title.strip()


def extract_summary(description: str | None, provider: str | None, title: str) -> str | None:
    if not description:
        return None

    text = html.unescape(re.sub(r"<[^>]+>", " ", description))
    text = re.sub(r"\s+", " ", text).strip()
    if provider and text.endswith(provider):
        text = text[: -len(provider)].strip(" -\u00a0")
    if not text or normalize_title(text) == normalize_title(title):
        return None
    return text


def normalize_title(value: str) -> str:
    normalized = value.lower().replace("$", " ")
    normalized = re.sub(r"\bbn\b", "billion", normalized)
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def title_token_set(value: str) -> set[str]:
    return {
        token
        for token in value.split()
        if token not in {"news", "report", "reports"} and len(token) > 1
    }


def stable_external_id(symbol: str, title: str, published_at: datetime) -> str:
    payload = f"{symbol}|{normalize_title(title)}|{published_at.date().isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
