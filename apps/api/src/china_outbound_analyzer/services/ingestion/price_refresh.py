import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.entities import (
    IngestionRun,
    PriceBar,
    RefreshJob,
    Stock,
    StockIdentifier,
)
from china_outbound_analyzer.models.enums import (
    JobStatus,
    PriceInterval,
    RefreshJobType,
    coerce_price_interval,
)
from china_outbound_analyzer.services.adapters.base import (
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
)
from china_outbound_analyzer.services.ingestion.mock_adapters import MockMarketDataAdapter
from china_outbound_analyzer.services.ingestion.seeder import get_source_id_by_key, seed_universe
from china_outbound_analyzer.services.ingestion.yahoo_finance_adapter import (
    YahooFinanceMarketDataAdapter,
)
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

logger = logging.getLogger(__name__)

MOCK_SOURCE_KEY = "mock_market_data"
YAHOO_SOURCE_KEY = "yahoo_finance_market_data"


@dataclass(frozen=True)
class FetchedPriceData:
    source_key: str
    records: list[HistoricalPriceRecord]
    latest_snapshot: LatestPriceSnapshotRecord | None
    used_fallback: bool


class PriceRefreshService:
    def __init__(
        self,
        session: Session | None,
        settings: Settings | None = None,
        primary_market_adapter: MarketDataAdapter | None = None,
        fallback_market_adapter: MarketDataAdapter | None = None,
        primary_source_key: str | None = None,
        fallback_source_key: str = MOCK_SOURCE_KEY,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        configured_source_key, configured_adapter = build_market_data_adapter(self.settings)
        self.primary_market_adapter = primary_market_adapter or configured_adapter
        self.fallback_market_adapter = fallback_market_adapter or MockMarketDataAdapter()
        self.primary_source_key = primary_source_key or configured_source_key
        self.fallback_source_key = fallback_source_key

    async def run(
        self,
        lookback_days: int = 400,
        *,
        trigger_source: str = "cli:refresh-prices",
        job_name: str = "refresh-prices",
        refresh_job: RefreshJob | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, int | str]:
        if self.session is None:
            raise RuntimeError("PriceRefreshService requires a database session to run.")

        seed_universe(self.session)

        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.MARKET_DATA_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            scheduled_for=scheduled_for,
            stage_status={
                "phase": "market_price_ingestion",
                "provider": self.settings.price_data_provider,
            },
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
        counts = {
            "provider": self.settings.price_data_provider,
            "price_bars": 0,
            "symbols": 0,
            "fallback_symbols": 0,
            "failed_symbols": 0,
        }
        failures: list[str] = []
        start_date = date.today() - timedelta(days=lookback_days)
        end_date = date.today()

        universe_rows = self.session.execute(
            select(
                Stock.id,
                Stock.slug,
                StockIdentifier.id,
                StockIdentifier.composite_symbol,
            )
            .join(StockIdentifier, StockIdentifier.stock_id == Stock.id)
            .where(StockIdentifier.is_primary.is_(True))
        ).all()

        try:
            for _stock_id, slug, identifier_id, primary_symbol in universe_rows:
                try:
                    with self.session.begin_nested():
                        fetched = await self._fetch_price_payload(
                            symbol=primary_symbol,
                            start_date=start_date,
                            end_date=end_date,
                        )
                        rows_written = self._ingest_price_history(
                            refresh_job_id=refresh_job.id,
                            identifier_id=identifier_id,
                            symbol=primary_symbol,
                            fetched=fetched,
                            source_ids=source_ids,
                        )
                    counts["price_bars"] += rows_written
                    counts["symbols"] += 1
                    if fetched.used_fallback:
                        counts["fallback_symbols"] += 1
                    logger.info(
                        "Refreshed price history for %s (%s) using %s with %s rows",
                        slug,
                        primary_symbol,
                        fetched.source_key,
                        rows_written,
                    )
                except Exception as exc:  # pragma: no cover
                    failures.append(primary_symbol)
                    counts["failed_symbols"] += 1
                    logger.exception("Price refresh failed for %s: %s", primary_symbol, exc)

            stage_status = {
                **counts,
                "failed_symbol_list": failures,
            }
            if failures:
                final_status = JobStatus.PARTIAL if counts["price_bars"] > 0 else JobStatus.FAILED
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
            await self.primary_market_adapter.aclose()
            if self.fallback_market_adapter is not self.primary_market_adapter:
                await self.fallback_market_adapter.aclose()

    async def _fetch_price_payload(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> FetchedPriceData:
        if self.primary_source_key == self.fallback_source_key:
            records = await self.primary_market_adapter.fetch_price_history(symbol, start_date, end_date)
            latest_snapshot = await self._resolve_latest_snapshot(
                adapter=self.primary_market_adapter,
                symbol=symbol,
                records=records,
            )
            return FetchedPriceData(
                source_key=self.primary_source_key,
                records=records,
                latest_snapshot=latest_snapshot,
                used_fallback=False,
            )

        try:
            records = await self.primary_market_adapter.fetch_price_history(symbol, start_date, end_date)
            latest_snapshot = await self._resolve_latest_snapshot(
                adapter=self.primary_market_adapter,
                symbol=symbol,
                records=records,
            )
            return FetchedPriceData(
                source_key=self.primary_source_key,
                records=records,
                latest_snapshot=latest_snapshot,
                used_fallback=False,
            )
        except Exception as exc:
            logger.warning(
                "Primary price provider %s failed for %s, falling back to mock: %s",
                self.primary_source_key,
                symbol,
                exc,
            )
            records = await self.fallback_market_adapter.fetch_price_history(symbol, start_date, end_date)
            latest_snapshot = await self._resolve_latest_snapshot(
                adapter=self.fallback_market_adapter,
                symbol=symbol,
                records=records,
            )
            return FetchedPriceData(
                source_key=self.fallback_source_key,
                records=records,
                latest_snapshot=latest_snapshot,
                used_fallback=True,
            )

    async def _resolve_latest_snapshot(
        self,
        adapter: MarketDataAdapter,
        symbol: str,
        records: list[HistoricalPriceRecord],
    ) -> LatestPriceSnapshotRecord | None:
        try:
            snapshot = await adapter.fetch_latest_price_snapshot(symbol)
            if snapshot is not None:
                return snapshot
        except Exception as exc:
            logger.warning("Latest price snapshot fetch failed for %s: %s", symbol, exc)

        if not records:
            return None

        latest_record = records[-1]
        return LatestPriceSnapshotRecord(
            symbol=symbol,
            trading_date=latest_record.trading_date,
            as_of=datetime.now(UTC),
            close=latest_record.close,
            volume=latest_record.volume,
            currency=latest_record.currency,
            source_name=latest_record.source_name,
            source_url=latest_record.source_url,
            raw_payload=latest_record.raw_payload,
        )

    def _ingest_price_history(
        self,
        refresh_job_id,
        identifier_id,
        symbol: str,
        fetched: FetchedPriceData,
        source_ids: dict[str, object],
    ) -> int:
        if self.session is None:
            raise RuntimeError("PriceRefreshService requires a database session to ingest prices.")

        source_id = source_ids[fetched.source_key]
        ingestion_run = self._new_ingestion_run(refresh_job_id, source_id, "price_bars")
        records = merge_price_history_with_snapshot(fetched.records, fetched.latest_snapshot)
        ingestion_run.rows_read = len(records)

        self.session.execute(
            delete(PriceBar).where(
                PriceBar.identifier_id == identifier_id,
                PriceBar.source_id.in_(list(source_ids.values())),
            )
        )

        for record in records:
            raw_payload = {
                "symbol": symbol,
                "source_key": fetched.source_key,
                "provider": record.source_name,
                "source_url": record.source_url,
                **(record.raw_payload or {}),
            }
            if (
                fetched.latest_snapshot is not None
                and fetched.latest_snapshot.trading_date == record.trading_date
            ):
                raw_payload["latest_snapshot"] = {
                    "as_of": fetched.latest_snapshot.as_of.isoformat(),
                    "close": fetched.latest_snapshot.close,
                    "volume": fetched.latest_snapshot.volume,
                    "currency": fetched.latest_snapshot.currency,
                    "source_name": fetched.latest_snapshot.source_name,
                    "source_url": fetched.latest_snapshot.source_url,
                    **(fetched.latest_snapshot.raw_payload or {}),
                }

            self.session.execute(
                insert(PriceBar)
                .values(
                    identifier_id=identifier_id,
                    source_id=source_id,
                    ingestion_run_id=ingestion_run.id,
                    interval=coerce_price_interval(PriceInterval.DAY_1),
                    trading_date=record.trading_date,
                    open=_to_decimal(record.open),
                    high=_to_decimal(record.high),
                    low=_to_decimal(record.low),
                    close=_to_decimal(record.close),
                    adjusted_close=_to_decimal(record.adjusted_close or record.close),
                    volume=record.volume,
                    raw_payload=raw_payload,
                )
                .on_conflict_do_update(
                    index_elements=[
                        PriceBar.identifier_id,
                        PriceBar.source_id,
                        PriceBar.interval,
                        PriceBar.trading_date,
                    ],
                    set_={
                        "open": _to_decimal(record.open),
                        "high": _to_decimal(record.high),
                        "low": _to_decimal(record.low),
                        "close": _to_decimal(record.close),
                        "adjusted_close": _to_decimal(record.adjusted_close or record.close),
                        "volume": record.volume,
                        "raw_payload": raw_payload,
                    },
                )
            )

        ingestion_run.rows_written = len(records)
        ingestion_run.status = JobStatus.SUCCESS
        self.session.flush()
        return len(records)

    def _new_ingestion_run(self, refresh_job_id, source_id, dataset_name: str) -> IngestionRun:
        if self.session is None:
            raise RuntimeError("PriceRefreshService requires a database session to create runs.")

        ingestion_run = IngestionRun(
            refresh_job_id=refresh_job_id,
            source_id=source_id,
            dataset_name=dataset_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
            parameters_json={"provider": self.settings.price_data_provider},
        )
        self.session.add(ingestion_run)
        self.session.flush()
        return ingestion_run


def build_market_data_adapter(settings: Settings) -> tuple[str, MarketDataAdapter]:
    provider = settings.price_data_provider.strip().lower()
    if provider in {"yahoo", "yahoo_finance", "real"}:
        return (
            YAHOO_SOURCE_KEY,
            YahooFinanceMarketDataAdapter(
                timeout_seconds=settings.price_request_timeout_seconds,
                max_retries=settings.price_request_max_retries,
            ),
        )
    return (MOCK_SOURCE_KEY, MockMarketDataAdapter())


def merge_price_history_with_snapshot(
    records: list[HistoricalPriceRecord],
    latest_snapshot: LatestPriceSnapshotRecord | None,
) -> list[HistoricalPriceRecord]:
    merged: dict[date, HistoricalPriceRecord] = {record.trading_date: record for record in records}
    if latest_snapshot is not None and latest_snapshot.trading_date not in merged:
        merged[latest_snapshot.trading_date] = HistoricalPriceRecord(
            symbol=latest_snapshot.symbol,
            trading_date=latest_snapshot.trading_date,
            close=latest_snapshot.close,
            open=latest_snapshot.close,
            high=latest_snapshot.close,
            low=latest_snapshot.close,
            adjusted_close=latest_snapshot.close,
            volume=latest_snapshot.volume,
            currency=latest_snapshot.currency,
            source_name=latest_snapshot.source_name,
            source_url=latest_snapshot.source_url,
            raw_payload=latest_snapshot.raw_payload,
        )
    return [merged[trading_date] for trading_date in sorted(merged)]


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
