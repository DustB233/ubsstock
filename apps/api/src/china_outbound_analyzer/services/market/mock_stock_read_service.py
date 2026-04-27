from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from china_outbound_analyzer.schemas.common import EmptyState, PricePoint
from china_outbound_analyzer.schemas.compare_views import (
    ComparisonHighlightsResponse,
    ComparisonRowResponse,
    ComparisonViewResponse,
)
from china_outbound_analyzer.schemas.recommendations import (
    RecommendationEvidenceBucketResponse,
    RecommendationItemResponse,
    RecommendationSnapshotResponse,
)
from china_outbound_analyzer.schemas.stock_views import (
    AnalysisEvidenceReferenceResponse,
    FactorScoreBreakdownResponse,
    FinancialSnapshotResponse,
    ReturnSnapshotResponse,
    StockAnalysisResponse,
    StockDetailViewResponse,
    StockIdentifierViewResponse,
    StockListViewResponse,
    StockNewsFeedResponse,
    StockNewsItemResponse,
    StockTimeseriesResponse,
    ValuationSnapshotResponse,
)
from china_outbound_analyzer.seeds.universe import UNIVERSE, IdentifierSeed, StockUniverseSeed
from china_outbound_analyzer.services.ai.competition_artifacts import (
    build_stock_analysis_response,
)
from china_outbound_analyzer.services.ingestion.mock_adapters import (
    MockMarketDataAdapter,
    MockNewsAdapter,
)
from china_outbound_analyzer.services.recommendation.scoring import (
    percentile_rank_map,
    weighted_total,
)

RANGE_TO_DAYS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}
POSITIVE_HINTS = {"accelerates", "demand", "improves", "stabilizes", "strengthens"}
NEGATIVE_HINTS = {"caution", "competition", "intensifies"}


@dataclass(frozen=True)
class MockSnapshot:
    stock: StockUniverseSeed
    primary_identifier: IdentifierSeed
    latest_price: float | None
    returns: ReturnSnapshotResponse
    factor_scores: FactorScoreBreakdownResponse
    valuation: ValuationSnapshotResponse
    financial_snapshot: FinancialSnapshotResponse
    sentiment_label: str
    sentiment_score: float
    keywords: list[str]
    ai_summary: str
    valuation_summary: str
    bull_case: str
    bear_case: str
    key_risks: list[str]
    analysis: StockAnalysisResponse
    news_items: list[StockNewsItemResponse]
    timeseries_points: list[PricePoint]


class MockStockReadService:
    def __init__(self) -> None:
        self.market_adapter = MockMarketDataAdapter()
        self.news_adapter = MockNewsAdapter()

    async def list_stocks(self) -> list[StockListViewResponse]:
        return [
            StockListViewResponse(
                slug=stock.slug,
                company_name=stock.company_name,
                company_name_zh=stock.company_name_zh,
                sector=stock.sector,
                outbound_theme=stock.outbound_theme,
                primary_symbol=self._primary_identifier(stock).composite_symbol,
                identifiers=[self._identifier_view(identifier) for identifier in stock.identifiers],
            )
            for stock in UNIVERSE
        ]

    async def get_stock_detail(self, symbol: str) -> StockDetailViewResponse | None:
        snapshot = await self._get_snapshot(symbol)
        if snapshot is None:
            return None

        return StockDetailViewResponse(
            slug=snapshot.stock.slug,
            symbol=snapshot.primary_identifier.composite_symbol,
            company_name=snapshot.stock.company_name,
            company_name_zh=snapshot.stock.company_name_zh,
            sector=snapshot.stock.sector,
            outbound_theme=snapshot.stock.outbound_theme,
            primary_symbol=snapshot.primary_identifier.composite_symbol,
            latest_price=snapshot.latest_price,
            returns=snapshot.returns,
            factor_scores=snapshot.factor_scores,
            valuation=snapshot.valuation,
            financial_snapshot=snapshot.financial_snapshot,
            identifiers=[
                self._identifier_view(identifier) for identifier in snapshot.stock.identifiers
            ],
        )

    async def get_timeseries(
        self,
        symbol: str,
        range_key: str,
    ) -> StockTimeseriesResponse | None:
        snapshot = await self._get_snapshot(symbol)
        if snapshot is None:
            return None

        points = snapshot.timeseries_points[-RANGE_TO_DAYS[range_key] :]
        return StockTimeseriesResponse(
            slug=snapshot.stock.slug,
            symbol=snapshot.primary_identifier.composite_symbol,
            range=range_key,
            points=points,
            empty_state=EmptyState(message="No timeseries data is available.")
            if not points
            else None,
        )

    async def get_news(self, symbol: str) -> StockNewsFeedResponse | None:
        snapshot = await self._get_snapshot(symbol)
        if snapshot is None:
            return None

        return StockNewsFeedResponse(
            slug=snapshot.stock.slug,
            symbol=snapshot.primary_identifier.composite_symbol,
            items=snapshot.news_items,
            empty_state=EmptyState(message="No recent news is available.")
            if not snapshot.news_items
            else None,
        )

    async def get_analysis(self, symbol: str) -> StockAnalysisResponse | None:
        snapshot = await self._get_snapshot(symbol)
        if snapshot is None:
            return None

        return snapshot.analysis

    async def compare(self, symbols: list[str]) -> ComparisonViewResponse:
        snapshots = await self._build_snapshots()
        if symbols:
            selected = [
                snapshot for snapshot in snapshots if self._matches(snapshot.stock, symbols)
            ]
        else:
            selected = snapshots[:3]

        rows = [
            ComparisonRowResponse(
                slug=snapshot.stock.slug,
                symbol=snapshot.primary_identifier.composite_symbol,
                company_name=snapshot.stock.company_name,
                sector=snapshot.stock.sector,
                factor_scores=snapshot.factor_scores,
                valuation=snapshot.valuation,
                financial_snapshot=snapshot.financial_snapshot,
                sentiment_label=snapshot.sentiment_label,
                sentiment_score=snapshot.sentiment_score,
            )
            for snapshot in selected
        ]

        ranked = sorted(
            [snapshot for snapshot in selected if snapshot.factor_scores.total_score is not None],
            key=lambda item: item.factor_scores.total_score or 0,
            reverse=True,
        )

        highlights = ComparisonHighlightsResponse()
        if ranked:
            highlights = ComparisonHighlightsResponse(
                most_attractive_symbol=ranked[0].primary_identifier.composite_symbol,
                most_attractive_name=ranked[0].stock.company_name,
                least_attractive_symbol=ranked[-1].primary_identifier.composite_symbol,
                least_attractive_name=ranked[-1].stock.company_name,
            )

        return ComparisonViewResponse(
            requested_symbols=symbols,
            rows=rows,
            highlights=highlights,
        )

    async def get_recommendation_snapshot(self) -> RecommendationSnapshotResponse:
        snapshots = await self._build_snapshots()
        ranked = sorted(
            [snapshot for snapshot in snapshots if snapshot.factor_scores.total_score is not None],
            key=lambda snapshot: snapshot.factor_scores.total_score or 0,
            reverse=True,
        )

        if not ranked:
            return RecommendationSnapshotResponse(
                methodology_version="transparent-mock-v1",
                generated_at=datetime.now(UTC),
                items=[],
            )

        long_candidate = ranked[0]
        short_candidate = ranked[-1]
        generated_at = max(
            (
                candidate.analysis.generated_at
                for candidate in [long_candidate, short_candidate]
                if candidate.analysis.generated_at is not None
            ),
            default=datetime.now(UTC),
        )

        return RecommendationSnapshotResponse(
            methodology_version="transparent-mock-v1",
            generated_at=generated_at,
            items=[
                self._recommendation_item(long_candidate, "LONG"),
                self._recommendation_item(short_candidate, "SHORT"),
            ],
        )

    async def _get_snapshot(self, symbol: str) -> MockSnapshot | None:
        snapshots = await self._build_snapshots()
        normalized = symbol.strip().lower()
        for snapshot in snapshots:
            if snapshot.stock.slug == normalized:
                return snapshot
            if snapshot.primary_identifier.composite_symbol.lower() == normalized:
                return snapshot
            if any(
                identifier.composite_symbol.lower() == normalized
                for identifier in snapshot.stock.identifiers
            ):
                return snapshot
        return None

    async def _build_snapshots(self) -> list[MockSnapshot]:
        raw_fundamentals: dict[str, float] = {}
        raw_valuation: dict[str, float] = {}
        raw_momentum: dict[str, float] = {}
        raw_sentiment: dict[str, float] = {}
        raw_globalization: dict[str, float] = {}
        intermediate: dict[str, dict] = {}

        start_date = date.today() - timedelta(days=400)
        end_date = date.today()

        for stock in UNIVERSE:
            primary_identifier = self._primary_identifier(stock)
            prices = await self.market_adapter.fetch_price_history(
                primary_identifier.composite_symbol,
                start_date=start_date,
                end_date=end_date,
            )
            valuation = await self.market_adapter.fetch_valuation_snapshot(
                primary_identifier.composite_symbol
            )
            financials = await self.market_adapter.fetch_financial_metrics(
                primary_identifier.composite_symbol
            )
            latest_financial = financials[0] if financials else None
            news_records = await self.news_adapter.fetch_recent_news(
                primary_identifier.composite_symbol, limit=6
            )

            returns = ReturnSnapshotResponse(
                return_1m=self._compute_return(prices, 21),
                return_3m=self._compute_return(prices, 63),
                return_6m=self._compute_return(prices, 126),
                return_1y=self._compute_return(prices, 252),
            )
            analysis = build_stock_analysis_response(
                slug=stock.slug,
                symbol=primary_identifier.composite_symbol,
                company_name=stock.company_name,
                company_name_zh=stock.company_name_zh,
                sector=stock.sector,
                outbound_theme=stock.outbound_theme,
                news_items=news_records,
                valuation=valuation,
                fundamentals=latest_financial,
                generated_at=datetime.now(UTC),
            )
            sentiment_score = analysis.sentiment_score or 0.0
            raw_fundamentals[stock.slug] = self._raw_fundamentals(latest_financial)
            raw_valuation[stock.slug] = self._raw_valuation(valuation)
            raw_momentum[stock.slug] = self._raw_momentum(returns)
            raw_sentiment[stock.slug] = sentiment_score
            raw_globalization[stock.slug] = self._raw_globalization(stock)
            intermediate[stock.slug] = {
                "stock": stock,
                "primary_identifier": primary_identifier,
                "prices": prices,
                "valuation": valuation,
                "latest_financial": latest_financial,
                "news_records": news_records,
                "returns": returns,
                "sentiment_score": sentiment_score,
                "analysis": analysis,
            }

        normalized_fundamentals = percentile_rank_map(raw_fundamentals, higher_is_better=True)
        normalized_valuation = percentile_rank_map(raw_valuation, higher_is_better=False)
        normalized_momentum = percentile_rank_map(raw_momentum, higher_is_better=True)
        normalized_sentiment = percentile_rank_map(raw_sentiment, higher_is_better=True)
        normalized_globalization = percentile_rank_map(raw_globalization, higher_is_better=True)

        snapshots: list[MockSnapshot] = []
        ranked_totals: list[tuple[str, float]] = []
        for slug, payload in intermediate.items():
            factor_scores = FactorScoreBreakdownResponse(
                fundamentals_quality=normalized_fundamentals[slug],
                valuation_attractiveness=normalized_valuation[slug],
                price_momentum=normalized_momentum[slug],
                news_sentiment=normalized_sentiment[slug],
                globalization_strength=normalized_globalization[slug],
                total_score=weighted_total(
                    {
                        "fundamentals_quality": normalized_fundamentals[slug],
                        "valuation_attractiveness": normalized_valuation[slug],
                        "price_momentum": normalized_momentum[slug],
                        "news_sentiment": normalized_sentiment[slug],
                        "globalization_strength": normalized_globalization[slug],
                    }
                ),
                rank=None,
            )
            ranked_totals.append((slug, factor_scores.total_score or 0))
            analysis = payload["analysis"]
            news_items = [
                StockNewsItemResponse(
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    summary=item.summary,
                    provider=item.provider,
                    source_url=item.source_url,
                    sentiment_label=self._sentiment_label(self._sentiment_score([item])),
                )
                for item in payload["news_records"]
            ]
            valuation = payload["valuation"]
            latest_financial = payload["latest_financial"]
            snapshots.append(
                MockSnapshot(
                    stock=payload["stock"],
                    primary_identifier=payload["primary_identifier"],
                    latest_price=payload["prices"][-1].close if payload["prices"] else None,
                    returns=payload["returns"],
                    factor_scores=factor_scores,
                    valuation=ValuationSnapshotResponse(
                        market_cap=valuation.market_cap,
                        pe_ttm=valuation.pe_ttm,
                        pe_forward=valuation.pe_forward,
                        pb=valuation.pb,
                        ps_ttm=valuation.ps_ttm,
                        ev_ebitda=valuation.ev_ebitda,
                        dividend_yield=valuation.dividend_yield,
                        as_of_date=valuation.as_of_date,
                    ),
                    financial_snapshot=FinancialSnapshotResponse(
                        report_date=latest_financial.report_date if latest_financial else None,
                        fiscal_year=latest_financial.fiscal_year if latest_financial else None,
                        fiscal_period=latest_financial.fiscal_period if latest_financial else None,
                        revenue=latest_financial.revenue if latest_financial else None,
                        net_profit=latest_financial.net_profit if latest_financial else None,
                        gross_margin=latest_financial.gross_margin if latest_financial else None,
                        roe=latest_financial.roe if latest_financial else None,
                        revenue_growth_yoy=latest_financial.revenue_growth_yoy
                        if latest_financial
                        else None,
                        net_profit_growth_yoy=latest_financial.net_profit_growth_yoy
                        if latest_financial
                        else None,
                    ),
                    sentiment_label=analysis.sentiment_label or "NEUTRAL",
                    sentiment_score=analysis.sentiment_score or 0.0,
                    keywords=analysis.keywords,
                    ai_summary=analysis.summary,
                    valuation_summary=analysis.valuation_summary,
                    bull_case=analysis.bull_case,
                    bear_case=analysis.bear_case,
                    key_risks=analysis.key_risks,
                    analysis=analysis,
                    news_items=news_items,
                    timeseries_points=[
                        PricePoint(
                            trading_date=item.trading_date,
                            close=item.close,
                            volume=item.volume,
                        )
                        for item in payload["prices"]
                    ],
                )
            )

        rank_map = {
            slug: index
            for index, (slug, _score) in enumerate(
                sorted(ranked_totals, key=lambda item: item[1], reverse=True),
                start=1,
            )
        }

        return [
            MockSnapshot(
                stock=snapshot.stock,
                primary_identifier=snapshot.primary_identifier,
                latest_price=snapshot.latest_price,
                returns=snapshot.returns,
                factor_scores=FactorScoreBreakdownResponse(
                    **snapshot.factor_scores.model_dump(exclude={"rank"}),
                    rank=rank_map[snapshot.stock.slug],
                ),
                valuation=snapshot.valuation,
                financial_snapshot=snapshot.financial_snapshot,
                sentiment_label=snapshot.sentiment_label,
                sentiment_score=snapshot.sentiment_score,
                keywords=snapshot.keywords,
                ai_summary=snapshot.ai_summary,
                valuation_summary=snapshot.valuation_summary,
                bull_case=snapshot.bull_case,
                bear_case=snapshot.bear_case,
                key_risks=snapshot.key_risks,
                analysis=snapshot.analysis,
                news_items=snapshot.news_items,
                timeseries_points=snapshot.timeseries_points,
            )
            for snapshot in snapshots
        ]

    @staticmethod
    def _primary_identifier(stock: StockUniverseSeed) -> IdentifierSeed:
        return next(identifier for identifier in stock.identifiers if identifier.is_primary)

    @staticmethod
    def _identifier_view(identifier: IdentifierSeed) -> StockIdentifierViewResponse:
        return StockIdentifierViewResponse(
            exchange_code=identifier.exchange_code,
            composite_symbol=identifier.composite_symbol,
            identifier_type=identifier.identifier_type,
            currency=identifier.currency,
            is_primary=identifier.is_primary,
        )

    @staticmethod
    def _compute_return(prices, days: int) -> float | None:
        if len(prices) <= days:
            return None
        current = prices[-1].close
        prior = prices[-(days + 1)].close
        if prior == 0:
            return None
        return round((current / prior) - 1, 4)

    @staticmethod
    def _raw_fundamentals(financial) -> float:
        if financial is None:
            return 0.0
        values = [
            financial.revenue_growth_yoy or 0,
            financial.net_profit_growth_yoy or 0,
            financial.gross_margin or 0,
            financial.roe or 0,
        ]
        return round(sum(values) / len(values), 6)

    @staticmethod
    def _raw_valuation(valuation) -> float:
        return round((valuation.pe_ttm + valuation.pb + valuation.ps_ttm) / 3, 6)

    @staticmethod
    def _raw_momentum(returns: ReturnSnapshotResponse) -> float:
        return round(
            (returns.return_1m or 0) * 0.2
            + (returns.return_3m or 0) * 0.3
            + (returns.return_6m or 0) * 0.2
            + (returns.return_1y or 0) * 0.3,
            6,
        )

    @staticmethod
    def _raw_globalization(stock: StockUniverseSeed) -> float:
        theme = stock.outbound_theme.lower()
        hits = sum(
            1
            for keyword in [
                "global",
                "overseas",
                "international",
                "export",
                "cross-border",
                "network",
            ]
            if keyword in theme
        )
        return float(40 + hits * 8 + max(0, len(stock.identifiers) - 1) * 10)

    def _sentiment_score(self, news_records) -> float:
        labels = []
        for item in news_records:
            normalized = f"{item.title} {item.summary or ''}".lower()
            positive_hits = sum(token in normalized for token in POSITIVE_HINTS)
            negative_hits = sum(token in normalized for token in NEGATIVE_HINTS)
            if positive_hits > negative_hits:
                labels.append(1.0)
            elif negative_hits > positive_hits:
                labels.append(-1.0)
            else:
                labels.append(0.0)
        return round(sum(labels) / len(labels), 4) if labels else 0.0

    @staticmethod
    def _sentiment_label(score: float) -> str:
        if score >= 0.2:
            return "POSITIVE"
        if score <= -0.2:
            return "NEGATIVE"
        return "NEUTRAL"

    @staticmethod
    def _keywords(news_records) -> list[str]:
        counter: Counter[str] = Counter()
        for item in news_records:
            normalized = (
                f"{item.title} {item.summary or ''}".lower()
                .replace(",", " ")
                .replace(".", " ")
                .replace(":", " ")
            )
            for token in normalized.split():
                if len(token) < 5:
                    continue
                counter[token] += 1
        return [token for token, _count in counter.most_common(5)]

    @staticmethod
    def _summary(stock, financial, valuation, sentiment_score: float, keywords: list[str]) -> str:
        return (
            f"{stock.company_name} shows mock revenue growth of "
            f"{financial.revenue_growth_yoy if financial else None}, valuation PE "
            f"{valuation.pe_ttm}, sentiment score {sentiment_score:.2f}, and keywords "
            f"{', '.join(keywords[:3])}."
        )

    @staticmethod
    def _valuation_summary(company_name: str, valuation) -> str:
        return (
            f"{company_name} trades on PE {valuation.pe_ttm}, PB {valuation.pb}, and PS "
            f"{valuation.ps_ttm} in the current mock snapshot."
        )

    @staticmethod
    def _bull_case(stock, financial, returns: ReturnSnapshotResponse, sentiment_label: str) -> str:
        return (
            f"{stock.company_name} benefits from outbound theme strength, quarterly revenue "
            f"growth of {financial.revenue_growth_yoy if financial else None}, and "
            f"{sentiment_label.lower()} recent news with 1Y return {returns.return_1y}."
        )

    @staticmethod
    def _bear_case(stock, valuation, sentiment_label: str) -> str:
        return (
            f"{stock.company_name} faces downside if valuation at PE {valuation.pe_ttm} proves "
            f"too rich or if {sentiment_label.lower()} sentiment persists."
        )

    @staticmethod
    def _key_risks(stock) -> list[str]:
        return [
            f"{stock.company_name} mock dataset may not reflect live market conditions.",
            "Competition and export execution remain meaningful swing factors.",
            "Human review is still required before forming an investment view.",
        ]

    def _recommendation_item(
        self,
        snapshot: MockSnapshot,
        side: str,
    ) -> RecommendationItemResponse:
        score = snapshot.factor_scores
        theme_names = [theme.theme for theme in snapshot.analysis.top_news_themes[:2]]
        theme_summary = ", ".join(theme_names) if theme_names else "recent coverage"
        explanation = (
            f"{snapshot.stock.company_name} is the {side.lower()} recommendation because total score "
            f"{score.total_score:.1f} combines fundamentals {score.fundamentals_quality:.1f}, "
            f"valuation {score.valuation_attractiveness:.1f}, momentum {score.price_momentum:.1f}, "
            f"sentiment {score.news_sentiment:.1f}, and globalization {score.globalization_strength:.1f}."
        )
        if side == "LONG":
            explanation += f" The evidence stack is led by {theme_summary.lower()}."
        else:
            explanation += f" The weakest link comes through {theme_summary.lower()} and lower factor resilience."

        return RecommendationItemResponse(
            side=side,
            slug=snapshot.stock.slug,
            symbol=snapshot.primary_identifier.composite_symbol,
            company_name=snapshot.stock.company_name,
            company_name_zh=snapshot.stock.company_name_zh,
            sector=snapshot.stock.sector,
            outbound_theme=snapshot.stock.outbound_theme,
            explanation=explanation,
            confidence_score=round(abs((score.total_score or 50) - 50) / 50, 4),
            latest_price=snapshot.latest_price,
            returns=snapshot.returns,
            factor_scores=snapshot.factor_scores,
            valuation=snapshot.valuation,
            financial_snapshot=snapshot.financial_snapshot,
            evidence_buckets=self._recommendation_evidence_buckets(snapshot),
            analysis=snapshot.analysis,
            key_risks=snapshot.analysis.key_risks,
            source_links=snapshot.analysis.source_links,
        )

    def _recommendation_evidence_buckets(
        self,
        snapshot: MockSnapshot,
    ) -> list[RecommendationEvidenceBucketResponse]:
        analysis = snapshot.analysis
        growth_references = self._filter_analysis_references(
            analysis, {"revenue_growth_yoy", "net_profit_growth_yoy", "gross_margin", "roe"}
        )
        momentum_references = self._momentum_references(snapshot)
        globalization_references = self._globalization_references(snapshot)
        theme_names = [theme.theme for theme in analysis.top_news_themes[:2]]

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
                    f"Revenue growth {self._format_percent(snapshot.financial_snapshot.revenue_growth_yoy)}, "
                    f"net profit growth {self._format_percent(snapshot.financial_snapshot.net_profit_growth_yoy)}, "
                    f"gross margin {self._format_percent(snapshot.financial_snapshot.gross_margin)}, "
                    f"and ROE {self._format_percent(snapshot.financial_snapshot.roe)}."
                ),
                references=growth_references,
            ),
            RecommendationEvidenceBucketResponse(
                key="momentum",
                title="Momentum evidence",
                summary=(
                    f"Recent price action shows 1M {self._format_percent(snapshot.returns.return_1m)}, "
                    f"3M {self._format_percent(snapshot.returns.return_3m)}, and "
                    f"1Y {self._format_percent(snapshot.returns.return_1y)} performance."
                ),
                references=momentum_references,
            ),
            RecommendationEvidenceBucketResponse(
                key="sentiment",
                title="Sentiment evidence",
                summary=(
                    f"AI sentiment is {analysis.sentiment_label.lower() if analysis.sentiment_label else 'unknown'} "
                    f"at {analysis.sentiment_score:.2f} and is driven by {theme_names[0].lower() if theme_names else 'recent coverage'}."
                ),
                references=self._dedupe_references(
                    analysis.sentiment_evidence
                    + [reference for theme in analysis.top_news_themes[:2] for reference in theme.evidence[:1]]
                ),
            ),
            RecommendationEvidenceBucketResponse(
                key="globalization",
                title="Outbound / globalization evidence",
                summary=(
                    f"{snapshot.stock.outbound_theme} The globalization factor score is "
                    f"{snapshot.factor_scores.globalization_strength:.1f} with {len(snapshot.stock.identifiers)} tracked listings."
                ),
                references=globalization_references,
            ),
        ]

    @staticmethod
    def _filter_analysis_references(
        analysis: StockAnalysisResponse,
        allowed_keys: set[str],
    ) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            reference
            for reference in analysis.source_references
            if reference.reference_type == "metric" and reference.metric_key in allowed_keys
        ]

    @staticmethod
    def _momentum_references(snapshot: MockSnapshot) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_1m",
                reference_type="metric",
                label="1M Return",
                metric_key="return_1m",
                metric_value=round(snapshot.returns.return_1m or 0, 4),
                metric_unit="ratio",
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_3m",
                reference_type="metric",
                label="3M Return",
                metric_key="return_3m",
                metric_value=round(snapshot.returns.return_3m or 0, 4),
                metric_unit="ratio",
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:return_1y",
                reference_type="metric",
                label="1Y Return",
                metric_key="return_1y",
                metric_value=round(snapshot.returns.return_1y or 0, 4),
                metric_unit="ratio",
            ),
        ]

    @staticmethod
    def _globalization_references(snapshot: MockSnapshot) -> list[AnalysisEvidenceReferenceResponse]:
        return [
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:outbound_theme",
                reference_type="metric",
                label="Outbound Theme",
                metric_key="outbound_theme",
                metric_value=snapshot.stock.outbound_theme,
            ),
            AnalysisEvidenceReferenceResponse(
                reference_id="metric:listing_count",
                reference_type="metric",
                label="Listing Breadth",
                metric_key="listing_count",
                metric_value=len(snapshot.stock.identifiers),
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
    def _format_percent(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value * 100:.1f}%"

    @staticmethod
    def _matches(stock: StockUniverseSeed, symbols: list[str]) -> bool:
        normalized = {symbol.strip().lower() for symbol in symbols if symbol.strip()}
        if stock.slug in normalized:
            return True
        return any(
            identifier.composite_symbol.lower() in normalized for identifier in stock.identifiers
        )
