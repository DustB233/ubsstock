import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.entities import (
    IngestionRun,
    NewsItem,
    RefreshJob,
    Stock,
    StockIdentifier,
    StockNewsMention,
)
from china_outbound_analyzer.models.enums import JobStatus, RefreshJobType
from china_outbound_analyzer.services.adapters.base import NewsAdapter, NewsRecord
from china_outbound_analyzer.services.ingestion.google_news_rss_adapter import GoogleNewsRSSAdapter
from china_outbound_analyzer.services.ingestion.mock_adapters import MockNewsAdapter
from china_outbound_analyzer.services.ingestion.seeder import get_source_id_by_key, seed_universe
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

logger = logging.getLogger(__name__)

MOCK_NEWS_SOURCE_KEY = "mock_news"
GOOGLE_NEWS_SOURCE_KEY = "google_news_rss"


@dataclass(frozen=True)
class FetchedNewsData:
    source_key: str
    records: list[NewsRecord]
    used_fallback: bool


class NewsRefreshService:
    def __init__(
        self,
        session: Session | None,
        settings: Settings | None = None,
        primary_news_adapter: NewsAdapter | None = None,
        fallback_news_adapter: NewsAdapter | None = None,
        primary_source_key: str | None = None,
        fallback_source_key: str = MOCK_NEWS_SOURCE_KEY,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        configured_source_key, configured_adapter = build_news_adapter(self.settings)
        self.primary_news_adapter = primary_news_adapter or configured_adapter
        self.fallback_news_adapter = fallback_news_adapter or MockNewsAdapter()
        self.primary_source_key = primary_source_key or configured_source_key
        self.fallback_source_key = fallback_source_key

    async def run(
        self,
        limit_per_symbol: int = 10,
        *,
        trigger_source: str = "cli:refresh-news",
        job_name: str = "refresh-news",
        refresh_job: RefreshJob | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, int | str]:
        if self.session is None:
            raise RuntimeError("NewsRefreshService requires a database session to run.")

        seed_universe(self.session)

        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.NEWS_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            scheduled_for=scheduled_for,
            stage_status={"phase": "news_ingestion", "provider": self.settings.news_data_provider},
        )
        if refresh_job is None:
            logger.info("Skipping %s because another run is still active.", job_name)
            return {
                "job_name": job_name,
                "status": "SKIPPED",
                "reason": "job_already_running",
            }

        managed_source_keys = {self.fallback_source_key, self.primary_source_key}
        source_ids = {key: get_source_id_by_key(self.session, key) for key in managed_source_keys}
        ingestion_runs = {
            key: self._new_ingestion_run(refresh_job.id, source_ids[key], "news_items")
            for key in managed_source_keys
        }
        counts = {
            "provider": self.settings.news_data_provider,
            "news_items": 0,
            "symbols": 0,
            "fallback_symbols": 0,
            "failed_symbols": 0,
        }
        failures: list[str] = []

        universe_rows = self.session.execute(
            select(Stock.id, Stock.slug, StockIdentifier.composite_symbol)
            .join(StockIdentifier, StockIdentifier.stock_id == Stock.id)
            .where(StockIdentifier.is_primary.is_(True))
        ).all()

        try:
            for stock_id, slug, primary_symbol in universe_rows:
                try:
                    with self.session.begin_nested():
                        fetched = await self._fetch_news_payload(
                            symbol=primary_symbol,
                            limit=limit_per_symbol,
                        )
                        rows_written = self._ingest_news(
                            stock_id=stock_id,
                            symbol=primary_symbol,
                            fetched=fetched,
                            source_ids=source_ids,
                            ingestion_runs=ingestion_runs,
                        )
                    counts["news_items"] += rows_written
                    counts["symbols"] += 1
                    if fetched.used_fallback:
                        counts["fallback_symbols"] += 1
                    logger.info(
                        "Refreshed news for %s (%s) using %s with %s retained items",
                        slug,
                        primary_symbol,
                        fetched.source_key,
                        rows_written,
                    )
                except Exception as exc:  # pragma: no cover
                    failures.append(primary_symbol)
                    counts["failed_symbols"] += 1
                    logger.exception("News refresh failed for %s: %s", primary_symbol, exc)

            self._cleanup_orphaned_news_items(list(source_ids.values()))

            for source_key, ingestion_run in ingestion_runs.items():
                ingestion_run.status = JobStatus.SUCCESS
                ingestion_run.completed_at = datetime.now(UTC)
                logger.info(
                    "Completed news ingestion run for %s with %s rows read and %s rows written",
                    source_key,
                    ingestion_run.rows_read,
                    ingestion_run.rows_written,
                )

            stage_status = {
                **counts,
                "failed_symbol_list": failures,
            }
            if failures:
                final_status = JobStatus.PARTIAL if counts["news_items"] > 0 else JobStatus.FAILED
                complete_job_success(
                    self.session,
                    refresh_job,
                    stage_status=stage_status,
                    status=final_status,
                    error_message="Failed symbols: " + ", ".join(failures),
                )
            else:
                complete_job_success(self.session, refresh_job, stage_status=stage_status)

            self.session.commit()
            return {"job_id": str(refresh_job.id), "status": refresh_job.status.value, **counts}
        except Exception as exc:
            complete_job_failure(
                self.session,
                refresh_job,
                error_message=str(exc),
                stage_status=counts,
            )
            self.session.commit()
            raise
        finally:
            await self.primary_news_adapter.aclose()
            if self.fallback_news_adapter is not self.primary_news_adapter:
                await self.fallback_news_adapter.aclose()

    async def _fetch_news_payload(self, symbol: str, limit: int) -> FetchedNewsData:
        if self.primary_source_key == self.fallback_source_key:
            records = list(await self.primary_news_adapter.fetch_recent_news(symbol, limit=limit))
            return FetchedNewsData(source_key=self.primary_source_key, records=records, used_fallback=False)

        try:
            records = list(await self.primary_news_adapter.fetch_recent_news(symbol, limit=limit))
            return FetchedNewsData(source_key=self.primary_source_key, records=records, used_fallback=False)
        except Exception as exc:
            logger.warning(
                "Primary news provider %s failed for %s, falling back to mock: %s",
                self.primary_source_key,
                symbol,
                exc,
            )
            records = list(await self.fallback_news_adapter.fetch_recent_news(symbol, limit=limit))
            return FetchedNewsData(source_key=self.fallback_source_key, records=records, used_fallback=True)

    def _ingest_news(
        self,
        stock_id,
        symbol: str,
        fetched: FetchedNewsData,
        source_ids: dict[str, object],
        ingestion_runs: dict[str, IngestionRun],
    ) -> int:
        if self.session is None:
            raise RuntimeError("NewsRefreshService requires a database session to ingest news.")

        source_id = source_ids[fetched.source_key]
        ingestion_run = ingestion_runs[fetched.source_key]
        ingestion_run.rows_read += len(fetched.records)

        managed_news_ids_subquery = select(NewsItem.id).where(
            NewsItem.source_id.in_(list(source_ids.values()))
        )
        self.session.execute(
            delete(StockNewsMention).where(
                StockNewsMention.stock_id == stock_id,
                StockNewsMention.news_item_id.in_(managed_news_ids_subquery),
            )
        )

        for index, record in enumerate(fetched.records, start=1):
            external_id, provider_external_id = self._normalize_external_id(
                symbol=symbol,
                record=record,
                index=index,
            )
            raw_payload = {
                "symbol": symbol,
                "source_name": record.provider,
                "source_url": record.source_url,
                "source_key": fetched.source_key,
                **(record.raw_payload or {}),
            }
            if provider_external_id is not None:
                raw_payload["provider_external_id"] = provider_external_id

            news_item_id = self.session.execute(
                insert(NewsItem)
                .values(
                    source_id=source_id,
                    external_id=external_id,
                    provider=record.provider or "Unknown Source",
                    title=record.title,
                    url=record.url,
                    summary=record.summary,
                    language=record.language or "en",
                    published_at=record.published_at,
                    raw_payload=raw_payload,
                )
                .on_conflict_do_update(
                    index_elements=[NewsItem.source_id, NewsItem.external_id],
                    set_={
                        "provider": record.provider or "Unknown Source",
                        "title": record.title,
                        "url": record.url,
                        "summary": record.summary,
                        "language": record.language or "en",
                        "published_at": record.published_at,
                        "raw_payload": raw_payload,
                    },
                )
                .returning(NewsItem.id)
            ).scalar_one()

            self.session.execute(
                insert(StockNewsMention)
                .values(
                    stock_id=stock_id,
                    news_item_id=news_item_id,
                    relevance_score=Decimal("0.95") if not fetched.used_fallback else Decimal("0.85"),
                )
                .on_conflict_do_update(
                    index_elements=[StockNewsMention.stock_id, StockNewsMention.news_item_id],
                    set_={
                        "relevance_score": Decimal("0.95") if not fetched.used_fallback else Decimal("0.85")
                    },
                )
            )

        ingestion_run.rows_written += len(fetched.records)
        self.session.flush()
        return len(fetched.records)

    @staticmethod
    def _normalize_external_id(
        *,
        symbol: str,
        record: NewsRecord,
        index: int,
    ) -> tuple[str, str | None]:
        original_external_id = (record.external_id or "").strip() or f"{symbol.lower()}-news-{index}"
        if len(original_external_id) <= 128:
            return original_external_id, None

        digest = sha256(original_external_id.encode("utf-8")).hexdigest()
        normalized = f"{symbol.lower()}-sha256-{digest}"
        return normalized[:128], original_external_id

    def _cleanup_orphaned_news_items(self, managed_source_ids: list[object]) -> None:
        if self.session is None:
            return
        mention_subquery = select(StockNewsMention.news_item_id)
        self.session.execute(
            delete(NewsItem).where(
                NewsItem.source_id.in_(managed_source_ids),
                ~NewsItem.id.in_(mention_subquery),
            )
        )

    def _new_ingestion_run(self, refresh_job_id, source_id, dataset_name: str) -> IngestionRun:
        if self.session is None:
            raise RuntimeError("NewsRefreshService requires a database session to create runs.")

        ingestion_run = IngestionRun(
            refresh_job_id=refresh_job_id,
            source_id=source_id,
            dataset_name=dataset_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
            parameters_json={"provider": self.settings.news_data_provider},
        )
        self.session.add(ingestion_run)
        self.session.flush()
        return ingestion_run


def build_news_adapter(settings: Settings) -> tuple[str, NewsAdapter]:
    provider = settings.news_data_provider.strip().lower()
    if provider in {"google_news", "google_news_rss", "real"}:
        return (
            GOOGLE_NEWS_SOURCE_KEY,
            GoogleNewsRSSAdapter(
                timeout_seconds=settings.news_request_timeout_seconds,
                max_retries=settings.news_request_max_retries,
            ),
        )
    return (MOCK_NEWS_SOURCE_KEY, MockNewsAdapter())
