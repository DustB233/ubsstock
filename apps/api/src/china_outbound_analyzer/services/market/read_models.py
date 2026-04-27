from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import (
    AIArtifact,
    Announcement,
    DataSource,
    FinancialMetric,
    NewsItem,
    PriceBar,
    RecommendationItem,
    RecommendationRun,
    ScoringRun,
    Stock,
    StockIdentifier,
    StockNewsMention,
    StockScore,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import AIArtifactType
from china_outbound_analyzer.schemas.common import EmptyState, PricePoint
from china_outbound_analyzer.schemas.compare_views import (
    ComparisonHighlightsResponse,
    ComparisonRowResponse,
    ComparisonViewResponse,
)
from china_outbound_analyzer.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardRecommendationCardResponse,
    DashboardStockRowResponse,
)
from china_outbound_analyzer.schemas.recommendations import (
    RecommendationEvidenceBucketResponse,
    RecommendationItemResponse,
    RecommendationSnapshotResponse,
)
from china_outbound_analyzer.schemas.stock_views import (
    AnalysisEvidenceReferenceResponse,
    AnalysisFreshnessResponse,
    FactorScoreBreakdownResponse,
    FinancialSnapshotResponse,
    ReturnSnapshotResponse,
    StockAnalysisResponse,
    StockAnnouncementItemResponse,
    StockDetailViewResponse,
    StockIdentifierViewResponse,
    StockListViewResponse,
    StockNewsFeedResponse,
    StockNewsItemResponse,
    StockTimeseriesResponse,
    ValuationSnapshotResponse,
)
from china_outbound_analyzer.services.market.universe import UniverseService

RANGE_TO_DAYS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}
ANALYSIS_SCHEMA_VERSION = "analysis-v2"


@dataclass(frozen=True)
class StockReadBundle:
    stock: Stock
    primary_identifier: StockIdentifier
    identifiers: list[StockIdentifier]
    prices: list[PriceBar]
    returns: ReturnSnapshotResponse
    latest_price: float | None
    factor_scores: FactorScoreBreakdownResponse
    valuation: ValuationSnapshotResponse
    financial_snapshot: FinancialSnapshotResponse
    analysis: StockAnalysisResponse


class DashboardReadService:
    def __init__(self, session: Session):
        self.session = session

    def get_overview(self) -> DashboardOverviewResponse:
        scoring_run = self.session.scalars(
            select(ScoringRun)
            .order_by(ScoringRun.run_date.desc(), ScoringRun.created_at.desc())
            .limit(1)
        ).first()
        recommendation_run = self.session.scalars(
            select(RecommendationRun).order_by(RecommendationRun.created_at.desc()).limit(1)
        ).first()

        if scoring_run is None:
            return self._fallback_overview()

        stock_scores = self.session.scalars(
            select(StockScore)
            .where(StockScore.scoring_run_id == scoring_run.id)
            .order_by(StockScore.rank.asc())
        ).all()
        if not stock_scores:
            return self._fallback_overview()

        rows: list[DashboardStockRowResponse] = []
        for stock_score in stock_scores:
            stock = self.session.get(Stock, stock_score.stock_id)
            if stock is None:
                continue

            primary_identifier = self.session.scalars(
                select(StockIdentifier)
                .where(
                    StockIdentifier.stock_id == stock.id,
                    StockIdentifier.is_primary.is_(True),
                )
                .limit(1)
            ).first()
            valuation = self.session.scalars(
                select(ValuationSnapshot)
                .where(ValuationSnapshot.stock_id == stock.id)
                .order_by(ValuationSnapshot.as_of_date.desc())
                .limit(1)
            ).first()
            prices = (
                self.session.scalars(
                    select(PriceBar)
                    .where(PriceBar.identifier_id == primary_identifier.id)
                    .order_by(PriceBar.trading_date.asc())
                ).all()
                if primary_identifier is not None
                else []
            )
            latest_price = (
                float(prices[-1].close) if prices and prices[-1].close is not None else None
            )

            rows.append(
                DashboardStockRowResponse(
                    slug=stock.slug,
                    company_name=stock.company_name,
                    primary_symbol=(
                        primary_identifier.composite_symbol if primary_identifier else stock.slug
                    ),
                    sector=stock.sector,
                    latest_price=latest_price,
                    return_1m=self._compute_return(prices, 21),
                    return_3m=self._compute_return(prices, 63),
                    return_1y=self._compute_return(prices, 252),
                    pe_ttm=(
                        float(valuation.pe_ttm)
                        if valuation and valuation.pe_ttm is not None
                        else None
                    ),
                    pb=(float(valuation.pb) if valuation and valuation.pb is not None else None),
                    ps_ttm=(
                        float(valuation.ps_ttm)
                        if valuation and valuation.ps_ttm is not None
                        else None
                    ),
                    total_score=float(stock_score.total_score),
                    rank=stock_score.rank,
                )
            )

        return DashboardOverviewResponse(
            as_of_date=scoring_run.run_date,
            stocks=rows,
            recommendations=self._recommendation_cards(recommendation_run),
        )

    @staticmethod
    def _compute_return(prices: list[PriceBar], days: int) -> float | None:
        if len(prices) <= days:
            return None
        current = float(prices[-1].close or 0)
        prior = float(prices[-(days + 1)].close or 0)
        if prior == 0:
            return None
        return round((current / prior) - 1, 4)

    def _recommendation_cards(
        self,
        recommendation_run: RecommendationRun | None,
    ) -> list[DashboardRecommendationCardResponse]:
        if recommendation_run is None:
            return [
                DashboardRecommendationCardResponse(
                    side="LONG",
                    explanation="Run the analysis and scoring pipeline to populate the long idea.",
                ),
                DashboardRecommendationCardResponse(
                    side="SHORT",
                    explanation="Run the analysis and scoring pipeline to populate the short idea.",
                ),
            ]

        items = self.session.scalars(
            select(RecommendationItem)
            .where(RecommendationItem.recommendation_run_id == recommendation_run.id)
            .order_by(RecommendationItem.side.asc())
        ).all()
        if not items:
            return self._recommendation_cards(None)

        cards: list[DashboardRecommendationCardResponse] = []
        for item in items:
            stock = self.session.get(Stock, item.stock_id)
            total_score = (
                float(item.supporting_metrics.get("total_score"))
                if item.supporting_metrics
                and item.supporting_metrics.get("total_score") is not None
                else None
            )
            cards.append(
                DashboardRecommendationCardResponse(
                    side=item.side.value,
                    slug=stock.slug if stock else None,
                    company_name=stock.company_name if stock else None,
                    explanation=item.rationale_markdown,
                    total_score=total_score,
                )
            )

        return cards

    @staticmethod
    def _fallback_overview() -> DashboardOverviewResponse:
        universe = UniverseService().get_dashboard_preview()
        return DashboardOverviewResponse(
            as_of_date=None,
            stocks=[
                DashboardStockRowResponse(
                    slug=item.slug,
                    company_name=item.companyName,
                    primary_symbol=item.primarySymbol,
                    sector=item.sector,
                )
                for item in universe.universe
            ],
            recommendations=[
                DashboardRecommendationCardResponse(
                    side=item.side.upper(),
                    explanation=item.explanation,
                )
                for item in universe.recommendations
            ],
        )


class DatabaseMarketReadService:
    def __init__(self, session: Session):
        self.session = session
        self._latest_scoring_run: ScoringRun | None = None
        self._latest_scoring_run_loaded = False
        self._latest_recommendation_run: RecommendationRun | None = None
        self._latest_recommendation_run_loaded = False
        self._data_source_cache: dict[str, DataSource | None] = {}

    def list_stocks(self) -> list[StockListViewResponse]:
        stocks = self.session.scalars(select(Stock).order_by(Stock.company_name.asc())).all()
        responses: list[StockListViewResponse] = []
        for stock in stocks:
            identifiers = self._identifiers(stock.id)
            primary_identifier = self._primary_identifier(stock.id)
            responses.append(
                StockListViewResponse(
                    slug=stock.slug,
                    company_name=stock.company_name,
                    company_name_zh=stock.company_name_zh,
                    sector=stock.sector,
                    outbound_theme=stock.outbound_theme,
                    primary_symbol=(
                        primary_identifier.composite_symbol if primary_identifier else stock.slug
                    ),
                    identifiers=[self._identifier_view(identifier) for identifier in identifiers],
                    valuation=self._valuation_response(stock.id),
                    financial_snapshot=self._financial_snapshot_response(stock.id),
                )
            )
        return responses

    def get_stock_detail(self, symbol: str) -> StockDetailViewResponse | None:
        bundle = self._bundle_from_lookup(symbol)
        if bundle is None:
            return None

        return StockDetailViewResponse(
            slug=bundle.stock.slug,
            symbol=bundle.primary_identifier.composite_symbol,
            company_name=bundle.stock.company_name,
            company_name_zh=bundle.stock.company_name_zh,
            sector=bundle.stock.sector,
            outbound_theme=bundle.stock.outbound_theme,
            primary_symbol=bundle.primary_identifier.composite_symbol,
            latest_price=bundle.latest_price,
            returns=bundle.returns,
            factor_scores=bundle.factor_scores,
            valuation=bundle.valuation,
            financial_snapshot=bundle.financial_snapshot,
            identifiers=[self._identifier_view(identifier) for identifier in bundle.identifiers],
            announcements=self._announcement_items(bundle.stock.id),
        )

    def get_timeseries(self, symbol: str, range_key: str) -> StockTimeseriesResponse | None:
        bundle = self._bundle_from_lookup(symbol)
        if bundle is None:
            return None

        days = RANGE_TO_DAYS.get(range_key, RANGE_TO_DAYS["1y"])
        points = [
            PricePoint(
                trading_date=bar.trading_date,
                close=float(bar.close) if bar.close is not None else None,
                volume=bar.volume,
            )
            for bar in bundle.prices[-days:]
        ]

        return StockTimeseriesResponse(
            slug=bundle.stock.slug,
            symbol=bundle.primary_identifier.composite_symbol,
            range=range_key,
            points=points,
            empty_state=EmptyState(message="No timeseries data is available.")
            if not points
            else None,
        )

    def get_news(self, symbol: str) -> StockNewsFeedResponse | None:
        resolved = self._resolve_stock_and_primary_identifier(symbol)
        if resolved is None:
            return None
        stock, primary_identifier = resolved

        rows = self.session.execute(
            select(NewsItem)
            .join(StockNewsMention, StockNewsMention.news_item_id == NewsItem.id)
            .where(StockNewsMention.stock_id == stock.id)
            .order_by(NewsItem.published_at.desc(), NewsItem.created_at.desc())
            .limit(10)
        ).scalars().all()

        items = [
            StockNewsItemResponse(
                title=item.title,
                url=item.url,
                published_at=item.published_at,
                summary=item.summary,
                provider=item.provider,
                source_url=(item.raw_payload or {}).get("source_url"),
                sentiment_label=None,
            )
            for item in rows
        ]

        return StockNewsFeedResponse(
            slug=stock.slug,
            symbol=primary_identifier.composite_symbol,
            items=items,
            empty_state=EmptyState(message="No recent news is available.") if not items else None,
        )

    def get_analysis(self, symbol: str) -> StockAnalysisResponse | None:
        resolved = self._resolve_stock_and_primary_identifier(symbol)
        if resolved is None:
            return None
        stock, primary_identifier = resolved
        return self._analysis_response(stock, primary_identifier.composite_symbol)

    def compare(self, requested_symbols: list[str]) -> ComparisonViewResponse:
        bundles: list[StockReadBundle] = []
        seen_stock_ids: set[str] = set()

        if requested_symbols:
            for requested_symbol in requested_symbols:
                bundle = self._bundle_from_lookup(requested_symbol)
                if bundle is None or str(bundle.stock.id) in seen_stock_ids:
                    continue
                seen_stock_ids.add(str(bundle.stock.id))
                bundles.append(bundle)
        else:
            for bundle in self._default_compare_bundles():
                if str(bundle.stock.id) in seen_stock_ids:
                    continue
                seen_stock_ids.add(str(bundle.stock.id))
                bundles.append(bundle)

        rows = [
            ComparisonRowResponse(
                slug=bundle.stock.slug,
                symbol=bundle.primary_identifier.composite_symbol,
                company_name=bundle.stock.company_name,
                sector=bundle.stock.sector,
                factor_scores=bundle.factor_scores,
                valuation=bundle.valuation,
                financial_snapshot=bundle.financial_snapshot,
                sentiment_label=bundle.analysis.sentiment_label,
                sentiment_score=bundle.analysis.sentiment_score,
            )
            for bundle in bundles
        ]

        ranked = [row for row in rows if row.factor_scores.total_score is not None]
        ranked.sort(key=lambda row: row.factor_scores.total_score or 0, reverse=True)

        highlights = ComparisonHighlightsResponse()
        if ranked:
            highlights = ComparisonHighlightsResponse(
                most_attractive_symbol=ranked[0].symbol,
                most_attractive_name=ranked[0].company_name,
                least_attractive_symbol=ranked[-1].symbol,
                least_attractive_name=ranked[-1].company_name,
            )

        return ComparisonViewResponse(
            requested_symbols=requested_symbols,
            rows=rows,
            highlights=highlights,
        )

    def get_recommendation_snapshot(self) -> RecommendationSnapshotResponse:
        recommendation_run = self._latest_recommendation_run_row()
        if recommendation_run is None:
            methodology_version = self._latest_scoring_run_row().methodology_version if self._latest_scoring_run_row() else "transparent-v1"
            return RecommendationSnapshotResponse(
                methodology_version=methodology_version,
                generated_at=None,
                items=[],
            )

        scoring_run = self.session.get(ScoringRun, recommendation_run.scoring_run_id)
        items = self.session.scalars(
            select(RecommendationItem)
            .where(RecommendationItem.recommendation_run_id == recommendation_run.id)
            .order_by(RecommendationItem.side.asc())
        ).all()

        responses: list[RecommendationItemResponse] = []
        for item in items:
            stock = self.session.get(Stock, item.stock_id)
            if stock is None:
                continue
            bundle = self._bundle_for_stock(stock)
            if bundle is None:
                continue
            responses.append(self._recommendation_item_response(item, bundle))

        return RecommendationSnapshotResponse(
            methodology_version=(
                scoring_run.methodology_version if scoring_run is not None else "transparent-v1"
            ),
            generated_at=recommendation_run.created_at,
            items=responses,
        )

    def _bundle_from_lookup(self, symbol: str) -> StockReadBundle | None:
        resolved = self._resolve_stock_and_primary_identifier(symbol)
        if resolved is None:
            return None
        stock, _primary_identifier = resolved
        return self._bundle_for_stock(stock)

    def _bundle_for_stock(self, stock: Stock) -> StockReadBundle | None:
        primary_identifier = self._primary_identifier(stock.id)
        if primary_identifier is None:
            return None
        identifiers = self._identifiers(stock.id)
        prices = self._price_series(primary_identifier.id)
        latest_price = float(prices[-1].close) if prices and prices[-1].close is not None else None
        returns = ReturnSnapshotResponse(
            return_1m=DashboardReadService._compute_return(prices, 21),
            return_3m=DashboardReadService._compute_return(prices, 63),
            return_6m=DashboardReadService._compute_return(prices, 126),
            return_1y=DashboardReadService._compute_return(prices, 252),
        )
        return StockReadBundle(
            stock=stock,
            primary_identifier=primary_identifier,
            identifiers=identifiers,
            prices=prices,
            returns=returns,
            latest_price=latest_price,
            factor_scores=self._factor_scores(stock.id),
            valuation=self._valuation_response(stock.id),
            financial_snapshot=self._financial_snapshot_response(stock.id),
            analysis=self._analysis_response(stock, primary_identifier.composite_symbol),
        )

    def _resolve_stock_and_primary_identifier(
        self,
        symbol: str,
    ) -> tuple[Stock, StockIdentifier] | None:
        normalized = symbol.strip().lower()
        identifier = self.session.scalars(
            select(StockIdentifier)
            .where(func.lower(StockIdentifier.composite_symbol) == normalized)
            .limit(1)
        ).first()
        if identifier is not None:
            stock = self.session.get(Stock, identifier.stock_id)
            primary_identifier = self._primary_identifier(identifier.stock_id)
            if stock is not None and primary_identifier is not None:
                return stock, primary_identifier

        stock = self.session.scalars(
            select(Stock).where(func.lower(Stock.slug) == normalized).limit(1)
        ).first()
        if stock is None:
            return None
        primary_identifier = self._primary_identifier(stock.id)
        if primary_identifier is None:
            return None
        return stock, primary_identifier

    def _identifiers(self, stock_id) -> list[StockIdentifier]:
        return self.session.scalars(
            select(StockIdentifier)
            .where(StockIdentifier.stock_id == stock_id)
            .order_by(StockIdentifier.is_primary.desc(), StockIdentifier.composite_symbol.asc())
        ).all()

    def _primary_identifier(self, stock_id) -> StockIdentifier | None:
        return self.session.scalars(
            select(StockIdentifier)
            .where(
                StockIdentifier.stock_id == stock_id,
                StockIdentifier.is_primary.is_(True),
            )
            .limit(1)
        ).first()

    def _price_series(self, identifier_id) -> list[PriceBar]:
        source_id = self.session.execute(
            select(PriceBar.source_id)
            .where(PriceBar.identifier_id == identifier_id)
            .order_by(PriceBar.created_at.desc(), PriceBar.trading_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if source_id is None:
            return []
        return self.session.scalars(
            select(PriceBar)
            .where(PriceBar.identifier_id == identifier_id, PriceBar.source_id == source_id)
            .order_by(PriceBar.trading_date.asc())
        ).all()

    def _factor_scores(self, stock_id) -> FactorScoreBreakdownResponse:
        scoring_run = self._latest_scoring_run_row()
        if scoring_run is None:
            return FactorScoreBreakdownResponse()
        stock_score = self.session.scalars(
            select(StockScore)
            .where(
                StockScore.scoring_run_id == scoring_run.id,
                StockScore.stock_id == stock_id,
            )
            .limit(1)
        ).first()
        if stock_score is None:
            return FactorScoreBreakdownResponse()

        return FactorScoreBreakdownResponse(
            fundamentals_quality=float(stock_score.fundamentals_score),
            valuation_attractiveness=float(stock_score.valuation_score),
            price_momentum=float(stock_score.momentum_score),
            news_sentiment=float(stock_score.sentiment_score),
            globalization_strength=float(stock_score.globalization_score),
            total_score=float(stock_score.total_score),
            rank=stock_score.rank,
        )

    def _valuation_response(self, stock_id) -> ValuationSnapshotResponse:
        valuation = self.session.scalars(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.stock_id == stock_id)
            .order_by(ValuationSnapshot.as_of_date.desc(), ValuationSnapshot.created_at.desc())
            .limit(1)
        ).first()
        if valuation is None:
            return ValuationSnapshotResponse()
        source = self._data_source(valuation.source_id)
        raw_payload = valuation.raw_payload or {}
        return ValuationSnapshotResponse(
            currency=valuation.currency or raw_payload.get("snapshot_currency") or raw_payload.get("currency"),
            market_cap=float(valuation.market_cap) if valuation.market_cap is not None else None,
            pe_ttm=float(valuation.pe_ttm) if valuation.pe_ttm is not None else None,
            pe_forward=float(valuation.pe_forward) if valuation.pe_forward is not None else None,
            pb=float(valuation.pb) if valuation.pb is not None else None,
            ps_ttm=float(valuation.ps_ttm) if valuation.ps_ttm is not None else None,
            enterprise_value=(
                float(valuation.enterprise_value) if valuation.enterprise_value is not None else None
            ),
            ev_ebitda=float(valuation.ev_ebitda) if valuation.ev_ebitda is not None else None,
            dividend_yield=(
                float(valuation.dividend_yield) if valuation.dividend_yield is not None else None
            ),
            as_of_date=valuation.as_of_date,
            source=raw_payload.get("source_name") or (source.display_name if source else None),
            source_url=raw_payload.get("source_url") or (source.base_url if source else None),
        )

    def _financial_snapshot_response(self, stock_id) -> FinancialSnapshotResponse:
        metric = self.session.scalars(
            select(FinancialMetric)
            .where(FinancialMetric.stock_id == stock_id)
            .order_by(
                FinancialMetric.report_date.desc(),
                FinancialMetric.period_end.desc(),
                FinancialMetric.created_at.desc(),
            )
            .limit(1)
        ).first()
        if metric is None:
            return FinancialSnapshotResponse()
        source = self._data_source(metric.source_id)
        raw_payload = metric.raw_payload or {}
        return FinancialSnapshotResponse(
            as_of_date=metric.report_date,
            report_date=metric.report_date,
            report_period=_report_period(metric.fiscal_period, metric.fiscal_year),
            fiscal_year=metric.fiscal_year,
            fiscal_period=metric.fiscal_period,
            currency=metric.currency,
            revenue=float(metric.revenue) if metric.revenue is not None else None,
            net_income=float(metric.net_profit) if metric.net_profit is not None else None,
            net_profit=float(metric.net_profit) if metric.net_profit is not None else None,
            gross_margin=float(metric.gross_margin) if metric.gross_margin is not None else None,
            operating_margin=(
                float(metric.operating_margin) if metric.operating_margin is not None else None
            ),
            roe=float(metric.roe) if metric.roe is not None else None,
            roa=float(metric.roa) if metric.roa is not None else None,
            debt_to_equity=(
                float(metric.debt_to_equity) if metric.debt_to_equity is not None else None
            ),
            overseas_revenue_ratio=(
                float(metric.overseas_revenue_ratio)
                if metric.overseas_revenue_ratio is not None
                else None
            ),
            revenue_growth_yoy=(
                float(metric.revenue_growth_yoy) if metric.revenue_growth_yoy is not None else None
            ),
            net_income_growth_yoy=(
                float(metric.net_profit_growth_yoy)
                if metric.net_profit_growth_yoy is not None
                else None
            ),
            net_profit_growth_yoy=(
                float(metric.net_profit_growth_yoy)
                if metric.net_profit_growth_yoy is not None
                else None
            ),
            source=raw_payload.get("source_name") or (source.display_name if source else None),
            source_url=raw_payload.get("source_url") or (source.base_url if source else None),
        )

    def _analysis_response(self, stock: Stock, primary_symbol: str) -> StockAnalysisResponse:
        artifact = self.session.scalars(
            select(AIArtifact)
            .where(
                AIArtifact.stock_id == stock.id,
                AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY,
            )
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()
        if artifact is None or not artifact.structured_payload:
            return self._empty_analysis(stock.slug, primary_symbol)

        payload = self._empty_analysis(stock.slug, primary_symbol).model_dump(mode="json")
        payload.update(artifact.structured_payload)
        artifact_source_links = artifact.source_links if isinstance(artifact.source_links, dict) else {}
        payload["slug"] = stock.slug
        payload["symbol"] = primary_symbol
        payload["schema_version"] = payload.get("schema_version") or ANALYSIS_SCHEMA_VERSION
        payload["generated_at"] = payload.get("generated_at") or artifact.generated_at
        payload["analysis_mode"] = payload.get("analysis_mode")
        payload["model_provider"] = payload.get("model_provider") or artifact.model_provider
        payload["model_name"] = payload.get("model_name") or artifact.model_name
        payload["prompt_version"] = payload.get("prompt_version") or artifact.prompt_version
        payload["missing_inputs"] = payload.get("missing_inputs") or []
        payload["freshness"] = payload.get("freshness") or {}
        payload["source_links"] = payload.get("source_links") or artifact_source_links.get("urls") or []
        payload["source_references"] = (
            payload.get("source_references")
            or artifact_source_links.get("references")
            or []
        )

        return StockAnalysisResponse.model_validate(payload)

    def _announcement_items(self, stock_id) -> list[StockAnnouncementItemResponse]:
        rows = self.session.scalars(
            select(Announcement)
            .where(Announcement.stock_id == stock_id)
            .order_by(Announcement.published_at.desc(), Announcement.created_at.desc())
            .limit(8)
        ).all()

        items: list[StockAnnouncementItemResponse] = []
        for row in rows:
            source = self._data_source(row.source_id)
            raw_payload = row.raw_payload or {}
            items.append(
                StockAnnouncementItemResponse(
                    title=row.title,
                    url=row.url,
                    published_at=row.published_at,
                    as_of_date=row.as_of_date,
                    summary=row.summary,
                    provider=row.provider or raw_payload.get("source_name") or (source.display_name if source else None),
                    source_url=row.raw_payload.get("source_url") if row.raw_payload else (source.base_url if source else None),
                    exchange_code=row.exchange_code or raw_payload.get("exchange_code"),
                    category=row.category,
                    language=row.language or raw_payload.get("language"),
                )
            )
        return items

    def _empty_analysis(self, slug: str, symbol: str) -> StockAnalysisResponse:
        return StockAnalysisResponse(
            slug=slug,
            symbol=symbol,
            schema_version=ANALYSIS_SCHEMA_VERSION,
            generated_at=None,
            analysis_mode=None,
            model_provider=None,
            model_name=None,
            prompt_version=None,
            missing_inputs=[],
            freshness=AnalysisFreshnessResponse(),
            summary="",
            summary_evidence=[],
            top_news_themes=[],
            valuation_summary="",
            valuation_evidence=[],
            bull_case="",
            bull_case_evidence=[],
            bear_case="",
            bear_case_evidence=[],
            key_risks=[],
            risk_evidence=[],
            keywords=[],
            keyword_insights=[],
            sentiment_label=None,
            sentiment_score=None,
            sentiment_evidence=[],
            source_references=[],
            source_links=[],
        )

    def _recommendation_item_response(
        self,
        item: RecommendationItem,
        bundle: StockReadBundle,
    ) -> RecommendationItemResponse:
        key_risks = []
        if item.key_risks and isinstance(item.key_risks, dict):
            key_risks = [str(risk) for risk in item.key_risks.get("risks", [])]
        if not key_risks:
            key_risks = bundle.analysis.key_risks

        source_links = []
        if item.source_links and isinstance(item.source_links, dict):
            source_links = [str(url) for url in item.source_links.get("urls", [])]
        if not source_links:
            source_links = bundle.analysis.source_links

        return RecommendationItemResponse(
            side=item.side.value,
            slug=bundle.stock.slug,
            symbol=bundle.primary_identifier.composite_symbol,
            company_name=bundle.stock.company_name,
            company_name_zh=bundle.stock.company_name_zh,
            sector=bundle.stock.sector,
            outbound_theme=bundle.stock.outbound_theme,
            explanation=item.rationale_markdown,
            confidence_score=(
                float(item.confidence_score) if item.confidence_score is not None else None
            ),
            latest_price=bundle.latest_price,
            returns=bundle.returns,
            factor_scores=bundle.factor_scores,
            valuation=bundle.valuation,
            financial_snapshot=bundle.financial_snapshot,
            evidence_buckets=self._recommendation_evidence_buckets(bundle),
            analysis=bundle.analysis,
            key_risks=key_risks,
            source_links=source_links,
        )

    def _recommendation_evidence_buckets(
        self,
        bundle: StockReadBundle,
    ) -> list[RecommendationEvidenceBucketResponse]:
        analysis = bundle.analysis
        growth_references = self._metric_references(
            analysis,
            {"revenue_growth_yoy", "net_profit_growth_yoy", "gross_margin", "roe"},
        )

        return [
            RecommendationEvidenceBucketResponse(
                key="valuation",
                title="Valuation evidence",
                summary=analysis.valuation_summary,
                references=analysis.valuation_evidence,
            ),
            RecommendationEvidenceBucketResponse(
                key="growth",
                title="Growth evidence",
                summary=(
                    f"Revenue growth {self._format_percent(bundle.financial_snapshot.revenue_growth_yoy)}, "
                    f"net profit growth {self._format_percent(bundle.financial_snapshot.net_profit_growth_yoy)}, "
                    f"gross margin {self._format_percent(bundle.financial_snapshot.gross_margin)}, "
                    f"and ROE {self._format_percent(bundle.financial_snapshot.roe)}."
                ),
                references=growth_references,
            ),
            RecommendationEvidenceBucketResponse(
                key="momentum",
                title="Momentum evidence",
                summary=(
                    f"Recent price action shows 1M {self._format_percent(bundle.returns.return_1m)}, "
                    f"3M {self._format_percent(bundle.returns.return_3m)}, and "
                    f"1Y {self._format_percent(bundle.returns.return_1y)} performance."
                ),
                references=self._momentum_references(bundle),
            ),
            RecommendationEvidenceBucketResponse(
                key="sentiment",
                title="Sentiment evidence",
                summary=(
                    f"AI sentiment is {analysis.sentiment_label.lower() if analysis.sentiment_label else 'unavailable'} "
                    f"at {analysis.sentiment_score:.2f}." if analysis.sentiment_score is not None else "No stored AI sentiment summary is available yet."
                ),
                references=self._dedupe_references(
                    analysis.sentiment_evidence
                    + [
                        reference
                        for theme in analysis.top_news_themes[:2]
                        for reference in theme.evidence[:1]
                    ]
                ),
            ),
            RecommendationEvidenceBucketResponse(
                key="globalization",
                title="Outbound / globalization evidence",
                summary=(
                    f"{bundle.stock.outbound_theme} The globalization factor score is "
                    f"{bundle.factor_scores.globalization_strength:.1f}."
                ) if bundle.factor_scores.globalization_strength is not None else bundle.stock.outbound_theme,
                references=self._globalization_references(bundle),
            ),
        ]

    def _default_compare_bundles(self) -> list[StockReadBundle]:
        scoring_run = self._latest_scoring_run_row()
        if scoring_run is not None:
            scores = self.session.scalars(
                select(StockScore)
                .where(StockScore.scoring_run_id == scoring_run.id)
                .order_by(StockScore.rank.asc())
                .limit(3)
            ).all()
            bundles = [
                self._bundle_for_stock(stock)
                for stock in [self.session.get(Stock, score.stock_id) for score in scores]
                if stock is not None
            ]
            return [bundle for bundle in bundles if bundle is not None]

        stocks = self.session.scalars(select(Stock).order_by(Stock.company_name.asc()).limit(3)).all()
        bundles = [self._bundle_for_stock(stock) for stock in stocks]
        return [bundle for bundle in bundles if bundle is not None]

    def _metric_references(
        self,
        analysis: StockAnalysisResponse,
        keys: set[str],
    ) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            reference
            for reference in analysis.source_references
            if reference.reference_type == "metric" and reference.metric_key in keys
        ]

    @staticmethod
    def _momentum_references(bundle: StockReadBundle) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_1m",
                reference_type="metric",
                label="1M Return",
                metric_key="return_1m",
                metric_value=round(bundle.returns.return_1m or 0, 4)
                if bundle.returns.return_1m is not None
                else None,
                metric_unit="ratio",
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_3m",
                reference_type="metric",
                label="3M Return",
                metric_key="return_3m",
                metric_value=round(bundle.returns.return_3m or 0, 4)
                if bundle.returns.return_3m is not None
                else None,
                metric_unit="ratio",
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_1y",
                reference_type="metric",
                label="1Y Return",
                metric_key="return_1y",
                metric_value=round(bundle.returns.return_1y or 0, 4)
                if bundle.returns.return_1y is not None
                else None,
                metric_unit="ratio",
            ),
        ]

    @staticmethod
    def _globalization_references(bundle: StockReadBundle) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:outbound_theme",
                reference_type="metric",
                label="Outbound Theme",
                metric_key="outbound_theme",
                metric_value=bundle.stock.outbound_theme,
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:listing_count",
                reference_type="metric",
                label="Listing Breadth",
                metric_key="listing_count",
                metric_value=len(bundle.identifiers),
            ),
        ]

    @staticmethod
    def _dedupe_references(
        references: list[AnalysisEvidenceReferenceResponse],
    ) -> list[AnalysisEvidenceReferenceResponse]:
        deduped: list[AnalysisEvidenceReferenceResponse] = []
        seen: set[str] = set()
        for reference in references:
            if reference.reference_id in seen:
                continue
            seen.add(reference.reference_id)
            deduped.append(reference)
        return deduped

    @staticmethod
    def _identifier_view(identifier: StockIdentifier) -> StockIdentifierViewResponse:
        return StockIdentifierViewResponse(
            exchange_code=identifier.exchange_code,
            composite_symbol=identifier.composite_symbol,
            identifier_type=identifier.identifier_type.value,
            currency=identifier.currency,
            is_primary=identifier.is_primary,
        )

    @staticmethod
    def _format_percent(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value * 100:.1f}%"

    def _latest_scoring_run_row(self) -> ScoringRun | None:
        if not self._latest_scoring_run_loaded:
            self._latest_scoring_run = self.session.scalars(
                select(ScoringRun)
                .order_by(ScoringRun.run_date.desc(), ScoringRun.created_at.desc())
                .limit(1)
            ).first()
            self._latest_scoring_run_loaded = True
        return self._latest_scoring_run

    def _latest_recommendation_run_row(self) -> RecommendationRun | None:
        if not self._latest_recommendation_run_loaded:
            self._latest_recommendation_run = self.session.scalars(
                select(RecommendationRun)
                .order_by(RecommendationRun.created_at.desc())
                .limit(1)
            ).first()
            self._latest_recommendation_run_loaded = True
        return self._latest_recommendation_run

    def _data_source(self, source_id) -> DataSource | None:
        cache_key = str(source_id)
        if cache_key not in self._data_source_cache:
            self._data_source_cache[cache_key] = self.session.get(DataSource, source_id)
        return self._data_source_cache[cache_key]


def _report_period(fiscal_period: str | None, fiscal_year: int | None) -> str | None:
    if fiscal_period is None and fiscal_year is None:
        return None
    if fiscal_period is None:
        return str(fiscal_year)
    if fiscal_year is None:
        return fiscal_period
    return f"{fiscal_period} {fiscal_year}"
