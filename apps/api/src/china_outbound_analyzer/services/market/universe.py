from china_outbound_analyzer.schemas.common import EmptyState
from china_outbound_analyzer.schemas.compare import ComparisonMetricDefinition, ComparisonResponse
from china_outbound_analyzer.schemas.recommendations import (
    RecommendationItemResponse,
    RecommendationSnapshotResponse,
)
from china_outbound_analyzer.schemas.stocks import (
    DashboardPreviewResponse,
    PriceHistoryResponse,
    RecommendationPreviewResponse,
    StockAnnouncementResponse,
    StockDetailResponse,
    StockIdentifierResponse,
    StockListItemResponse,
    StockNewsResponse,
    UniverseStockCardResponse,
)
from china_outbound_analyzer.seeds.universe import UNIVERSE, IdentifierSeed, StockUniverseSeed

COMPARISON_METRICS = [
    ComparisonMetricDefinition(key="pe", label="PE", category="valuation"),
    ComparisonMetricDefinition(key="pb", label="PB", category="valuation"),
    ComparisonMetricDefinition(key="ps", label="PS", category="valuation"),
    ComparisonMetricDefinition(
        key="revenue_growth", label="Revenue Growth", category="fundamentals"
    ),
    ComparisonMetricDefinition(
        key="net_profit_growth", label="Net Profit Growth", category="fundamentals"
    ),
    ComparisonMetricDefinition(key="roe", label="ROE", category="fundamentals"),
    ComparisonMetricDefinition(key="gross_margin", label="Gross Margin", category="fundamentals"),
    ComparisonMetricDefinition(key="momentum", label="Momentum", category="market"),
    ComparisonMetricDefinition(key="sentiment", label="Sentiment", category="ai"),
]


class UniverseService:
    def list_stocks(self) -> list[StockListItemResponse]:
        return [self._to_stock_list_item(stock) for stock in UNIVERSE]

    def get_stock_detail(self, slug: str) -> StockDetailResponse | None:
        stock = next((item for item in UNIVERSE if item.slug == slug), None)
        if stock is None:
            return None

        identifiers = [self._to_identifier(identifier) for identifier in stock.identifiers]

        return StockDetailResponse(
            slug=stock.slug,
            company_name=stock.company_name,
            company_name_zh=stock.company_name_zh,
            sector=stock.sector,
            outbound_theme=stock.outbound_theme,
            identifiers=identifiers,
            valuation_metrics=[],
            financial_metrics=[],
            ai_summary="AI summary pipeline will populate this field after Phase 3 processing.",
            bull_case="Bull case generation will merge valuation, momentum, and globalization evidence.",
            bear_case="Bear case generation will surface downside drivers and adverse sentiment clusters.",
            key_risks=[
                "Live data ingestion is not connected yet.",
                "Recommendation engine is still pending Phase 4 scoring logic.",
            ],
            announcements=[],
            news=[],
        )

    def get_dashboard_preview(self) -> DashboardPreviewResponse:
        return DashboardPreviewResponse(
            universe=[
                UniverseStockCardResponse(
                    slug=stock.slug,
                    companyName=stock.company_name,
                    primarySymbol=next(
                        identifier.composite_symbol
                        for identifier in stock.identifiers
                        if identifier.is_primary
                    ),
                    exchanges=[identifier.exchange_code for identifier in stock.identifiers],
                    sector=stock.sector,
                    geographyAngle=stock.outbound_theme,
                )
                for stock in UNIVERSE
            ],
            recommendations=[
                RecommendationPreviewResponse(
                    side="long",
                    title="Long candidate placeholder",
                    explanation="The API contract is ready; the final long idea will appear after scoring runs are implemented.",
                ),
                RecommendationPreviewResponse(
                    side="short",
                    title="Short candidate placeholder",
                    explanation="The short idea will be backed by factor scores, source links, and traceable AI reasoning.",
                ),
            ],
        )

    def get_price_history(self, slug: str) -> PriceHistoryResponse | None:
        if not any(stock.slug == slug for stock in UNIVERSE):
            return None

        return PriceHistoryResponse(
            slug=slug,
            interval="1d",
            points=[],
            empty_state=EmptyState(message="Historical price ingestion arrives in Phase 2."),
        )

    def get_news(self, slug: str) -> StockNewsResponse | None:
        if not any(stock.slug == slug for stock in UNIVERSE):
            return None

        return StockNewsResponse(
            slug=slug,
            items=[],
            empty_state=EmptyState(message="News ingestion and clustering arrive in Phase 3."),
        )

    def get_announcements(self, slug: str) -> StockAnnouncementResponse | None:
        if not any(stock.slug == slug for stock in UNIVERSE):
            return None

        return StockAnnouncementResponse(
            slug=slug,
            items=[],
            empty_state=EmptyState(message="Announcement ingestion adapters arrive in Phase 2."),
        )

    def get_comparison(self, requested_slugs: list[str]) -> ComparisonResponse:
        selected = [
            stock for stock in UNIVERSE if not requested_slugs or stock.slug in requested_slugs
        ]
        return ComparisonResponse(
            requested_slugs=requested_slugs,
            metrics=COMPARISON_METRICS,
            rows=[
                {
                    "slug": stock.slug,
                    "company_name": stock.company_name,
                    "metrics": {metric.key: None for metric in COMPARISON_METRICS},
                }
                for stock in selected
            ],
        )

    def get_recommendation_snapshot(self) -> RecommendationSnapshotResponse:
        return RecommendationSnapshotResponse(
            methodology_version="draft-v1",
            items=[
                RecommendationItemResponse(
                    side="LONG",
                    explanation=(
                        "Final long recommendation will be selected from the ranked universe "
                        "in Phase 4."
                    ),
                    supporting_metrics={
                        "fundamentals_quality_weight": 0.25,
                        "valuation_attractiveness_weight": 0.25,
                    },
                    source_links=[],
                ),
                RecommendationItemResponse(
                    side="SHORT",
                    explanation=(
                        "Final short recommendation will be selected from the ranked universe "
                        "in Phase 4."
                    ),
                    supporting_metrics={
                        "news_sentiment_weight": 0.20,
                        "globalization_strength_weight": 0.15,
                    },
                    source_links=[],
                ),
            ],
        )

    @staticmethod
    def _to_identifier(identifier: IdentifierSeed) -> StockIdentifierResponse:
        return StockIdentifierResponse(
            exchange_code=identifier.exchange_code,
            composite_symbol=identifier.composite_symbol,
            identifier_type=identifier.identifier_type,
            currency=identifier.currency,
            is_primary=identifier.is_primary,
        )

    def _to_stock_list_item(self, stock: StockUniverseSeed) -> StockListItemResponse:
        return StockListItemResponse(
            slug=stock.slug,
            company_name=stock.company_name,
            company_name_zh=stock.company_name_zh,
            sector=stock.sector,
            outbound_theme=stock.outbound_theme,
            identifiers=[self._to_identifier(identifier) for identifier in stock.identifiers],
        )
