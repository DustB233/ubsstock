import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.entities import (
    FinancialMetric,
    IngestionRun,
    RefreshJob,
    Stock,
    StockIdentifier,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import (
    FinancialPeriodType,
    IdentifierType,
    JobStatus,
    RefreshJobType,
)
from china_outbound_analyzer.services.adapters.base import (
    FinancialMetricRecord,
    MarketDataAdapter,
    ValuationRecord,
)
from china_outbound_analyzer.services.ingestion.akshare_fundamentals_adapter import (
    AkshareFundamentalsAdapter,
)
from china_outbound_analyzer.services.ingestion.mock_adapters import MockMarketDataAdapter
from china_outbound_analyzer.services.ingestion.seeder import get_source_id_by_key, seed_universe
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

logger = logging.getLogger(__name__)

MOCK_FUNDAMENTALS_SOURCE_KEY = "mock_fundamentals"
AKSHARE_FUNDAMENTALS_SOURCE_KEY = "akshare_fundamentals"


@dataclass(frozen=True)
class FetchedFundamentalsData:
    source_key: str
    valuation: ValuationRecord | None
    financials: list[FinancialMetricRecord]
    used_fallback: bool
    lookup_symbol: str
    lookup_identifier_type: str | None
    lookup_currency: str | None


class FundamentalsRefreshService:
    def __init__(
        self,
        session: Session | None,
        settings: Settings | None = None,
        primary_market_adapter: MarketDataAdapter | None = None,
        fallback_market_adapter: MarketDataAdapter | None = None,
        primary_source_key: str | None = None,
        fallback_source_key: str = MOCK_FUNDAMENTALS_SOURCE_KEY,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        configured_source_key, configured_adapter = build_fundamentals_adapter(self.settings)
        self.primary_market_adapter = primary_market_adapter or configured_adapter
        self.fallback_market_adapter = fallback_market_adapter or MockMarketDataAdapter()
        self.primary_source_key = primary_source_key or configured_source_key
        self.fallback_source_key = fallback_source_key

    async def run(
        self,
        *,
        trigger_source: str = "cli:refresh-fundamentals",
        job_name: str = "refresh-fundamentals",
        refresh_job: RefreshJob | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, int | str]:
        if self.session is None:
            raise RuntimeError("FundamentalsRefreshService requires a database session to run.")

        seed_universe(self.session)
        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.FUNDAMENTALS_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            scheduled_for=scheduled_for,
            stage_status={
                "phase": "fundamentals_ingestion",
                "provider": self.settings.fundamentals_data_provider,
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
            key: {
                "valuation_snapshots": self._new_ingestion_run(
                    refresh_job.id,
                    source_ids[key],
                    "valuation_snapshots",
                ),
                "financial_metrics": self._new_ingestion_run(
                    refresh_job.id,
                    source_ids[key],
                    "financial_metrics",
                ),
            }
            for key in managed_source_keys
        }
        counts = {
            "provider": self.settings.fundamentals_data_provider,
            "valuation_snapshots": 0,
            "financial_metrics": 0,
            "symbols": 0,
            "fallback_symbols": 0,
            "failed_symbols": 0,
        }
        failures: list[str] = []

        stocks = self.session.scalars(select(Stock).order_by(Stock.slug.asc())).all()

        try:
            for stock in stocks:
                identifiers = self._identifier_candidates_for_stock(stock.id)
                if not identifiers:
                    failures.append(stock.slug)
                    counts["failed_symbols"] += 1
                    logger.warning("Fundamentals refresh skipped for %s because no identifiers exist.", stock.slug)
                    continue

                primary_identifier = next(
                    (identifier for identifier in identifiers if identifier.is_primary),
                    identifiers[0],
                )
                try:
                    with self.session.begin_nested():
                        fetched = await self._fetch_fundamentals_for_identifiers(identifiers)
                        written = self._ingest_fundamentals(
                            stock_id=stock.id,
                            primary_symbol=primary_identifier.composite_symbol,
                            fetched=fetched,
                            source_ids=source_ids,
                            ingestion_runs=ingestion_runs,
                        )
                    counts["valuation_snapshots"] += written["valuation_snapshots"]
                    counts["financial_metrics"] += written["financial_metrics"]
                    counts["symbols"] += 1
                    if fetched.used_fallback:
                        counts["fallback_symbols"] += 1
                    logger.info(
                        "Refreshed fundamentals for %s (%s) using %s with %s valuation rows and %s financial rows",
                        stock.slug,
                        fetched.lookup_symbol,
                        fetched.source_key,
                        written["valuation_snapshots"],
                        written["financial_metrics"],
                    )
                except Exception as exc:  # pragma: no cover
                    failures.append(primary_identifier.composite_symbol)
                    counts["failed_symbols"] += 1
                    logger.exception(
                        "Fundamentals refresh failed for %s: %s",
                        primary_identifier.composite_symbol,
                        exc,
                    )

            for source_runs in ingestion_runs.values():
                for ingestion_run in source_runs.values():
                    ingestion_run.status = JobStatus.SUCCESS
                    ingestion_run.completed_at = datetime.now(UTC)

            if failures:
                final_status = (
                    JobStatus.PARTIAL
                    if counts["valuation_snapshots"] > 0 or counts["financial_metrics"] > 0
                    else JobStatus.FAILED
                )
                complete_job_success(
                    self.session,
                    refresh_job,
                    stage_status={**counts, "failed_symbol_list": failures},
                    status=final_status,
                    error_message="Failed symbols: " + ", ".join(failures),
                )
            else:
                complete_job_success(self.session, refresh_job, stage_status=counts)

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

    async def _fetch_fundamentals_payload(self, symbol: str) -> FetchedFundamentalsData:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol.endswith(".HK"):
            lookup_currency = "HKD"
            lookup_identifier_type = IdentifierType.H_SHARE.value
        elif normalized_symbol.endswith(".SZ") or normalized_symbol.endswith(".SH"):
            lookup_currency = "CNY"
            lookup_identifier_type = IdentifierType.A_SHARE.value
        else:
            lookup_currency = "USD"
            lookup_identifier_type = IdentifierType.US_LISTING.value
        if self.primary_source_key == self.fallback_source_key:
            valuation = await self.primary_market_adapter.fetch_valuation_snapshot(normalized_symbol)
            financials = list(await self.primary_market_adapter.fetch_financial_metrics(normalized_symbol))
            return FetchedFundamentalsData(
                source_key=self.primary_source_key,
                valuation=valuation,
                financials=financials,
                used_fallback=False,
                lookup_symbol=normalized_symbol,
                lookup_identifier_type=lookup_identifier_type,
                lookup_currency=lookup_currency,
            )

        valuation, financials = await self._fetch_from_primary_provider(normalized_symbol)
        if valuation is not None or financials:
            return FetchedFundamentalsData(
                source_key=self.primary_source_key,
                valuation=valuation,
                financials=financials,
                used_fallback=False,
                lookup_symbol=normalized_symbol,
                lookup_identifier_type=lookup_identifier_type,
                lookup_currency=lookup_currency,
            )

        logger.warning(
            "Primary fundamentals provider %s produced no usable data for %s, falling back to mock.",
            self.primary_source_key,
            normalized_symbol,
        )
        fallback_valuation = await self.fallback_market_adapter.fetch_valuation_snapshot(normalized_symbol)
        fallback_financials = list(
            await self.fallback_market_adapter.fetch_financial_metrics(normalized_symbol)
        )
        return FetchedFundamentalsData(
            source_key=self.fallback_source_key,
            valuation=fallback_valuation,
            financials=fallback_financials,
            used_fallback=True,
            lookup_symbol=normalized_symbol,
            lookup_identifier_type=lookup_identifier_type,
            lookup_currency=lookup_currency,
        )

    async def _fetch_fundamentals_for_identifiers(
        self,
        identifiers: list[StockIdentifier],
    ) -> FetchedFundamentalsData:
        ordered_candidates = order_fundamentals_identifiers(identifiers)
        if not ordered_candidates:
            raise ValueError("At least one identifier is required for fundamentals refresh.")

        if self.primary_source_key == self.fallback_source_key:
            chosen_identifier = ordered_candidates[0]
            valuation = await self.primary_market_adapter.fetch_valuation_snapshot(
                chosen_identifier.composite_symbol
            )
            financials = list(
                await self.primary_market_adapter.fetch_financial_metrics(
                    chosen_identifier.composite_symbol
                )
            )
            return FetchedFundamentalsData(
                source_key=self.primary_source_key,
                valuation=valuation,
                financials=financials,
                used_fallback=False,
                lookup_symbol=chosen_identifier.composite_symbol,
                lookup_identifier_type=chosen_identifier.identifier_type.value,
                lookup_currency=chosen_identifier.currency,
            )

        best_real_result: tuple[StockIdentifier, ValuationRecord | None, list[FinancialMetricRecord]] | None = None
        best_real_score = -1

        for identifier in ordered_candidates:
            valuation, financials = await self._fetch_from_primary_provider(identifier.composite_symbol)
            score = _candidate_data_score(valuation, financials)
            if score == 3:
                return FetchedFundamentalsData(
                    source_key=self.primary_source_key,
                    valuation=valuation,
                    financials=financials,
                    used_fallback=False,
                    lookup_symbol=identifier.composite_symbol,
                    lookup_identifier_type=identifier.identifier_type.value,
                    lookup_currency=identifier.currency,
                )
            if score > best_real_score:
                best_real_result = (identifier, valuation, financials)
                best_real_score = score

        if best_real_result is not None and best_real_score > 0:
            identifier, valuation, financials = best_real_result
            return FetchedFundamentalsData(
                source_key=self.primary_source_key,
                valuation=valuation,
                financials=financials,
                used_fallback=False,
                lookup_symbol=identifier.composite_symbol,
                lookup_identifier_type=identifier.identifier_type.value,
                lookup_currency=identifier.currency,
            )

        fallback_identifier = ordered_candidates[0]
        logger.warning(
            "Primary fundamentals provider %s produced no usable data for %s, falling back to mock.",
            self.primary_source_key,
            fallback_identifier.composite_symbol,
        )
        valuation = await self.fallback_market_adapter.fetch_valuation_snapshot(
            fallback_identifier.composite_symbol
        )
        financials = list(
            await self.fallback_market_adapter.fetch_financial_metrics(
                fallback_identifier.composite_symbol
            )
        )
        return FetchedFundamentalsData(
            source_key=self.fallback_source_key,
            valuation=valuation,
            financials=financials,
            used_fallback=True,
            lookup_symbol=fallback_identifier.composite_symbol,
            lookup_identifier_type=fallback_identifier.identifier_type.value,
            lookup_currency=fallback_identifier.currency,
        )

    async def _fetch_from_primary_provider(
        self,
        symbol: str,
    ) -> tuple[ValuationRecord | None, list[FinancialMetricRecord]]:
        valuation: ValuationRecord | None = None
        financials: list[FinancialMetricRecord] = []

        try:
            valuation = await self.primary_market_adapter.fetch_valuation_snapshot(symbol)
        except Exception as exc:
            logger.warning(
                "Primary fundamentals valuation provider %s failed for %s: %s",
                self.primary_source_key,
                symbol,
                exc,
            )

        try:
            financials = list(await self.primary_market_adapter.fetch_financial_metrics(symbol))
        except Exception as exc:
            logger.warning(
                "Primary fundamentals financial provider %s failed for %s: %s",
                self.primary_source_key,
                symbol,
                exc,
            )

        return valuation, financials

    def _ingest_fundamentals(
        self,
        *,
        stock_id,
        primary_symbol: str,
        fetched: FetchedFundamentalsData,
        source_ids: dict[str, object],
        ingestion_runs: dict[str, dict[str, IngestionRun]],
    ) -> dict[str, int]:
        if self.session is None:
            raise RuntimeError("FundamentalsRefreshService requires a database session to ingest data.")

        source_id = source_ids[fetched.source_key]
        valuation_ingestion_run = ingestion_runs[fetched.source_key]["valuation_snapshots"]
        financial_ingestion_run = ingestion_runs[fetched.source_key]["financial_metrics"]
        managed_source_ids = list(source_ids.values())

        self.session.execute(
            delete(ValuationSnapshot).where(
                ValuationSnapshot.stock_id == stock_id,
                ValuationSnapshot.source_id.in_(managed_source_ids),
            )
        )
        self.session.execute(
            delete(FinancialMetric).where(
                FinancialMetric.stock_id == stock_id,
                FinancialMetric.source_id.in_(managed_source_ids),
            )
        )

        valuation_record = enrich_valuation_with_financials(
            fetched.valuation,
            fetched.financials,
            listing_currency=fetched.lookup_currency,
        )

        written = {"valuation_snapshots": 0, "financial_metrics": 0}
        valuation_ingestion_run.rows_read += 1 if valuation_record is not None else 0
        if valuation_record is not None:
            self.session.execute(
                insert(ValuationSnapshot)
                .values(
                    stock_id=stock_id,
                    source_id=source_id,
                    ingestion_run_id=valuation_ingestion_run.id,
                    as_of_date=valuation_record.as_of_date,
                    currency=valuation_record.currency,
                    market_cap=_to_decimal(valuation_record.market_cap),
                    pe_ttm=_to_decimal(valuation_record.pe_ttm),
                    pe_forward=_to_decimal(valuation_record.pe_forward),
                    pb=_to_decimal(valuation_record.pb),
                    ps_ttm=_to_decimal(valuation_record.ps_ttm),
                    enterprise_value=_to_decimal(valuation_record.enterprise_value),
                    ev_ebitda=_to_decimal(valuation_record.ev_ebitda),
                    dividend_yield=_to_decimal(valuation_record.dividend_yield),
                    raw_payload={
                        "symbol": primary_symbol,
                        "lookup_symbol": fetched.lookup_symbol,
                        "lookup_identifier_type": fetched.lookup_identifier_type,
                        "lookup_currency": fetched.lookup_currency,
                        "source_key": fetched.source_key,
                        "source_name": valuation_record.source_name,
                        "source_url": valuation_record.source_url,
                        **(valuation_record.raw_payload or {}),
                    },
                )
                .on_conflict_do_update(
                    index_elements=[
                        ValuationSnapshot.stock_id,
                        ValuationSnapshot.source_id,
                        ValuationSnapshot.as_of_date,
                    ],
                    set_={
                        "currency": valuation_record.currency,
                        "market_cap": _to_decimal(valuation_record.market_cap),
                        "pe_ttm": _to_decimal(valuation_record.pe_ttm),
                        "pe_forward": _to_decimal(valuation_record.pe_forward),
                        "pb": _to_decimal(valuation_record.pb),
                        "ps_ttm": _to_decimal(valuation_record.ps_ttm),
                        "enterprise_value": _to_decimal(valuation_record.enterprise_value),
                        "ev_ebitda": _to_decimal(valuation_record.ev_ebitda),
                        "dividend_yield": _to_decimal(valuation_record.dividend_yield),
                        "raw_payload": {
                            "symbol": primary_symbol,
                            "lookup_symbol": fetched.lookup_symbol,
                            "lookup_identifier_type": fetched.lookup_identifier_type,
                            "lookup_currency": fetched.lookup_currency,
                            "source_key": fetched.source_key,
                            "source_name": valuation_record.source_name,
                            "source_url": valuation_record.source_url,
                            **(valuation_record.raw_payload or {}),
                        },
                    },
                )
            )
            valuation_ingestion_run.rows_written += 1
            written["valuation_snapshots"] = 1

        financial_ingestion_run.rows_read += len(fetched.financials)
        for record in fetched.financials:
            self.session.execute(
                insert(FinancialMetric)
                .values(
                    stock_id=stock_id,
                    source_id=source_id,
                    ingestion_run_id=financial_ingestion_run.id,
                    period_type=FinancialPeriodType(record.period_type),
                    fiscal_year=record.fiscal_year,
                    fiscal_period=record.fiscal_period,
                    period_start=record.period_start,
                    period_end=record.period_end,
                    report_date=record.report_date,
                    currency=record.currency,
                    revenue=_to_decimal(record.revenue),
                    net_profit=_to_decimal(record.net_profit),
                    gross_margin=_to_decimal(record.gross_margin),
                    operating_margin=_to_decimal(record.operating_margin),
                    roe=_to_decimal(record.roe),
                    roa=_to_decimal(record.roa),
                    debt_to_equity=_to_decimal(record.debt_to_equity),
                    overseas_revenue_ratio=_to_decimal(record.overseas_revenue_ratio),
                    revenue_growth_yoy=_to_decimal(record.revenue_growth_yoy),
                    net_profit_growth_yoy=_to_decimal(record.net_profit_growth_yoy),
                    raw_payload={
                        "symbol": primary_symbol,
                        "lookup_symbol": fetched.lookup_symbol,
                        "lookup_identifier_type": fetched.lookup_identifier_type,
                        "lookup_currency": fetched.lookup_currency,
                        "source_key": fetched.source_key,
                        "source_name": record.source_name,
                        "source_url": record.source_url,
                        **(record.raw_payload or {}),
                    },
                )
                .on_conflict_do_update(
                    index_elements=[
                        FinancialMetric.stock_id,
                        FinancialMetric.source_id,
                        FinancialMetric.period_type,
                        FinancialMetric.fiscal_year,
                        FinancialMetric.fiscal_period,
                    ],
                    set_={
                        "period_start": record.period_start,
                        "period_end": record.period_end,
                        "report_date": record.report_date,
                        "currency": record.currency,
                        "revenue": _to_decimal(record.revenue),
                        "net_profit": _to_decimal(record.net_profit),
                        "gross_margin": _to_decimal(record.gross_margin),
                        "operating_margin": _to_decimal(record.operating_margin),
                        "roe": _to_decimal(record.roe),
                        "roa": _to_decimal(record.roa),
                        "debt_to_equity": _to_decimal(record.debt_to_equity),
                        "overseas_revenue_ratio": _to_decimal(record.overseas_revenue_ratio),
                        "revenue_growth_yoy": _to_decimal(record.revenue_growth_yoy),
                        "net_profit_growth_yoy": _to_decimal(record.net_profit_growth_yoy),
                        "raw_payload": {
                            "symbol": primary_symbol,
                            "lookup_symbol": fetched.lookup_symbol,
                            "lookup_identifier_type": fetched.lookup_identifier_type,
                            "lookup_currency": fetched.lookup_currency,
                            "source_key": fetched.source_key,
                            "source_name": record.source_name,
                            "source_url": record.source_url,
                            **(record.raw_payload or {}),
                        },
                    },
                )
            )
            written["financial_metrics"] += 1

        financial_ingestion_run.rows_written += written["financial_metrics"]
        self.session.flush()
        return written

    def _new_ingestion_run(self, refresh_job_id, source_id, dataset_name: str) -> IngestionRun:
        if self.session is None:
            raise RuntimeError("FundamentalsRefreshService requires a database session to create runs.")

        ingestion_run = IngestionRun(
            refresh_job_id=refresh_job_id,
            source_id=source_id,
            dataset_name=dataset_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
            parameters_json={"provider": self.settings.fundamentals_data_provider},
        )
        self.session.add(ingestion_run)
        self.session.flush()
        return ingestion_run

    def _identifier_candidates_for_stock(self, stock_id) -> list[StockIdentifier]:
        if self.session is None:
            raise RuntimeError("FundamentalsRefreshService requires a database session to load identifiers.")
        identifiers = self.session.scalars(
            select(StockIdentifier)
            .where(StockIdentifier.stock_id == stock_id)
            .order_by(StockIdentifier.is_primary.desc(), StockIdentifier.composite_symbol.asc())
        ).all()
        return order_fundamentals_identifiers(identifiers)


def build_fundamentals_adapter(settings: Settings) -> tuple[str, MarketDataAdapter]:
    provider = settings.fundamentals_data_provider.strip().lower()
    if provider in {"akshare", "real"}:
        return (
            AKSHARE_FUNDAMENTALS_SOURCE_KEY,
            AkshareFundamentalsAdapter(
                timeout_seconds=settings.fundamentals_request_timeout_seconds,
                max_retries=settings.fundamentals_request_max_retries,
            ),
        )
    return (MOCK_FUNDAMENTALS_SOURCE_KEY, MockMarketDataAdapter())


def enrich_valuation_with_financials(
    valuation: ValuationRecord | None,
    financials: list[FinancialMetricRecord],
    *,
    listing_currency: str | None,
) -> ValuationRecord | None:
    if valuation is None:
        return None

    latest_financial = latest_financial_metric(financials)
    effective_listing_currency = valuation.currency or listing_currency
    ps_ttm = valuation.ps_ttm
    derived_ps = False
    if (
        ps_ttm is None
        and valuation.market_cap is not None
        and latest_financial is not None
        and latest_financial.revenue is not None
        and latest_financial.revenue > 0
        and effective_listing_currency is not None
        and latest_financial.currency == effective_listing_currency
    ):
        ps_ttm = round(valuation.market_cap / latest_financial.revenue, 6)
        derived_ps = True

    raw_payload = dict(valuation.raw_payload or {})
    if derived_ps:
        raw_payload["derived_metrics"] = {
            "ps_ttm": {
                "formula": "market_cap / revenue",
                "listing_currency": effective_listing_currency,
                "revenue_period": latest_financial.fiscal_period if latest_financial else None,
                "revenue_report_date": latest_financial.report_date.isoformat()
                if latest_financial and latest_financial.report_date
                else None,
            }
        }

    return ValuationRecord(
        symbol=valuation.symbol,
        as_of_date=valuation.as_of_date,
        currency=effective_listing_currency,
        pe_ttm=valuation.pe_ttm,
        pe_forward=valuation.pe_forward,
        pb=valuation.pb,
        ps_ttm=ps_ttm,
        market_cap=valuation.market_cap,
        enterprise_value=valuation.enterprise_value,
        ev_ebitda=valuation.ev_ebitda,
        dividend_yield=valuation.dividend_yield,
        source_name=valuation.source_name,
        source_url=valuation.source_url,
        raw_payload=raw_payload,
    )


def latest_financial_metric(
    financials: list[FinancialMetricRecord],
) -> FinancialMetricRecord | None:
    if not financials:
        return None
    return max(
        financials,
        key=lambda item: (
            item.report_date,
            item.period_end,
            item.fiscal_year,
            item.fiscal_period,
        ),
    )


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def order_fundamentals_identifiers(
    identifiers: list[StockIdentifier],
) -> list[StockIdentifier]:
    return sorted(
        identifiers,
        key=lambda identifier: (
            _fundamentals_identifier_priority(identifier.identifier_type),
            0 if identifier.is_primary else 1,
            identifier.composite_symbol,
        ),
    )


def _fundamentals_identifier_priority(identifier_type: IdentifierType) -> int:
    if identifier_type == IdentifierType.A_SHARE:
        return 0
    if identifier_type == IdentifierType.H_SHARE:
        return 1
    return 2


def _candidate_data_score(
    valuation: ValuationRecord | None,
    financials: list[FinancialMetricRecord],
) -> int:
    if valuation is not None and financials:
        return 3
    if financials:
        return 2
    if valuation is not None:
        return 1
    return 0
