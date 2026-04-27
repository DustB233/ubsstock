from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.entities import (
    Announcement,
    IngestionRun,
    RefreshJob,
    Stock,
    StockIdentifier,
)
from china_outbound_analyzer.models.enums import IdentifierType, JobStatus, RefreshJobType
from china_outbound_analyzer.services.adapters.base import AnnouncementAdapter, AnnouncementRecord
from china_outbound_analyzer.services.ingestion.cninfo_announcements_adapter import (
    CninfoAnnouncementAdapter,
    deduplicate_announcement_records,
)
from china_outbound_analyzer.services.ingestion.mock_adapters import MockAnnouncementAdapter
from china_outbound_analyzer.services.ingestion.seeder import get_source_id_by_key, seed_universe
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

logger = logging.getLogger(__name__)

MOCK_ANNOUNCEMENTS_SOURCE_KEY = "mock_announcements"
CNINFO_ANNOUNCEMENTS_SOURCE_KEY = "cninfo_announcements"


@dataclass(frozen=True)
class FetchedAnnouncementsData:
    source_key: str
    records: list[AnnouncementRecord]
    used_fallback: bool
    lookup_symbols: list[str]
    failed_lookup_symbols: list[str]


class AnnouncementRefreshService:
    def __init__(
        self,
        session: Session | None,
        settings: Settings | None = None,
        primary_announcement_adapter: AnnouncementAdapter | None = None,
        fallback_announcement_adapter: AnnouncementAdapter | None = None,
        primary_source_key: str | None = None,
        fallback_source_key: str = MOCK_ANNOUNCEMENTS_SOURCE_KEY,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        configured_source_key, configured_adapter = build_announcement_adapter(self.settings)
        self.primary_announcement_adapter = primary_announcement_adapter or configured_adapter
        self.fallback_announcement_adapter = fallback_announcement_adapter or MockAnnouncementAdapter()
        self.primary_source_key = primary_source_key or configured_source_key
        self.fallback_source_key = fallback_source_key

    async def run(
        self,
        *,
        limit_per_symbol: int = 12,
        lookback_days: int = 365,
        trigger_source: str = "cli:refresh-announcements",
        job_name: str = "refresh-announcements",
        refresh_job: RefreshJob | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, int | str]:
        if self.session is None:
            raise RuntimeError("AnnouncementRefreshService requires a database session to run.")

        seed_universe(self.session)
        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.ANNOUNCEMENTS_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            scheduled_for=scheduled_for,
            stage_status={
                "phase": "announcement_ingestion",
                "provider": self.settings.announcements_data_provider,
            },
        )
        if refresh_job is None:
            logger.info("Skipping %s because another run is still active.", job_name)
            return {
                "job_name": job_name,
                "status": "SKIPPED",
                "reason": "job_already_running",
            }

        managed_source_keys = {self.primary_source_key, self.fallback_source_key}
        source_ids = {key: get_source_id_by_key(self.session, key) for key in managed_source_keys}
        ingestion_runs = {
            key: self._new_ingestion_run(refresh_job.id, source_ids[key], "announcements")
            for key in managed_source_keys
        }
        counts = {
            "provider": self.settings.announcements_data_provider,
            "announcements": 0,
            "symbols": 0,
            "fallback_symbols": 0,
            "failed_symbols": 0,
        }
        failures: list[str] = []

        stocks = self.session.scalars(select(Stock).order_by(Stock.slug.asc())).all()

        try:
            for stock in stocks:
                identifiers = order_announcement_identifiers(self._identifiers(stock.id))
                if not identifiers:
                    failures.append(stock.slug)
                    counts["failed_symbols"] += 1
                    logger.warning(
                        "Announcement refresh skipped for %s because no supported identifiers exist.",
                        stock.slug,
                    )
                    continue

                try:
                    with self.session.begin_nested():
                        fetched = await self._fetch_announcements_for_identifiers(
                            identifiers=identifiers,
                            limit_per_symbol=limit_per_symbol,
                            lookback_days=lookback_days,
                        )
                        rows_written = self._ingest_announcements(
                            stock_id=stock.id,
                            stock_slug=stock.slug,
                            fetched=fetched,
                            source_ids=source_ids,
                            ingestion_runs=ingestion_runs,
                        )
                    counts["announcements"] += rows_written
                    counts["symbols"] += 1
                    if fetched.used_fallback:
                        counts["fallback_symbols"] += 1
                    logger.info(
                        "Refreshed %s announcements for %s using %s across %s",
                        rows_written,
                        stock.slug,
                        fetched.source_key,
                        ", ".join(fetched.lookup_symbols) or "no identifiers",
                    )
                except Exception as exc:  # pragma: no cover
                    failures.append(stock.slug)
                    counts["failed_symbols"] += 1
                    logger.exception("Announcement refresh failed for %s: %s", stock.slug, exc)

            for ingestion_run in ingestion_runs.values():
                ingestion_run.status = JobStatus.SUCCESS
                ingestion_run.completed_at = datetime.now(UTC)

            stage_status = {**counts, "failed_stock_list": failures}
            if failures:
                final_status = JobStatus.PARTIAL if counts["announcements"] > 0 else JobStatus.FAILED
                complete_job_success(
                    self.session,
                    refresh_job,
                    stage_status=stage_status,
                    status=final_status,
                    error_message="Failed stocks: " + ", ".join(failures),
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
            await self.primary_announcement_adapter.aclose()
            if self.fallback_announcement_adapter is not self.primary_announcement_adapter:
                await self.fallback_announcement_adapter.aclose()

    async def _fetch_announcements_for_identifiers(
        self,
        *,
        identifiers: list[StockIdentifier],
        limit_per_symbol: int,
        lookback_days: int,
    ) -> FetchedAnnouncementsData:
        lookup_symbols = [identifier.composite_symbol for identifier in identifiers]

        if self.primary_source_key == self.fallback_source_key:
            records: list[AnnouncementRecord] = []
            for identifier in identifiers:
                records.extend(
                    await self.primary_announcement_adapter.fetch_announcements(
                        identifier.composite_symbol,
                        limit=limit_per_symbol,
                        lookback_days=lookback_days,
                    )
                )
            return FetchedAnnouncementsData(
                source_key=self.primary_source_key,
                records=deduplicate_announcement_records(records),
                used_fallback=False,
                lookup_symbols=lookup_symbols,
                failed_lookup_symbols=[],
            )

        records: list[AnnouncementRecord] = []
        failed_lookup_symbols: list[str] = []
        successful_fetches = 0
        for identifier in identifiers:
            try:
                fetched_records = await self.primary_announcement_adapter.fetch_announcements(
                    identifier.composite_symbol,
                    limit=limit_per_symbol,
                    lookback_days=lookback_days,
                )
                successful_fetches += 1
                records.extend(fetched_records)
            except Exception as exc:
                failed_lookup_symbols.append(identifier.composite_symbol)
                logger.warning(
                    "Primary announcement provider %s failed for %s: %s",
                    self.primary_source_key,
                    identifier.composite_symbol,
                    exc,
                )

        if successful_fetches > 0:
            return FetchedAnnouncementsData(
                source_key=self.primary_source_key,
                records=deduplicate_announcement_records(records),
                used_fallback=False,
                lookup_symbols=lookup_symbols,
                failed_lookup_symbols=failed_lookup_symbols,
            )

        fallback_symbol = identifiers[0].composite_symbol
        logger.warning(
            "Primary announcement provider %s failed for all identifiers on %s; falling back to mock.",
            self.primary_source_key,
            fallback_symbol,
        )
        fallback_records = await self.fallback_announcement_adapter.fetch_announcements(
            fallback_symbol,
            limit=limit_per_symbol,
            lookback_days=lookback_days,
        )
        return FetchedAnnouncementsData(
            source_key=self.fallback_source_key,
            records=deduplicate_announcement_records(list(fallback_records)),
            used_fallback=True,
            lookup_symbols=lookup_symbols,
            failed_lookup_symbols=failed_lookup_symbols,
        )

    def _ingest_announcements(
        self,
        *,
        stock_id,
        stock_slug: str,
        fetched: FetchedAnnouncementsData,
        source_ids: dict[str, object],
        ingestion_runs: dict[str, IngestionRun],
    ) -> int:
        if self.session is None:
            raise RuntimeError(
                "AnnouncementRefreshService requires a database session to ingest announcements."
            )

        source_id = source_ids[fetched.source_key]
        ingestion_run = ingestion_runs[fetched.source_key]
        ingestion_run.rows_read += len(fetched.records)

        self.session.execute(
            delete(Announcement).where(
                Announcement.stock_id == stock_id,
                Announcement.source_id.in_(list(source_ids.values())),
            )
        )

        for record in fetched.records:
            raw_payload = {
                "symbol": record.symbol,
                "stock_slug": stock_slug,
                "source_name": record.provider,
                "source_url": record.source_url,
                "exchange_code": record.exchange,
                "language": record.language,
                "source_key": fetched.source_key,
                **(record.raw_payload or {}),
            }
            self.session.execute(
                insert(Announcement)
                .values(
                    stock_id=stock_id,
                    source_id=source_id,
                    external_id=record.external_id or f"{record.symbol.lower()}-{record.title[:48]}",
                    title=record.title,
                    url=record.url,
                    provider=record.provider,
                    exchange_code=record.exchange,
                    category=record.category,
                    language=record.language or "zh",
                    published_at=record.published_at,
                    as_of_date=record.as_of_date or record.published_at.date(),
                    summary=record.summary,
                    raw_payload=raw_payload,
                )
                .on_conflict_do_update(
                    index_elements=[
                        Announcement.stock_id,
                        Announcement.source_id,
                        Announcement.external_id,
                    ],
                    set_={
                        "title": record.title,
                        "url": record.url,
                        "provider": record.provider,
                        "exchange_code": record.exchange,
                        "category": record.category,
                        "language": record.language or "zh",
                        "published_at": record.published_at,
                        "as_of_date": record.as_of_date or record.published_at.date(),
                        "summary": record.summary,
                        "raw_payload": raw_payload,
                    },
                )
            )

        ingestion_run.rows_written += len(fetched.records)
        self.session.flush()
        return len(fetched.records)

    def _identifiers(self, stock_id) -> list[StockIdentifier]:
        if self.session is None:
            return []
        return self.session.scalars(
            select(StockIdentifier)
            .where(StockIdentifier.stock_id == stock_id)
            .order_by(StockIdentifier.is_primary.desc(), StockIdentifier.composite_symbol.asc())
        ).all()

    def _new_ingestion_run(self, refresh_job_id, source_id, dataset_name: str) -> IngestionRun:
        if self.session is None:
            raise RuntimeError("AnnouncementRefreshService requires a database session.")
        ingestion_run = IngestionRun(
            refresh_job_id=refresh_job_id,
            source_id=source_id,
            dataset_name=dataset_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self.session.add(ingestion_run)
        self.session.flush()
        return ingestion_run


def build_announcement_adapter(
    settings: Settings,
) -> tuple[str, AnnouncementAdapter]:
    provider = settings.announcements_data_provider.strip().lower()
    if provider == "mock":
        return MOCK_ANNOUNCEMENTS_SOURCE_KEY, MockAnnouncementAdapter()
    if provider in {"cninfo", "real"}:
        return (
            CNINFO_ANNOUNCEMENTS_SOURCE_KEY,
            CninfoAnnouncementAdapter(
                timeout_seconds=settings.announcements_request_timeout_seconds,
                max_retries=settings.announcements_request_max_retries,
            ),
        )
    raise ValueError(f"Unsupported announcements provider: {settings.announcements_data_provider}")


def order_announcement_identifiers(
    identifiers: list[StockIdentifier],
) -> list[StockIdentifier]:
    filtered = [
        identifier
        for identifier in identifiers
        if identifier.identifier_type in {IdentifierType.A_SHARE, IdentifierType.H_SHARE}
    ]
    candidates = filtered or identifiers
    return sorted(
        candidates,
        key=lambda identifier: (
            0
            if identifier.identifier_type == IdentifierType.A_SHARE
            else 1
            if identifier.identifier_type == IdentifierType.H_SHARE
            else 2,
            0 if identifier.is_primary else 1,
            identifier.composite_symbol,
        ),
    )
