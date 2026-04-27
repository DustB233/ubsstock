from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import (
    AIArtifact,
    FinancialMetric,
    NewsCluster,
    NewsClusterItem,
    NewsItem,
    RefreshJob,
    Stock,
    StockIdentifier,
    StockNewsMention,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import AIArtifactType, JobStatus, RefreshJobType
from china_outbound_analyzer.services.ai.competition_artifacts import (
    SCHEMA_VERSION,
    _classify_theme,
    _normalize_news_items,
    build_stock_analysis_response,
)
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "into",
    "from",
    "mock",
    "item",
    "focus",
    "update",
    "designed",
    "phase",
    "pipeline",
    "covering",
    "recent",
}

POSITIVE_WORDS = {
    "accelerates",
    "approval",
    "demand",
    "expansion",
    "gains",
    "improves",
    "momentum",
    "positive",
    "stabilizes",
    "strengthens",
}

NEGATIVE_WORDS = {
    "caution",
    "competition",
    "decline",
    "delay",
    "intensifies",
    "negative",
    "pressure",
    "risk",
    "slowdown",
    "weak",
}


class MockAIAnalysisService:
    def __init__(self, session: Session):
        self.session = session

    def run(
        self,
        *,
        trigger_source: str = "cli:analyze-mock",
        job_name: str = "analyze-mock",
        refresh_job: RefreshJob | None = None,
        stale_after_seconds: int = 7200,
    ) -> dict[str, int | str]:
        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.AI_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=stale_after_seconds,
            stage_status={"phase": "ai_analysis", "mode": "deterministic_mock"},
        )
        if refresh_job is None:
            return {
                "job_name": job_name,
                "status": "SKIPPED",
                "reason": "job_already_running",
            }

        stocks = self.session.scalars(select(Stock).order_by(Stock.company_name)).all()
        artifact_count = 0
        cluster_count = 0

        try:
            for stock in stocks:
                stock_clusters, stock_artifacts = self._process_stock(stock)
                cluster_count += stock_clusters
                artifact_count += stock_artifacts

            complete_job_success(
                self.session,
                refresh_job,
                stage_status={
                    "phase": "ai_analysis",
                    "clusters": cluster_count,
                    "artifacts": artifact_count,
                },
            )
            self.session.commit()
            return {
                "job_id": str(refresh_job.id),
                "status": refresh_job.status.value,
                "clusters": cluster_count,
                "artifacts": artifact_count,
            }
        except Exception as exc:
            complete_job_failure(
                self.session,
                refresh_job,
                error_message=str(exc),
                stage_status={
                    "phase": "ai_analysis",
                    "clusters": cluster_count,
                    "artifacts": artifact_count,
                },
            )
            self.session.commit()
            raise

    def _process_stock(self, stock: Stock) -> tuple[int, int]:
        news_rows = self.session.execute(
            select(
                NewsItem.id,
                NewsItem.title,
                NewsItem.summary,
                NewsItem.url,
                NewsItem.provider,
                NewsItem.published_at,
                NewsItem.raw_payload,
            )
            .join(StockNewsMention, StockNewsMention.news_item_id == NewsItem.id)
            .where(StockNewsMention.stock_id == stock.id)
            .order_by(NewsItem.published_at.desc())
        ).all()

        if not news_rows:
            return (0, 0)

        news_items = joined_news_as_dict(news_rows)
        news_id_map = {str(item["id"]): item["id"] for item in news_items}
        normalized_news = _normalize_news_items(news_items)

        self.session.execute(
            delete(AIArtifact).where(
                AIArtifact.stock_id == stock.id,
                AIArtifact.artifact_type.in_(
                    [
                        AIArtifactType.NEWS_CLUSTER,
                        AIArtifactType.SENTIMENT_SUMMARY,
                        AIArtifactType.KEYWORD_EXTRACTION,
                        AIArtifactType.VALUATION_SUMMARY,
                        AIArtifactType.THESIS_SUMMARY,
                    ]
                ),
            )
        )

        existing_cluster_ids = self.session.scalars(
            select(NewsCluster.id).where(NewsCluster.stock_id == stock.id)
        ).all()
        if existing_cluster_ids:
            self.session.execute(
                delete(NewsClusterItem).where(NewsClusterItem.cluster_id.in_(existing_cluster_ids))
            )
            self.session.execute(
                delete(NewsCluster).where(NewsCluster.id.in_(existing_cluster_ids))
            )

        valuation = self.session.scalars(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.stock_id == stock.id)
            .order_by(ValuationSnapshot.as_of_date.desc())
            .limit(1)
        ).first()
        fundamentals = self.session.scalars(
            select(FinancialMetric)
            .where(FinancialMetric.stock_id == stock.id)
            .order_by(FinancialMetric.report_date.desc(), FinancialMetric.period_end.desc())
            .limit(1)
        ).first()

        primary_identifier = self.session.scalars(
            select(StockIdentifier)
            .where(StockIdentifier.stock_id == stock.id, StockIdentifier.is_primary.is_(True))
            .limit(1)
        ).first()
        primary_symbol = primary_identifier.composite_symbol if primary_identifier else stock.slug
        analysis = build_stock_analysis_response(
            slug=stock.slug,
            symbol=primary_symbol,
            company_name=stock.company_name,
            company_name_zh=stock.company_name_zh,
            sector=stock.sector,
            outbound_theme=stock.outbound_theme,
            news_items=news_items,
            valuation=valuation,
            fundamentals=fundamentals,
            generated_at=datetime.now(UTC),
        )
        analysis_payload = analysis.model_dump(mode="json")

        grouped = defaultdict(list)
        for item in normalized_news:
            grouped[_classify_theme(item)].append(item)

        cluster_count = 0
        for theme in analysis.top_news_themes:
            cluster = NewsCluster(
                stock_id=stock.id,
                cluster_label=theme.theme,
                summary=theme.summary,
                sentiment_score=Decimal(str(theme.sentiment_score or 0.0)),
                sentiment_label=theme.sentiment_label,
                keyword_payload={
                    "schema_version": SCHEMA_VERSION,
                    "article_count": theme.article_count,
                    "evidence_ids": [reference.reference_id for reference in theme.evidence],
                },
                window_start=datetime.now(UTC),
                window_end=datetime.now(UTC),
            )
            self.session.add(cluster)
            self.session.flush()

            items = grouped.get(theme.theme, [])
            representative_ids = {reference.reference_id for reference in theme.evidence[:1]}
            for item in items:
                self.session.add(
                    NewsClusterItem(
                        cluster_id=cluster.id,
                        news_item_id=news_id_map[item.reference_id],
                        is_representative=item.reference_id in representative_ids,
                    )
                )

            cluster_count += 1

        artifacts = [
            self._build_artifact(
                stock.id,
                AIArtifactType.NEWS_CLUSTER,
                f"Top themes for {stock.company_name}: {', '.join(theme.theme for theme in analysis.top_news_themes)}.",
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "top_news_themes": analysis_payload["top_news_themes"],
                },
                source_links={
                    "references": analysis_payload["source_references"],
                    "urls": analysis_payload["source_links"],
                },
                trace_payload={"news_ids": [str(item["id"]) for item in news_items]},
            ),
            self._build_artifact(
                stock.id,
                AIArtifactType.SENTIMENT_SUMMARY,
                (
                    f"Recent news tone is {analysis.sentiment_label.lower()} "
                    f"with score {(analysis.sentiment_score or 0.0):.3f}."
                ),
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "score": analysis.sentiment_score,
                    "label": analysis.sentiment_label,
                    "evidence": analysis_payload["sentiment_evidence"],
                },
                source_links={
                    "references": analysis_payload["sentiment_evidence"],
                    "urls": analysis_payload["source_links"],
                },
                trace_payload={
                    "positive_words": sorted(POSITIVE_WORDS),
                    "negative_words": sorted(NEGATIVE_WORDS),
                },
            ),
            self._build_artifact(
                stock.id,
                AIArtifactType.KEYWORD_EXTRACTION,
                f"Top extracted keywords: {', '.join(analysis.keywords)}.",
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "keywords": analysis.keywords,
                    "keyword_insights": analysis_payload["keyword_insights"],
                },
                source_links={
                    "references": analysis_payload["source_references"],
                    "urls": analysis_payload["source_links"],
                },
                trace_payload={"stopwords": sorted(STOPWORDS)},
            ),
            self._build_artifact(
                stock.id,
                AIArtifactType.VALUATION_SUMMARY,
                analysis.valuation_summary,
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "text": analysis.valuation_summary,
                    "evidence": analysis_payload["valuation_evidence"],
                },
                source_links={"references": analysis_payload["valuation_evidence"], "urls": []},
                trace_payload={"stock_slug": stock.slug, "valuation": self._valuation_payload(valuation)},
            ),
            self._build_artifact(
                stock.id,
                AIArtifactType.THESIS_SUMMARY,
                analysis.summary,
                structured_payload=analysis_payload,
                source_links={
                    "references": analysis_payload["source_references"],
                    "urls": analysis_payload["source_links"],
                },
                trace_payload={
                    "valuation": self._valuation_payload(valuation),
                    "fundamentals_report_date": (
                        str(fundamentals.report_date) if fundamentals else None
                    ),
                    "schema_version": SCHEMA_VERSION,
                },
            ),
        ]

        self.session.add_all(artifacts)
        return (cluster_count, len(artifacts))

    def _build_artifact(
        self,
        stock_id,
        artifact_type: AIArtifactType,
        content_markdown: str,
        structured_payload: dict,
        source_links: dict,
        trace_payload: dict,
    ) -> AIArtifact:
        return AIArtifact(
            stock_id=stock_id,
            artifact_type=artifact_type,
            model_provider="mock",
            model_name="deterministic-heuristic-v1",
            prompt_version="mock-v1",
            status=JobStatus.SUCCESS,
            generated_at=datetime.now(UTC),
            content_markdown=content_markdown,
            structured_payload=structured_payload,
            source_links=source_links,
            trace_payload=trace_payload,
        )

    @staticmethod
    def _extract_theme(title: str) -> str:
        if ": " in title:
            return title.split(": ", 1)[1].replace(" in focus", "")
        return "market update"

    @staticmethod
    def _extract_keywords(texts: list[str], limit: int = 5) -> list[str]:
        tokens = Counter()
        for text in texts:
            normalized = (
                text.lower().replace(",", " ").replace(".", " ").replace(":", " ").replace("'", " ")
            )
            for token in normalized.split():
                if len(token) < 4 or token in STOPWORDS or token.isdigit():
                    continue
                tokens[token] += 1

        return [word for word, _count in tokens.most_common(limit)]

    @staticmethod
    def _sentiment_score(text: str) -> float:
        tokens = set(
            text.lower()
            .replace(",", " ")
            .replace(".", " ")
            .replace(":", " ")
            .replace("'", " ")
            .split()
        )
        positive_hits = len(tokens & POSITIVE_WORDS)
        negative_hits = len(tokens & NEGATIVE_WORDS)
        if positive_hits == negative_hits == 0:
            return 0.0
        return round((positive_hits - negative_hits) / max(positive_hits + negative_hits, 1), 4)

    def _average_sentiment(self, texts: Iterable[str]) -> float:
        scores = [self._sentiment_score(text) for text in texts]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    @staticmethod
    def _sentiment_label(score: float) -> str:
        if score >= 0.2:
            return "POSITIVE"
        if score <= -0.2:
            return "NEGATIVE"
        return "NEUTRAL"

    @staticmethod
    def _valuation_payload(
        valuation: ValuationSnapshot | None,
    ) -> dict[str, float | None]:
        if valuation is None:
            return {"pe_ttm": None, "pb": None, "ps_ttm": None}
        return {
            "pe_ttm": float(valuation.pe_ttm) if valuation.pe_ttm is not None else None,
            "pb": float(valuation.pb) if valuation.pb is not None else None,
            "ps_ttm": float(valuation.ps_ttm) if valuation.ps_ttm is not None else None,
        }

    def _valuation_summary(
        self,
        company_name: str,
        valuation: ValuationSnapshot | None,
    ) -> str:
        if valuation is None:
            return f"No valuation snapshot is available for {company_name} yet."

        pe = float(valuation.pe_ttm) if valuation.pe_ttm is not None else None
        pb = float(valuation.pb) if valuation.pb is not None else None
        ps = float(valuation.ps_ttm) if valuation.ps_ttm is not None else None
        posture = "balanced"
        if pe is not None and pb is not None and pe < 18 and pb < 3.5:
            posture = "relatively attractive"
        elif pe is not None and pe > 30:
            posture = "demanding"

        return (
            f"{company_name} screens as {posture} on the latest mock snapshot with "
            f"PE {pe}, PB {pb}, and PS {ps}."
        )

    def _thesis_summary(
        self,
        company_name: str,
        fundamentals: FinancialMetric | None,
        valuation: ValuationSnapshot | None,
        sentiment: float,
        keywords: list[str],
    ) -> str:
        if fundamentals is None:
            return f"{company_name} has no fundamentals loaded yet for thesis generation."

        rev_growth = (
            float(fundamentals.revenue_growth_yoy)
            if fundamentals.revenue_growth_yoy is not None
            else None
        )
        profit_growth = (
            float(fundamentals.net_profit_growth_yoy)
            if fundamentals.net_profit_growth_yoy is not None
            else None
        )
        pe = float(valuation.pe_ttm) if valuation and valuation.pe_ttm is not None else None

        return (
            f"{company_name} combines revenue growth of {rev_growth}, net profit growth of "
            f"{profit_growth}, recent sentiment score {sentiment:.3f}, and leading keywords "
            f"{', '.join(keywords[:3])}. Latest PE stands at {pe}."
        )


def joined_news_as_dict(rows: list[tuple]) -> list[dict[str, str]]:
    return [
        {
            "id": row[0],
            "title": row[1],
            "summary": row[2] or "",
            "url": row[3],
            "provider": row[4],
            "published_at": row[5].isoformat() if row[5] is not None else None,
            "source_url": (row[6] or {}).get("source_url") if row[6] else None,
        }
        for row in rows
    ]


def build_news_source_links(news_items: list[dict[str, str]]) -> dict[str, list[dict[str, str]] | list[str]]:
    return {
        "urls": [item["url"] for item in news_items],
        "items": [
            {
                "title": item["title"],
                "url": item["url"],
                "provider": item.get("provider"),
                "published_at": item.get("published_at"),
                "source_url": item.get("source_url"),
            }
            for item in news_items
        ],
    }
