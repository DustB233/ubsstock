from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import (
    AIArtifact,
    FinancialMetric,
    NewsItem,
    PriceBar,
    RecommendationItem,
    RecommendationRun,
    RefreshJob,
    ScoringRun,
    Stock,
    StockIdentifier,
    StockNewsMention,
    StockScore,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import (
    AIArtifactType,
    JobStatus,
    RecommendationSide,
    RefreshJobType,
)
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)
from china_outbound_analyzer.services.recommendation.contracts import (
    DEFAULT_SCORING_WEIGHTS,
    ScoringWeights,
)


@dataclass(frozen=True)
class FactorScores:
    fundamentals_quality: float
    valuation_attractiveness: float
    price_momentum: float
    news_sentiment: float
    globalization_strength: float

    def total(self, weights: ScoringWeights = DEFAULT_SCORING_WEIGHTS) -> float:
        return weighted_total(
            {
                "fundamentals_quality": self.fundamentals_quality,
                "valuation_attractiveness": self.valuation_attractiveness,
                "price_momentum": self.price_momentum,
                "news_sentiment": self.news_sentiment,
                "globalization_strength": self.globalization_strength,
            },
            weights,
        )


@dataclass(frozen=True)
class RankedStock:
    slug: str
    company_name: str
    factor_scores: FactorScores
    total_score: float


def percentile_rank_map(
    raw_scores: dict[str, float],
    higher_is_better: bool = True,
) -> dict[str, float]:
    if not raw_scores:
        return {}

    ordered = sorted(
        raw_scores.items(),
        key=lambda item: item[1],
        reverse=higher_is_better,
    )
    if len(ordered) == 1:
        return {ordered[0][0]: 50.0}

    result: dict[str, float] = {}
    denominator = len(ordered) - 1
    for index, (slug, _value) in enumerate(ordered):
        result[slug] = round((denominator - index) / denominator * 100, 4)
    return result


def weighted_total(
    factors: dict[str, float],
    weights: ScoringWeights = DEFAULT_SCORING_WEIGHTS,
) -> float:
    return round(
        factors["fundamentals_quality"] * weights.fundamentals_quality
        + factors["valuation_attractiveness"] * weights.valuation_attractiveness
        + factors["price_momentum"] * weights.price_momentum
        + factors["news_sentiment"] * weights.news_sentiment
        + factors["globalization_strength"] * weights.globalization_strength,
        4,
    )


def select_long_and_short(
    ranked_stocks: list[RankedStock],
) -> tuple[RankedStock, RankedStock]:
    if len(ranked_stocks) < 2:
        raise ValueError("At least two ranked stocks are required.")

    ordered = sorted(ranked_stocks, key=lambda item: item.total_score, reverse=True)
    return ordered[0], ordered[-1]


class ScoringService:
    def __init__(self, session: Session):
        self.session = session

    def run(
        self,
        *,
        trigger_source: str = "cli:score-universe",
        job_name: str = "score-universe",
        refresh_job: RefreshJob | None = None,
        stale_after_seconds: int = 7200,
    ) -> dict[str, str | int]:
        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.SCORING_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=stale_after_seconds,
            stage_status={"phase": "scoring", "methodology_version": "transparent-v1"},
        )
        if refresh_job is None:
            return {
                "job_name": job_name,
                "status": "SKIPPED",
                "reason": "job_already_running",
            }

        stocks = self.session.scalars(select(Stock).order_by(Stock.slug)).all()
        if not stocks:
            complete_job_failure(
                self.session,
                refresh_job,
                error_message="No stocks are available. Seed the universe first.",
                stage_status={"phase": "scoring", "ranked_count": 0},
            )
            self.session.commit()
            raise ValueError("No stocks are available. Seed the universe first.")

        raw_fundamentals: dict[str, float] = {}
        raw_valuation: dict[str, float] = {}
        raw_momentum: dict[str, float] = {}
        raw_sentiment: dict[str, float] = {}
        raw_globalization: dict[str, float] = {}
        score_details: dict[str, dict] = {}
        stock_map = {stock.slug: stock for stock in stocks}

        for stock in stocks:
            latest_financial = self.session.scalars(
                select(FinancialMetric)
                .where(FinancialMetric.stock_id == stock.id)
                .order_by(FinancialMetric.report_date.desc(), FinancialMetric.period_end.desc())
                .limit(1)
            ).first()
            latest_valuation = self.session.scalars(
                select(ValuationSnapshot)
                .where(ValuationSnapshot.stock_id == stock.id)
                .order_by(ValuationSnapshot.as_of_date.desc())
                .limit(1)
            ).first()
            sentiment_artifact = self.session.scalars(
                select(AIArtifact)
                .where(
                    AIArtifact.stock_id == stock.id,
                    AIArtifact.artifact_type == AIArtifactType.SENTIMENT_SUMMARY,
                )
                .order_by(AIArtifact.generated_at.desc())
                .limit(1)
            ).first()

            returns = self._momentum_returns(stock.id)
            raw_fundamentals[stock.slug] = self._raw_fundamentals(latest_financial)
            raw_valuation[stock.slug] = self._raw_valuation(latest_valuation)
            raw_momentum[stock.slug] = self._raw_momentum(returns)
            raw_sentiment[stock.slug] = self._raw_sentiment(sentiment_artifact)
            raw_globalization[stock.slug] = self._raw_globalization(stock)
            score_details[stock.slug] = {
                "returns": returns,
                "valuation": {
                    "pe_ttm": (
                        float(latest_valuation.pe_ttm)
                        if latest_valuation and latest_valuation.pe_ttm is not None
                        else None
                    ),
                    "pb": (
                        float(latest_valuation.pb)
                        if latest_valuation and latest_valuation.pb is not None
                        else None
                    ),
                    "ps_ttm": (
                        float(latest_valuation.ps_ttm)
                        if latest_valuation and latest_valuation.ps_ttm is not None
                        else None
                    ),
                },
                "sentiment_score": raw_sentiment[stock.slug],
            }

        normalized_fundamentals = percentile_rank_map(raw_fundamentals, True)
        normalized_valuation = percentile_rank_map(raw_valuation, False)
        normalized_momentum = percentile_rank_map(raw_momentum, True)
        normalized_sentiment = percentile_rank_map(raw_sentiment, True)
        normalized_globalization = percentile_rank_map(raw_globalization, True)

        try:
            scoring_run = ScoringRun(
                run_date=datetime.now(UTC).date(),
                methodology_version="transparent-v1",
                weights_json={
                    "fundamentals_quality": DEFAULT_SCORING_WEIGHTS.fundamentals_quality,
                    "valuation_attractiveness": (DEFAULT_SCORING_WEIGHTS.valuation_attractiveness),
                    "price_momentum": DEFAULT_SCORING_WEIGHTS.price_momentum,
                    "news_sentiment": DEFAULT_SCORING_WEIGHTS.news_sentiment,
                    "globalization_strength": DEFAULT_SCORING_WEIGHTS.globalization_strength,
                },
                status=JobStatus.RUNNING,
                notes="Deterministic scoring over stored market, news, and fundamentals data.",
            )
            self.session.add(scoring_run)
            self.session.flush()

            ranked_rows: list[RankedStock] = []
            for stock in stocks:
                factors = FactorScores(
                    fundamentals_quality=normalized_fundamentals[stock.slug],
                    valuation_attractiveness=normalized_valuation[stock.slug],
                    price_momentum=normalized_momentum[stock.slug],
                    news_sentiment=normalized_sentiment[stock.slug],
                    globalization_strength=normalized_globalization[stock.slug],
                )
                ranked_rows.append(
                    RankedStock(
                        slug=stock.slug,
                        company_name=stock.company_name,
                        factor_scores=factors,
                        total_score=factors.total(),
                    )
                )

            ranked_rows.sort(key=lambda item: item.total_score, reverse=True)
            for rank, row in enumerate(ranked_rows, start=1):
                self.session.add(
                    StockScore(
                        scoring_run_id=scoring_run.id,
                        stock_id=stock_map[row.slug].id,
                        fundamentals_score=Decimal(str(row.factor_scores.fundamentals_quality)),
                        valuation_score=Decimal(str(row.factor_scores.valuation_attractiveness)),
                        momentum_score=Decimal(str(row.factor_scores.price_momentum)),
                        sentiment_score=Decimal(str(row.factor_scores.news_sentiment)),
                        globalization_score=Decimal(str(row.factor_scores.globalization_strength)),
                        total_score=Decimal(str(row.total_score)),
                        rank=rank,
                        score_details=score_details[row.slug],
                    )
                )

            long_candidate, short_candidate = select_long_and_short(ranked_rows)
            recommendation_run = RecommendationRun(
                scoring_run_id=scoring_run.id,
                status=JobStatus.SUCCESS,
                explanation_markdown=(
                    f"Long: {long_candidate.company_name} at {long_candidate.total_score}. "
                    f"Short: {short_candidate.company_name} at {short_candidate.total_score}."
                ),
                trace_payload={
                    "long_slug": long_candidate.slug,
                    "short_slug": short_candidate.slug,
                    "methodology_version": "transparent-v1",
                },
            )
            self.session.add(recommendation_run)
            self.session.flush()

            self.session.add(
                self._recommendation_item(
                    recommendation_run.id,
                    stock_map[long_candidate.slug],
                    long_candidate,
                    RecommendationSide.LONG,
                )
            )
            self.session.add(
                self._recommendation_item(
                    recommendation_run.id,
                    stock_map[short_candidate.slug],
                    short_candidate,
                    RecommendationSide.SHORT,
                )
            )

            scoring_run.status = JobStatus.SUCCESS
            complete_job_success(
                self.session,
                refresh_job,
                stage_status={
                    "phase": "scoring",
                    "long_slug": long_candidate.slug,
                    "short_slug": short_candidate.slug,
                    "ranked_count": len(ranked_rows),
                    "scoring_run_id": str(scoring_run.id),
                },
            )
            self.session.commit()

            return {
                "job_id": str(refresh_job.id),
                "status": refresh_job.status.value,
                "scoring_run_id": str(scoring_run.id),
                "long_slug": long_candidate.slug,
                "short_slug": short_candidate.slug,
                "ranked_count": len(ranked_rows),
            }
        except Exception as exc:
            complete_job_failure(
                self.session,
                refresh_job,
                error_message=str(exc),
                stage_status={"phase": "scoring"},
            )
            self.session.commit()
            raise

    def _recommendation_item(
        self,
        recommendation_run_id,
        stock: Stock,
        ranked_stock: RankedStock,
        side: RecommendationSide,
    ) -> RecommendationItem:
        factors = ranked_stock.factor_scores
        source_urls = self._source_urls(stock.id)
        thesis = self.session.scalars(
            select(AIArtifact)
            .where(
                AIArtifact.stock_id == stock.id,
                AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY,
            )
            .order_by(AIArtifact.generated_at.desc())
            .limit(1)
        ).first()

        rationale = (
            f"{stock.company_name} is the {side.value.lower()} idea because total score "
            f"{ranked_stock.total_score:.2f} reflects fundamentals "
            f"{factors.fundamentals_quality:.1f}, valuation "
            f"{factors.valuation_attractiveness:.1f}, momentum "
            f"{factors.price_momentum:.1f}, sentiment "
            f"{factors.news_sentiment:.1f}, and globalization "
            f"{factors.globalization_strength:.1f}."
        )

        thesis_payload = thesis.structured_payload if thesis and thesis.structured_payload else {}
        source_payload = thesis.source_links if thesis and thesis.source_links else {"urls": source_urls}

        return RecommendationItem(
            recommendation_run_id=recommendation_run_id,
            stock_id=stock.id,
            side=side,
            confidence_score=Decimal(str(abs(ranked_stock.total_score - 50) / 50)),
            rationale_markdown=rationale,
            bull_case=(
                thesis_payload.get("bull_case")
                if thesis_payload.get("bull_case")
                else thesis.content_markdown
                if thesis
                else f"No stored AI bull case is available for {stock.company_name} yet."
            ),
            bear_case=(
                thesis_payload.get("bear_case")
                if thesis_payload.get("bear_case")
                else f"{stock.company_name} could disappoint if sentiment, valuation, or momentum reverse."
            ),
            key_risks={
                "risks": thesis_payload.get("key_risks")
                or [
                    "Live AI rationale is missing, so only score-based evidence is available.",
                    "Factor weights are transparent but still heuristic rather than predictive.",
                ]
            },
            supporting_metrics={
                "fundamentals_quality": factors.fundamentals_quality,
                "valuation_attractiveness": factors.valuation_attractiveness,
                "price_momentum": factors.price_momentum,
                "news_sentiment": factors.news_sentiment,
                "globalization_strength": factors.globalization_strength,
                "total_score": ranked_stock.total_score,
            },
            source_links=source_payload,
        )

    def _source_urls(self, stock_id) -> list[str]:
        rows = self.session.execute(
            select(NewsItem.url)
            .join(StockNewsMention, StockNewsMention.news_item_id == NewsItem.id)
            .where(StockNewsMention.stock_id == stock_id)
            .order_by(NewsItem.published_at.desc())
            .limit(5)
        ).all()
        return [row[0] for row in rows]

    @staticmethod
    def _raw_fundamentals(metric: FinancialMetric | None) -> float:
        if metric is None:
            return 0.0
        values = [
            float(metric.revenue_growth_yoy or 0),
            float(metric.net_profit_growth_yoy or 0),
            float(metric.gross_margin or 0),
            float(metric.roe or 0),
        ]
        return round(sum(values) / len(values), 6)

    @staticmethod
    def _raw_valuation(valuation: ValuationSnapshot | None) -> float:
        if valuation is None:
            return 999.0
        values = [
            float(valuation.pe_ttm or 999),
            float(valuation.pb or 999),
            float(valuation.ps_ttm or 999),
        ]
        return round(sum(values) / len(values), 6)

    @staticmethod
    def _raw_sentiment(artifact: AIArtifact | None) -> float:
        if artifact is None or not artifact.structured_payload:
            return 0.0
        score = artifact.structured_payload.get("score")
        if score is None:
            return 0.0
        return float(score)

    def _raw_globalization(self, stock: Stock) -> float:
        keyword_hits = sum(
            1
            for keyword in [
                "global",
                "overseas",
                "international",
                "export",
                "cross-border",
                "network",
            ]
            if keyword in stock.outbound_theme.lower()
        )
        identifier_count = len(
            self.session.scalars(
                select(StockIdentifier.id).where(StockIdentifier.stock_id == stock.id)
            ).all()
        )
        return round(40 + keyword_hits * 8 + max(0, identifier_count - 1) * 10, 6)

    @staticmethod
    def _raw_momentum(returns: dict[str, float]) -> float:
        return round(
            returns["return_1m"] * 0.3 + returns["return_3m"] * 0.3 + returns["return_1y"] * 0.4,
            6,
        )

    def _momentum_returns(self, stock_id) -> dict[str, float]:
        primary_identifier_id = self.session.scalar(
            select(StockIdentifier.id)
            .where(StockIdentifier.stock_id == stock_id, StockIdentifier.is_primary.is_(True))
            .limit(1)
        )
        prices = self.session.scalars(
            select(PriceBar)
            .where(PriceBar.identifier_id == primary_identifier_id)
            .order_by(PriceBar.trading_date.asc())
        ).all()
        if not prices:
            return {"return_1m": 0.0, "return_3m": 0.0, "return_1y": 0.0}

        def compute(days: int) -> float:
            if len(prices) <= days:
                return 0.0
            current = float(prices[-1].close or 0)
            prior = float(prices[-(days + 1)].close or 0)
            if prior == 0:
                return 0.0
            return round((current / prior) - 1, 6)

        return {
            "return_1m": compute(21),
            "return_3m": compute(63),
            "return_1y": compute(252),
        }
