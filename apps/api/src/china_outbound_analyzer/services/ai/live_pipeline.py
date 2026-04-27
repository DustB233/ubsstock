from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.entities import (
    AIArtifact,
    Announcement,
    FinancialMetric,
    NewsItem,
    PriceBar,
    RefreshJob,
    ScoringRun,
    Stock,
    StockIdentifier,
    StockNewsMention,
    StockScore,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import AIArtifactType, JobStatus, RefreshJobType
from china_outbound_analyzer.schemas.stock_views import (
    AnalysisEvidenceReferenceResponse,
    AnalysisFreshnessResponse,
    AnalysisKeywordInsightResponse,
    AnalysisRiskInsightResponse,
    AnalysisThemeResponse,
    StockAnalysisResponse,
)
from china_outbound_analyzer.services.ai.competition_artifacts import (
    SCHEMA_VERSION,
    _dedupe_references,
    _fundamental_metric_references,
    _unique_urls,
    _valuation_metric_references,
    build_stock_analysis_response,
)
from china_outbound_analyzer.services.jobs.runtime import (
    complete_job_failure,
    complete_job_success,
    start_job_run,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "live-v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


class LiveAnalysisSectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str]


class LiveAnalysisRiskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: str
    evidence_ids: list[str]


class LiveAnalysisNarrativeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investment_takeaway: str
    summary_evidence_ids: list[str]
    valuation_summary: str
    valuation_evidence_ids: list[str]
    bull_case: str
    bull_case_evidence_ids: list[str]
    bear_case: str
    bear_case_evidence_ids: list[str]
    key_risks: list[LiveAnalysisRiskDraft]
    missing_inputs: list[str]


@dataclass(frozen=True)
class LiveAnalysisContext:
    stock: Stock
    primary_symbol: str
    baseline_analysis: StockAnalysisResponse
    evidence_catalog: dict[str, AnalysisEvidenceReferenceResponse]
    evidence_payloads: list[dict[str, Any]]
    combined_story_inputs: list[dict[str, Any]]
    news_items: list[dict[str, Any]]
    announcements: list[dict[str, Any]]
    valuation_payload: dict[str, Any] | None
    fundamentals_payload: dict[str, Any] | None
    price_payload: dict[str, Any] | None
    factor_payload: dict[str, Any] | None
    missing_inputs: list[str]
    freshness: AnalysisFreshnessResponse


@dataclass(frozen=True)
class GeneratedNarrative:
    draft: LiveAnalysisNarrativeDraft
    analysis_mode: str
    model_provider: str
    model_name: str
    prompt_version: str
    trace_payload: dict[str, Any]


class LiveAnalysisGenerator(Protocol):
    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        ...

    async def aclose(self) -> None:
        return None


class OpenAIRetryableError(Exception):
    pass


class OpenAIChatCompletionsGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        base_url: str = OPENAI_BASE_URL,
        reasoning_effort: str = "medium",
        verbosity: str = "low",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(context)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "live_stock_analysis_narrative",
                    "strict": True,
                    "schema": LiveAnalysisNarrativeDraft.model_json_schema(),
                },
            },
            "reasoning_effort": self.reasoning_effort,
            "verbosity": self.verbosity,
            "store": False,
        }

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max(self.max_retries, 1)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.TransportError, OpenAIRetryableError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await self._client.post("/chat/completions", json=request_payload)
                if response.status_code >= 500 or response.status_code == 429:
                    raise OpenAIRetryableError(
                        f"OpenAI retryable status {response.status_code}: {response.text[:200]}"
                    )
                if not response.is_success:
                    raise httpx.HTTPStatusError(
                        (
                            f"OpenAI non-retryable status {response.status_code}: "
                            f"{response.text[:500]}"
                        ),
                        request=response.request,
                        response=response,
                    )
                payload = response.json()
                draft = LiveAnalysisNarrativeDraft.model_validate_json(
                    self._extract_message_content(payload)
                )
                return GeneratedNarrative(
                    draft=draft,
                    analysis_mode="live_ai",
                    model_provider="openai",
                    model_name=self.model,
                    prompt_version=PROMPT_VERSION,
                    trace_payload={
                        "request_model": self.model,
                        "reasoning_effort": self.reasoning_effort,
                        "verbosity": self.verbosity,
                        "response_id": payload.get("id"),
                        "usage": payload.get("usage"),
                    },
                )

        raise RuntimeError("OpenAI narrative generation exhausted retries unexpectedly.")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are generating a competition-ready investment analysis artifact for a stock "
            "dashboard. Use only the provided stored evidence. Never invent facts, never invent "
            "evidence IDs, and never imply confidence where evidence is missing. Keep each section "
            "concise, decision-useful, and presentation-ready."
        )

    @staticmethod
    def _user_prompt(context: LiveAnalysisContext) -> str:
        prompt = {
            "task": (
                "Write a structured stock narrative using only the supplied evidence IDs. "
                "If a section cannot be supported, leave the text empty or mention the missing "
                "input explicitly in missing_inputs."
            ),
            "stock": {
                "slug": context.stock.slug,
                "symbol": context.primary_symbol,
                "company_name": context.stock.company_name,
                "company_name_zh": context.stock.company_name_zh,
                "sector": context.stock.sector,
                "outbound_theme": context.stock.outbound_theme,
            },
            "baseline": {
                "summary": context.baseline_analysis.summary,
                "valuation_summary": context.baseline_analysis.valuation_summary,
                "bull_case": context.baseline_analysis.bull_case,
                "bear_case": context.baseline_analysis.bear_case,
                "key_risks": context.baseline_analysis.key_risks,
                "top_news_themes": [
                    {
                        "theme": theme.theme,
                        "summary": theme.summary,
                        "article_count": theme.article_count,
                        "sentiment_label": theme.sentiment_label,
                    }
                    for theme in context.baseline_analysis.top_news_themes
                ],
                "keywords": context.baseline_analysis.keywords,
                "sentiment_score": context.baseline_analysis.sentiment_score,
                "sentiment_label": context.baseline_analysis.sentiment_label,
            },
            "price_context": context.price_payload,
            "valuation_context": context.valuation_payload,
            "fundamental_context": context.fundamentals_payload,
            "factor_context": context.factor_payload,
            "freshness": context.freshness.model_dump(mode="json"),
            "missing_inputs": context.missing_inputs,
            "evidence_catalog": context.evidence_payloads,
        }
        return json.dumps(prompt, ensure_ascii=False, default=_json_default)

    @staticmethod
    def _extract_message_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("OpenAI response did not contain any choices.")
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = [
                str(item.get("text"))
                for item in content
                if isinstance(item, Mapping) and item.get("text")
            ]
            if chunks:
                return "".join(chunks)
        raise ValueError("OpenAI response did not contain JSON message content.")


class HeuristicNarrativeGenerator:
    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        baseline = context.baseline_analysis
        return GeneratedNarrative(
            draft=LiveAnalysisNarrativeDraft(
                investment_takeaway=baseline.summary,
                summary_evidence_ids=[reference.reference_id for reference in baseline.summary_evidence],
                valuation_summary=baseline.valuation_summary,
                valuation_evidence_ids=[
                    reference.reference_id for reference in baseline.valuation_evidence
                ],
                bull_case=baseline.bull_case,
                bull_case_evidence_ids=[
                    reference.reference_id for reference in baseline.bull_case_evidence
                ],
                bear_case=baseline.bear_case,
                bear_case_evidence_ids=[
                    reference.reference_id for reference in baseline.bear_case_evidence
                ],
                key_risks=[
                    LiveAnalysisRiskDraft(
                        risk=risk.risk,
                        evidence_ids=[
                            reference.reference_id for reference in risk.evidence
                        ],
                    )
                    for risk in baseline.risk_evidence
                ],
                missing_inputs=context.missing_inputs,
            ),
            analysis_mode="heuristic_fallback",
            model_provider="heuristic",
            model_name="stored-data-composer-v1",
            prompt_version=PROMPT_VERSION,
            trace_payload={"fallback_reason": "llm_unavailable_or_skipped"},
        )

    async def aclose(self) -> None:
        return None


class LiveAIAnalysisService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        analysis_generator: LiveAnalysisGenerator | None = None,
        fallback_generator: LiveAnalysisGenerator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.analysis_generator = analysis_generator or build_live_analysis_generator(
            self.settings
        )
        self.fallback_generator = fallback_generator or HeuristicNarrativeGenerator()

    async def run(
        self,
        *,
        trigger_source: str = "cli:analyze-live",
        job_name: str = "analyze-live",
        refresh_job: RefreshJob | None = None,
        stale_after_seconds: int | None = None,
    ) -> dict[str, int | str]:
        stale_after_seconds = (
            stale_after_seconds or self.settings.scheduler_running_job_stale_after_seconds
        )
        refresh_job = refresh_job or start_job_run(
            self.session,
            job_name=job_name,
            job_type=RefreshJobType.AI_REFRESH,
            trigger_source=trigger_source,
            stale_after_seconds=stale_after_seconds,
            stage_status={
                "phase": "ai_analysis",
                "mode": self.settings.ai_analysis_provider,
                "prompt_version": PROMPT_VERSION,
            },
        )
        if refresh_job is None:
            return {
                "job_name": job_name,
                "status": "SKIPPED",
                "reason": "job_already_running",
            }

        stocks = self.session.scalars(select(Stock).order_by(Stock.company_name)).all()
        counts = {
            "symbols": 0,
            "artifacts": 0,
            "live_ai_symbols": 0,
            "fallback_symbols": 0,
            "partial_symbols": 0,
            "failed_symbols": 0,
        }
        failures: list[str] = []

        try:
            for stock in stocks:
                artifact_count, used_fallback, is_partial = await self._process_stock(
                    stock=stock,
                    refresh_job=refresh_job,
                )
                counts["symbols"] += 1
                counts["artifacts"] += artifact_count
                counts["fallback_symbols"] += 1 if used_fallback else 0
                counts["live_ai_symbols"] += 0 if used_fallback else 1
                counts["partial_symbols"] += 1 if is_partial else 0

            final_status = JobStatus.SUCCESS
            error_message = None
            if failures:
                final_status = JobStatus.PARTIAL if counts["artifacts"] > 0 else JobStatus.FAILED
                error_message = "Failed stocks: " + ", ".join(failures)
            elif counts["fallback_symbols"] > 0 or counts["partial_symbols"] > 0:
                final_status = JobStatus.PARTIAL
                error_message = "One or more stocks used heuristic fallback or partial live inputs."

            complete_job_success(
                self.session,
                refresh_job,
                stage_status=counts,
                status=final_status,
                error_message=error_message,
            )
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
            await self.analysis_generator.aclose()
            if self.fallback_generator is not self.analysis_generator:
                await self.fallback_generator.aclose()

    async def _process_stock(
        self,
        *,
        stock: Stock,
        refresh_job: RefreshJob,
    ) -> tuple[int, bool, bool]:
        context = self._build_context(stock)
        should_skip_live_ai = self._should_skip_live_ai(context)
        used_fallback = should_skip_live_ai
        generated: GeneratedNarrative

        if should_skip_live_ai:
            generated = await self.fallback_generator.generate(context)
        else:
            try:
                generated = await self.analysis_generator.generate(context)
            except Exception as exc:
                logger.warning(
                    "Live AI provider failed for %s, falling back to heuristic narrative: %s",
                    context.primary_symbol,
                    exc,
                )
                generated = await self.fallback_generator.generate(context)
                used_fallback = True

        final_analysis = self._compose_final_analysis(context, generated)
        artifact_payload = final_analysis.model_dump(mode="json")
        source_links = {
            "references": artifact_payload["source_references"],
            "urls": artifact_payload["source_links"],
        }
        trace_payload = _jsonable(
            {
            "freshness": context.freshness.model_dump(mode="json"),
            "missing_inputs": final_analysis.missing_inputs,
            "input_counts": {
                "news_items": len(context.news_items),
                "announcements": len(context.announcements),
                "evidence_references": len(context.evidence_catalog),
            },
            "price_context": context.price_payload,
            "valuation_context": context.valuation_payload,
            "fundamental_context": context.fundamentals_payload,
            "factor_context": context.factor_payload,
            **generated.trace_payload,
            }
        )

        artifacts = [
            self._build_artifact(
                refresh_job_id=refresh_job.id,
                stock_id=stock.id,
                artifact_type=AIArtifactType.NEWS_CLUSTER,
                content_markdown=(
                    f"Top themes for {stock.company_name}: "
                    + ", ".join(theme.theme for theme in final_analysis.top_news_themes)
                )
                if final_analysis.top_news_themes
                else f"No supported themes were identified for {stock.company_name}.",
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "analysis_mode": final_analysis.analysis_mode,
                    "top_news_themes": artifact_payload["top_news_themes"],
                    "freshness": artifact_payload["freshness"],
                    "missing_inputs": artifact_payload["missing_inputs"],
                },
                source_links=source_links,
                trace_payload=trace_payload,
                generated=generated,
            ),
            self._build_artifact(
                refresh_job_id=refresh_job.id,
                stock_id=stock.id,
                artifact_type=AIArtifactType.SENTIMENT_SUMMARY,
                content_markdown=(
                    "Recent stored tone is "
                    f"{(final_analysis.sentiment_label or 'UNAVAILABLE').lower()} "
                    f"with score {final_analysis.sentiment_score if final_analysis.sentiment_score is not None else 'n/a'}."
                ),
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "analysis_mode": final_analysis.analysis_mode,
                    "score": final_analysis.sentiment_score,
                    "label": final_analysis.sentiment_label,
                    "evidence": artifact_payload["sentiment_evidence"],
                    "freshness": artifact_payload["freshness"],
                    "missing_inputs": artifact_payload["missing_inputs"],
                },
                source_links={
                    "references": artifact_payload["sentiment_evidence"],
                    "urls": final_analysis.source_links,
                },
                trace_payload=trace_payload,
                generated=generated,
            ),
            self._build_artifact(
                refresh_job_id=refresh_job.id,
                stock_id=stock.id,
                artifact_type=AIArtifactType.KEYWORD_EXTRACTION,
                content_markdown=(
                    "Top keywords: " + ", ".join(final_analysis.keywords)
                    if final_analysis.keywords
                    else "No extracted keywords are available."
                ),
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "analysis_mode": final_analysis.analysis_mode,
                    "keywords": final_analysis.keywords,
                    "keyword_insights": artifact_payload["keyword_insights"],
                    "freshness": artifact_payload["freshness"],
                    "missing_inputs": artifact_payload["missing_inputs"],
                },
                source_links=source_links,
                trace_payload=trace_payload,
                generated=generated,
            ),
            self._build_artifact(
                refresh_job_id=refresh_job.id,
                stock_id=stock.id,
                artifact_type=AIArtifactType.VALUATION_SUMMARY,
                content_markdown=final_analysis.valuation_summary,
                structured_payload={
                    "schema_version": SCHEMA_VERSION,
                    "analysis_mode": final_analysis.analysis_mode,
                    "text": final_analysis.valuation_summary,
                    "evidence": artifact_payload["valuation_evidence"],
                    "freshness": artifact_payload["freshness"],
                    "missing_inputs": artifact_payload["missing_inputs"],
                },
                source_links={
                    "references": artifact_payload["valuation_evidence"],
                    "urls": _unique_urls(final_analysis.valuation_evidence),
                },
                trace_payload=trace_payload,
                generated=generated,
            ),
            self._build_artifact(
                refresh_job_id=refresh_job.id,
                stock_id=stock.id,
                artifact_type=AIArtifactType.THESIS_SUMMARY,
                content_markdown=final_analysis.summary,
                structured_payload=artifact_payload,
                source_links=source_links,
                trace_payload=trace_payload,
                generated=generated,
            ),
        ]

        self.session.add_all(artifacts)
        self.session.flush()
        return len(artifacts), used_fallback, bool(final_analysis.missing_inputs)

    def _build_context(self, stock: Stock) -> LiveAnalysisContext:
        primary_identifier = self.session.scalars(
            select(StockIdentifier)
            .where(
                StockIdentifier.stock_id == stock.id,
                StockIdentifier.is_primary.is_(True),
            )
            .limit(1)
        ).first()
        if primary_identifier is None:
            raise ValueError(f"No primary identifier exists for stock {stock.slug}.")

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
            .order_by(NewsItem.published_at.desc(), NewsItem.created_at.desc())
            .limit(12)
        ).all()
        announcement_rows = self.session.execute(
            select(
                Announcement.id,
                Announcement.title,
                Announcement.summary,
                Announcement.url,
                Announcement.published_at,
                Announcement.as_of_date,
                Announcement.provider,
                Announcement.exchange_code,
                Announcement.category,
                Announcement.language,
                Announcement.raw_payload,
            )
            .where(Announcement.stock_id == stock.id)
            .order_by(Announcement.published_at.desc(), Announcement.created_at.desc())
            .limit(8)
        ).all()

        news_items = [
            {
                "id": f"news:{row[0]}",
                "title": row[1],
                "summary": row[2] or "",
                "url": row[3],
                "provider": row[4],
                "published_at": row[5].isoformat() if row[5] is not None else None,
                "source_url": (row[6] or {}).get("source_url") if row[6] else None,
            }
            for row in news_rows
        ]
        announcements = [
            {
                "id": f"announcement:{row[0]}",
                "title": row[1],
                "summary": row[2] or "",
                "url": row[3],
                "provider": row[6] or ((row[10] or {}).get("source_name") if row[10] else "Company Filing"),
                "published_at": row[4].isoformat() if row[4] is not None else None,
                "as_of_date": row[5].isoformat() if row[5] is not None else None,
                "exchange_code": row[7],
                "source_url": (row[10] or {}).get("source_url") if row[10] else None,
                "category": row[8],
                "language": row[9] or ((row[10] or {}).get("language") if row[10] else None),
            }
            for row in announcement_rows
        ]
        combined_story_inputs = news_items + announcements

        valuation = self.session.scalars(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.stock_id == stock.id)
            .order_by(ValuationSnapshot.as_of_date.desc(), ValuationSnapshot.created_at.desc())
            .limit(1)
        ).first()
        fundamentals = self.session.scalars(
            select(FinancialMetric)
            .where(FinancialMetric.stock_id == stock.id)
            .order_by(
                FinancialMetric.report_date.desc(),
                FinancialMetric.period_end.desc(),
                FinancialMetric.created_at.desc(),
            )
            .limit(1)
        ).first()
        price_series = self.session.scalars(
            select(PriceBar)
            .where(PriceBar.identifier_id == primary_identifier.id)
            .order_by(PriceBar.trading_date.asc())
        ).all()

        stock_score = None
        scoring_run = self.session.scalars(
            select(ScoringRun)
            .order_by(ScoringRun.run_date.desc(), ScoringRun.created_at.desc())
            .limit(1)
        ).first()
        if scoring_run is not None:
            stock_score = self.session.scalars(
                select(StockScore)
                .where(
                    StockScore.scoring_run_id == scoring_run.id,
                    StockScore.stock_id == stock.id,
                )
                .limit(1)
            ).first()

        valuation_payload = _valuation_payload(valuation)
        fundamentals_payload = _fundamentals_payload(fundamentals)
        price_payload = _price_payload(price_series)
        factor_payload = _factor_payload(stock_score, scoring_run)
        freshness = AnalysisFreshnessResponse(
            latest_news_at=max(
                (
                    row[5]
                    for row in news_rows
                    if len(row) > 5 and isinstance(row[5], datetime)
                ),
                default=None,
            ),
            latest_announcement_at=max(
                (
                    row[4]
                    for row in announcement_rows
                    if len(row) > 4 and isinstance(row[4], datetime)
                ),
                default=None,
            ),
            latest_price_date=price_series[-1].trading_date if price_series else None,
            valuation_as_of_date=valuation.as_of_date if valuation else None,
            fundamentals_report_date=fundamentals.report_date if fundamentals else None,
            scoring_as_of_date=scoring_run.run_date if scoring_run else None,
        )
        missing_inputs = _missing_inputs(
            news_items=news_items,
            announcements=announcements,
            valuation=valuation,
            fundamentals=fundamentals,
            price_series=price_series,
            factor_payload=factor_payload,
        )

        baseline_analysis = build_stock_analysis_response(
            slug=stock.slug,
            symbol=primary_identifier.composite_symbol,
            company_name=stock.company_name,
            company_name_zh=stock.company_name_zh,
            sector=stock.sector,
            outbound_theme=stock.outbound_theme,
            news_items=combined_story_inputs,
            valuation=valuation_payload,
            fundamentals=fundamentals_payload,
            generated_at=datetime.now(UTC),
        )

        evidence_catalog = _build_evidence_catalog(
            news_items=news_items,
            announcements=announcements,
            valuation=valuation_payload,
            fundamentals=fundamentals_payload,
            price_payload=price_payload,
            factor_payload=factor_payload,
        )
        baseline_analysis = _remap_analysis_references(baseline_analysis, evidence_catalog)
        baseline_analysis = _apply_missing_input_guards(
            baseline_analysis,
            missing_inputs,
            stock.company_name,
        )
        evidence_payloads = _build_evidence_payloads(
            evidence_catalog=evidence_catalog,
            news_items=news_items,
            announcements=announcements,
        )

        return LiveAnalysisContext(
            stock=stock,
            primary_symbol=primary_identifier.composite_symbol,
            baseline_analysis=baseline_analysis,
            evidence_catalog=evidence_catalog,
            evidence_payloads=evidence_payloads,
            combined_story_inputs=combined_story_inputs,
            news_items=news_items,
            announcements=announcements,
            valuation_payload=valuation_payload,
            fundamentals_payload=fundamentals_payload,
            price_payload=price_payload,
            factor_payload=factor_payload,
            missing_inputs=missing_inputs,
            freshness=freshness,
        )

    @staticmethod
    def _should_skip_live_ai(context: LiveAnalysisContext) -> bool:
        if not context.evidence_catalog:
            return True
        hard_missing = {
            "recent_news",
            "valuation_snapshot",
            "financial_snapshot",
            "price_history",
        }
        return hard_missing.issubset(set(context.missing_inputs))

    def _compose_final_analysis(
        self,
        context: LiveAnalysisContext,
        generated: GeneratedNarrative,
    ) -> StockAnalysisResponse:
        baseline = context.baseline_analysis
        draft = generated.draft
        summary_evidence = _resolve_references(
            context.evidence_catalog,
            draft.summary_evidence_ids,
            fallback=baseline.summary_evidence,
        )
        valuation_evidence = _resolve_references(
            context.evidence_catalog,
            draft.valuation_evidence_ids,
            fallback=baseline.valuation_evidence,
        )
        bull_case_evidence = _resolve_references(
            context.evidence_catalog,
            draft.bull_case_evidence_ids,
            fallback=baseline.bull_case_evidence,
        )
        bear_case_evidence = _resolve_references(
            context.evidence_catalog,
            draft.bear_case_evidence_ids,
            fallback=baseline.bear_case_evidence,
        )

        risk_evidence = baseline.risk_evidence
        if draft.key_risks:
            risk_evidence = [
                AnalysisRiskInsightResponse(
                    risk=item.risk,
                    evidence=_resolve_references(context.evidence_catalog, item.evidence_ids),
                )
                for item in draft.key_risks
            ]

        context_missing_inputs = {item for item in context.missing_inputs if item}
        combined_missing_inputs = sorted(
            context_missing_inputs | {item for item in draft.missing_inputs if item in context_missing_inputs}
        )

        final_analysis = baseline.model_copy(
            update={
                "generated_at": datetime.now(UTC),
                "summary": draft.investment_takeaway or baseline.summary,
                "summary_evidence": summary_evidence,
                "valuation_summary": draft.valuation_summary or baseline.valuation_summary,
                "valuation_evidence": valuation_evidence,
                "bull_case": draft.bull_case or baseline.bull_case,
                "bull_case_evidence": bull_case_evidence,
                "bear_case": draft.bear_case or baseline.bear_case,
                "bear_case_evidence": bear_case_evidence,
                "risk_evidence": risk_evidence,
                "key_risks": [item.risk for item in risk_evidence],
                "analysis_mode": generated.analysis_mode,
                "model_provider": generated.model_provider,
                "model_name": generated.model_name,
                "prompt_version": generated.prompt_version,
                "missing_inputs": combined_missing_inputs,
                "freshness": context.freshness,
            }
        )

        final_source_references = _dedupe_references(
            final_analysis.summary_evidence
            + final_analysis.sentiment_evidence
            + final_analysis.valuation_evidence
            + final_analysis.bull_case_evidence
            + final_analysis.bear_case_evidence
            + [reference for theme in final_analysis.top_news_themes for reference in theme.evidence]
            + [
                reference
                for keyword in final_analysis.keyword_insights
                for reference in keyword.evidence
            ]
            + [
                reference
                for risk in final_analysis.risk_evidence
                for reference in risk.evidence
            ]
        )

        return final_analysis.model_copy(
            update={
                "source_references": final_source_references,
                "source_links": _unique_urls(final_source_references),
            }
        )

    @staticmethod
    def _build_artifact(
        *,
        refresh_job_id,
        stock_id,
        artifact_type: AIArtifactType,
        content_markdown: str,
        structured_payload: dict[str, Any],
        source_links: dict[str, Any],
        trace_payload: dict[str, Any],
        generated: GeneratedNarrative,
    ) -> AIArtifact:
        return AIArtifact(
            stock_id=stock_id,
            refresh_job_id=refresh_job_id,
            artifact_type=artifact_type,
            model_provider=generated.model_provider,
            model_name=generated.model_name,
            prompt_version=generated.prompt_version,
            status=JobStatus.SUCCESS,
            generated_at=datetime.now(UTC),
            content_markdown=content_markdown,
            structured_payload=structured_payload,
            source_links=source_links,
            trace_payload=trace_payload,
        )


def build_live_analysis_generator(settings: Settings) -> LiveAnalysisGenerator:
    if settings.ai_analysis_provider.lower() == "openai":
        if settings.openai_api_key:
            return OpenAIChatCompletionsGenerator(
                api_key=settings.openai_api_key,
                model=settings.ai_analysis_model,
                timeout_seconds=settings.ai_analysis_request_timeout_seconds,
                max_retries=settings.ai_analysis_max_retries,
                base_url=settings.ai_analysis_base_url,
                reasoning_effort=settings.ai_analysis_reasoning_effort,
                verbosity=settings.ai_analysis_verbosity,
            )
        logger.warning(
            "AI_ANALYSIS_PROVIDER is openai but OPENAI_API_KEY is empty; using heuristic fallback."
        )
    return HeuristicNarrativeGenerator()


def _missing_inputs(
    *,
    news_items: list[dict[str, Any]],
    announcements: list[dict[str, Any]],
    valuation: ValuationSnapshot | None,
    fundamentals: FinancialMetric | None,
    price_series: list[PriceBar],
    factor_payload: dict[str, Any] | None,
) -> list[str]:
    missing: list[str] = []
    if not news_items:
        missing.append("recent_news")
    if not announcements:
        missing.append("company_announcements")
    if valuation is None:
        missing.append("valuation_snapshot")
    if fundamentals is None:
        missing.append("financial_snapshot")
    if len(price_series) < 21:
        missing.append("price_history")
    if factor_payload is None:
        missing.append("factor_scores")
    return missing


def _valuation_payload(valuation: ValuationSnapshot | None) -> dict[str, Any] | None:
    if valuation is None:
        return None
    raw_payload = valuation.raw_payload or {}
    return {
        "as_of_date": valuation.as_of_date,
        "currency": valuation.currency or raw_payload.get("snapshot_currency") or raw_payload.get("currency"),
        "market_cap": float(valuation.market_cap) if valuation.market_cap is not None else None,
        "pe_ttm": float(valuation.pe_ttm) if valuation.pe_ttm is not None else None,
        "pe_forward": float(valuation.pe_forward) if valuation.pe_forward is not None else None,
        "pb": float(valuation.pb) if valuation.pb is not None else None,
        "ps_ttm": float(valuation.ps_ttm) if valuation.ps_ttm is not None else None,
        "enterprise_value": (
            float(valuation.enterprise_value) if valuation.enterprise_value is not None else None
        ),
        "ev_ebitda": (
            float(valuation.ev_ebitda) if valuation.ev_ebitda is not None else None
        ),
        "dividend_yield": (
            float(valuation.dividend_yield) if valuation.dividend_yield is not None else None
        ),
        "source_name": raw_payload.get("source_name"),
        "source_url": raw_payload.get("source_url"),
    }


def _fundamentals_payload(fundamentals: FinancialMetric | None) -> dict[str, Any] | None:
    if fundamentals is None:
        return None
    raw_payload = fundamentals.raw_payload or {}
    return {
        "report_date": fundamentals.report_date,
        "fiscal_year": fundamentals.fiscal_year,
        "fiscal_period": fundamentals.fiscal_period,
        "currency": fundamentals.currency,
        "revenue": float(fundamentals.revenue) if fundamentals.revenue is not None else None,
        "net_profit": (
            float(fundamentals.net_profit) if fundamentals.net_profit is not None else None
        ),
        "gross_margin": (
            float(fundamentals.gross_margin) if fundamentals.gross_margin is not None else None
        ),
        "operating_margin": (
            float(fundamentals.operating_margin)
            if fundamentals.operating_margin is not None
            else None
        ),
        "roe": float(fundamentals.roe) if fundamentals.roe is not None else None,
        "roa": float(fundamentals.roa) if fundamentals.roa is not None else None,
        "debt_to_equity": (
            float(fundamentals.debt_to_equity)
            if fundamentals.debt_to_equity is not None
            else None
        ),
        "overseas_revenue_ratio": (
            float(fundamentals.overseas_revenue_ratio)
            if fundamentals.overseas_revenue_ratio is not None
            else None
        ),
        "revenue_growth_yoy": (
            float(fundamentals.revenue_growth_yoy)
            if fundamentals.revenue_growth_yoy is not None
            else None
        ),
        "net_profit_growth_yoy": (
            float(fundamentals.net_profit_growth_yoy)
            if fundamentals.net_profit_growth_yoy is not None
            else None
        ),
        "source_name": raw_payload.get("source_name"),
        "source_url": raw_payload.get("source_url"),
    }


def _price_payload(price_series: list[PriceBar]) -> dict[str, Any] | None:
    if not price_series:
        return None

    def compute_return(days: int) -> float | None:
        if len(price_series) <= days:
            return None
        current = float(price_series[-1].close or 0)
        prior = float(price_series[-(days + 1)].close or 0)
        if prior == 0:
            return None
        return round((current / prior) - 1, 4)

    closes = [float(bar.close) for bar in price_series if bar.close is not None]
    if not closes:
        return None
    return {
        "latest_price": closes[-1],
        "latest_price_date": price_series[-1].trading_date,
        "return_1m": compute_return(21),
        "return_3m": compute_return(63),
        "return_6m": compute_return(126),
        "return_1y": compute_return(252),
        "high_1y": round(max(closes[-252:]), 4) if len(closes) >= 1 else None,
        "low_1y": round(min(closes[-252:]), 4) if len(closes) >= 1 else None,
    }


def _factor_payload(
    stock_score: StockScore | None,
    scoring_run: ScoringRun | None,
) -> dict[str, Any] | None:
    if stock_score is None or scoring_run is None:
        return None
    return {
        "as_of_date": scoring_run.run_date,
        "methodology_version": scoring_run.methodology_version,
        "fundamentals_quality": float(stock_score.fundamentals_score),
        "valuation_attractiveness": float(stock_score.valuation_score),
        "price_momentum": float(stock_score.momentum_score),
        "news_sentiment": float(stock_score.sentiment_score),
        "globalization_strength": float(stock_score.globalization_score),
        "total_score": float(stock_score.total_score),
        "rank": stock_score.rank,
    }


def _build_evidence_catalog(
    *,
    news_items: list[dict[str, Any]],
    announcements: list[dict[str, Any]],
    valuation: dict[str, Any] | None,
    fundamentals: dict[str, Any] | None,
    price_payload: dict[str, Any] | None,
    factor_payload: dict[str, Any] | None,
) -> dict[str, AnalysisEvidenceReferenceResponse]:
    catalog: dict[str, AnalysisEvidenceReferenceResponse] = {}

    for item in news_items:
        catalog[item["id"]] = AnalysisEvidenceReferenceResponse(
            reference_id=item["id"],
            reference_type="news_article",
            label=item["title"],
            url=item["url"],
            provider=item.get("provider"),
            published_at=_coerce_datetime(item.get("published_at")),
            source_url=item.get("source_url"),
        )
    for item in announcements:
        catalog[item["id"]] = AnalysisEvidenceReferenceResponse(
            reference_id=item["id"],
            reference_type="announcement",
            label=item["title"],
            url=item["url"],
            provider=item.get("provider") or "Company Filing",
            published_at=_coerce_datetime(item.get("published_at")),
            source_url=item.get("source_url"),
            as_of_date=_coerce_date(item.get("as_of_date")),
        )

    for reference in _valuation_metric_references(valuation):
        catalog[reference.reference_id] = reference
    for reference in _fundamental_metric_references(fundamentals):
        catalog[reference.reference_id] = reference

    if price_payload:
        latest_price_date = _coerce_date(price_payload.get("latest_price_date"))
        metric_rows = [
            ("metric:latest_price", "Latest Price", price_payload.get("latest_price"), None),
            ("metric:return_1m", "1M Return", price_payload.get("return_1m"), "ratio"),
            ("metric:return_3m", "3M Return", price_payload.get("return_3m"), "ratio"),
            ("metric:return_1y", "1Y Return", price_payload.get("return_1y"), "ratio"),
            ("metric:high_1y", "1Y High", price_payload.get("high_1y"), None),
            ("metric:low_1y", "1Y Low", price_payload.get("low_1y"), None),
        ]
        for reference_id, label, value, metric_unit in metric_rows:
            if value is None:
                continue
            catalog[reference_id] = AnalysisEvidenceReferenceResponse(
                reference_id=reference_id,
                reference_type="metric",
                label=label,
                metric_key=reference_id.replace("metric:", ""),
                metric_value=value,
                metric_unit=metric_unit,
                as_of_date=latest_price_date,
            )

    if factor_payload:
        scoring_date = _coerce_date(factor_payload.get("as_of_date"))
        factor_rows = [
            ("metric:factor_total_score", "Total Score", factor_payload.get("total_score"), "score"),
            ("metric:factor_rank", "Universe Rank", factor_payload.get("rank"), "rank"),
            (
                "metric:factor_fundamentals_quality",
                "Fundamentals Quality Score",
                factor_payload.get("fundamentals_quality"),
                "score",
            ),
            (
                "metric:factor_valuation_attractiveness",
                "Valuation Attractiveness Score",
                factor_payload.get("valuation_attractiveness"),
                "score",
            ),
            (
                "metric:factor_price_momentum",
                "Price Momentum Score",
                factor_payload.get("price_momentum"),
                "score",
            ),
            (
                "metric:factor_news_sentiment",
                "News Sentiment Score",
                factor_payload.get("news_sentiment"),
                "score",
            ),
            (
                "metric:factor_globalization_strength",
                "Globalization Strength Score",
                factor_payload.get("globalization_strength"),
                "score",
            ),
        ]
        for reference_id, label, value, metric_unit in factor_rows:
            if value is None:
                continue
            catalog[reference_id] = AnalysisEvidenceReferenceResponse(
                reference_id=reference_id,
                reference_type="metric",
                label=label,
                metric_key=reference_id.replace("metric:", ""),
                metric_value=value,
                metric_unit=metric_unit,
                as_of_date=scoring_date,
            )

    return catalog


def _build_evidence_payloads(
    *,
    evidence_catalog: dict[str, AnalysisEvidenceReferenceResponse],
    news_items: list[dict[str, Any]],
    announcements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    news_lookup = {item["id"]: item for item in news_items}
    announcement_lookup = {item["id"]: item for item in announcements}

    payloads: list[dict[str, Any]] = []
    for reference_id, reference in evidence_catalog.items():
        payload: dict[str, Any] = {
            "id": reference_id,
            "type": reference.reference_type,
            "label": reference.label,
            "provider": reference.provider,
            "published_at": (
                reference.published_at.isoformat() if reference.published_at else None
            ),
            "metric_key": reference.metric_key,
            "metric_value": reference.metric_value,
            "metric_unit": reference.metric_unit,
            "as_of_date": reference.as_of_date.isoformat() if reference.as_of_date else None,
        }
        if reference.reference_type == "news_article" and reference_id in news_lookup:
            payload["summary"] = news_lookup[reference_id].get("summary")
        elif reference.reference_type == "announcement" and reference_id in announcement_lookup:
            payload["summary"] = announcement_lookup[reference_id].get("summary")
            payload["category"] = announcement_lookup[reference_id].get("category")
            payload["exchange_code"] = announcement_lookup[reference_id].get("exchange_code")
            payload["language"] = announcement_lookup[reference_id].get("language")
        payloads.append(payload)
    return payloads


def _apply_missing_input_guards(
    analysis: StockAnalysisResponse,
    missing_inputs: list[str],
    company_name: str,
) -> StockAnalysisResponse:
    updates: dict[str, Any] = {}
    missing = set(missing_inputs)

    if "recent_news" in missing and "company_announcements" in missing:
        updates.update(
            {
                "top_news_themes": [],
                "keywords": [],
                "keyword_insights": [],
                "sentiment_score": None,
                "sentiment_label": None,
                "sentiment_evidence": [],
            }
        )

    if {"recent_news", "valuation_snapshot", "financial_snapshot", "price_history"} <= missing:
        updates.update(
            {
                "summary": (
                    f"Insufficient live inputs to generate a complete thesis for {company_name}. "
                    "Load recent news, price history, and fundamentals to produce a fuller view."
                ),
                "summary_evidence": [],
                "bull_case": "Insufficient live evidence to articulate a supported bull case.",
                "bull_case_evidence": [],
                "bear_case": "Insufficient live evidence to articulate a supported bear case.",
                "bear_case_evidence": [],
                "key_risks": ["Live inputs are incomplete, so thesis risk framing is currently limited."],
                "risk_evidence": [],
            }
        )

    return analysis.model_copy(update=updates) if updates else analysis


def _remap_analysis_references(
    analysis: StockAnalysisResponse,
    evidence_catalog: dict[str, AnalysisEvidenceReferenceResponse],
) -> StockAnalysisResponse:
    def remap_list(
        references: Sequence[AnalysisEvidenceReferenceResponse],
    ) -> list[AnalysisEvidenceReferenceResponse]:
        remapped: list[AnalysisEvidenceReferenceResponse] = []
        for reference in references:
            remapped.append(evidence_catalog.get(reference.reference_id, reference))
        return remapped

    top_news_themes = [
        AnalysisThemeResponse(
            theme=theme.theme,
            article_count=theme.article_count,
            sentiment_score=theme.sentiment_score,
            sentiment_label=theme.sentiment_label,
            summary=theme.summary,
            evidence=remap_list(theme.evidence),
        )
        for theme in analysis.top_news_themes
    ]
    keyword_insights = [
        AnalysisKeywordInsightResponse(
            keyword=keyword.keyword,
            mentions=keyword.mentions,
            evidence=remap_list(keyword.evidence),
        )
        for keyword in analysis.keyword_insights
    ]
    risk_evidence = [
        AnalysisRiskInsightResponse(
            risk=risk.risk,
            evidence=remap_list(risk.evidence),
        )
        for risk in analysis.risk_evidence
    ]
    source_references = _dedupe_references(
        remap_list(analysis.summary_evidence)
        + remap_list(analysis.valuation_evidence)
        + remap_list(analysis.bull_case_evidence)
        + remap_list(analysis.bear_case_evidence)
        + remap_list(analysis.sentiment_evidence)
        + [reference for theme in top_news_themes for reference in theme.evidence]
        + [reference for keyword in keyword_insights for reference in keyword.evidence]
        + [reference for risk in risk_evidence for reference in risk.evidence]
    )
    return analysis.model_copy(
        update={
            "summary_evidence": remap_list(analysis.summary_evidence),
            "top_news_themes": top_news_themes,
            "valuation_evidence": remap_list(analysis.valuation_evidence),
            "bull_case_evidence": remap_list(analysis.bull_case_evidence),
            "bear_case_evidence": remap_list(analysis.bear_case_evidence),
            "keyword_insights": keyword_insights,
            "risk_evidence": risk_evidence,
            "sentiment_evidence": remap_list(analysis.sentiment_evidence),
            "source_references": source_references,
            "source_links": _unique_urls(source_references),
        }
    )


def _resolve_references(
    evidence_catalog: dict[str, AnalysisEvidenceReferenceResponse],
    reference_ids: Sequence[str],
    *,
    fallback: Sequence[AnalysisEvidenceReferenceResponse] | None = None,
) -> list[AnalysisEvidenceReferenceResponse]:
    resolved = [
        evidence_catalog[reference_id]
        for reference_id in reference_ids
        if reference_id in evidence_catalog
    ]
    if resolved:
        return _dedupe_references(resolved)
    return list(fallback or [])


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        candidate = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        candidate = value.split("T", 1)[0]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def validate_live_narrative_payload(payload: str | bytes | dict[str, Any]) -> LiveAnalysisNarrativeDraft:
    if isinstance(payload, dict):
        return LiveAnalysisNarrativeDraft.model_validate(payload)
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        return LiveAnalysisNarrativeDraft.model_validate_json(payload)
    except ValidationError:
        if isinstance(payload, str):
            return LiveAnalysisNarrativeDraft.model_validate(json.loads(payload))
        raise


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value
