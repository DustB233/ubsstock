from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from china_outbound_analyzer.schemas.metadata import (
    AIMethodologyResponse,
    AIMethodologySectionResponse,
)
from china_outbound_analyzer.schemas.stock_views import (
    AnalysisEvidenceReferenceResponse,
    AnalysisKeywordInsightResponse,
    AnalysisRiskInsightResponse,
    AnalysisThemeResponse,
    StockAnalysisResponse,
)

SCHEMA_VERSION = "analysis-v2"
METHODOLOGY_SCHEMA_VERSION = "ai-methodology-v2"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "by",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "item",
    "more",
    "news",
    "phase",
    "pipeline",
    "recent",
    "that",
    "the",
    "their",
    "this",
    "with",
}

POSITIVE_WORDS = {
    "accelerate",
    "accelerates",
    "approval",
    "beat",
    "beats",
    "benefit",
    "demand",
    "expand",
    "expansion",
    "gain",
    "gains",
    "growth",
    "improve",
    "improves",
    "launch",
    "momentum",
    "positive",
    "profit",
    "record",
    "recovery",
    "stabilize",
    "stabilizes",
    "strength",
    "strengthens",
    "upgrade",
    "wins",
}

NEGATIVE_WORDS = {
    "caution",
    "competition",
    "cut",
    "cuts",
    "delay",
    "delays",
    "downgrade",
    "fall",
    "falls",
    "headwind",
    "intensifies",
    "investigation",
    "negative",
    "pressure",
    "probe",
    "regulatory",
    "risk",
    "slowdown",
    "tariff",
    "weak",
}

THEME_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Global Demand & Exports",
        (
            "demand",
            "export",
            "exports",
            "global",
            "international",
            "market",
            "order",
            "orders",
            "overseas",
            "sales",
            "shipment",
        ),
    ),
    (
        "Margins & Earnings",
        (
            "earnings",
            "guidance",
            "margin",
            "margins",
            "profit",
            "profits",
            "quarter",
            "quarterly",
            "results",
            "revenue",
        ),
    ),
    (
        "Capacity & Expansion",
        (
            "capacity",
            "dealer",
            "expansion",
            "factory",
            "launch",
            "plant",
            "production",
            "rollout",
            "store",
            "supply",
        ),
    ),
    (
        "Competition & Regulation",
        (
            "caution",
            "competition",
            "delay",
            "pricing",
            "probe",
            "regulation",
            "regulatory",
            "risk",
            "tariff",
            "pressure",
        ),
    ),
    (
        "Technology & Pipeline",
        (
            "ai",
            "approval",
            "battery",
            "clinical",
            "drug",
            "innovation",
            "model",
            "pipeline",
            "robot",
            "sensor",
            "technology",
        ),
    ),
)


@dataclass(frozen=True)
class NormalizedNewsItem:
    reference_id: str
    title: str
    summary: str
    url: str
    provider: str | None
    published_at: datetime | None
    source_url: str | None


def build_stock_analysis_response(
    *,
    slug: str,
    symbol: str,
    company_name: str,
    company_name_zh: str | None,
    sector: str,
    outbound_theme: str,
    news_items: list[dict[str, Any] | Any],
    valuation: dict[str, Any] | Any | None,
    fundamentals: dict[str, Any] | Any | None,
    generated_at: datetime | None = None,
) -> StockAnalysisResponse:
    normalized_news = _normalize_news_items(news_items)
    generated_timestamp = generated_at or _fallback_generated_at(normalized_news)

    ignored_tokens = _company_stopwords(company_name, company_name_zh, slug, symbol)
    article_scores = {item.reference_id: _article_sentiment(item) for item in normalized_news}
    theme_groups = _group_themes(normalized_news, article_scores)
    top_themes = _build_theme_responses(theme_groups)
    keyword_insights = _build_keyword_insights(normalized_news, ignored_tokens)
    keywords = [item.keyword for item in keyword_insights]

    overall_sentiment = _aggregate_sentiment(article_scores.values())
    sentiment_label = _sentiment_label(overall_sentiment)
    sentiment_evidence = _dedupe_references(
        [
            _news_reference(item)
            for item in sorted(
                normalized_news,
                key=lambda entry: entry.published_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )[:4]
        ]
    )

    valuation_evidence = _valuation_metric_references(valuation)
    fundamentals_evidence = _fundamental_metric_references(fundamentals)
    valuation_posture = _valuation_posture(valuation)
    growth_descriptor = _growth_descriptor(fundamentals)
    lead_theme = top_themes[0] if top_themes else None
    caution_theme = _pick_caution_theme(top_themes)

    valuation_summary = _valuation_summary_text(
        company_name=company_name,
        valuation=valuation,
        fundamentals=fundamentals,
        valuation_posture=valuation_posture,
    )
    bull_case = _bull_case_text(
        company_name=company_name,
        lead_theme=lead_theme.theme if lead_theme else None,
        fundamentals=fundamentals,
        valuation_posture=valuation_posture,
        sentiment_label=sentiment_label,
    )
    bear_case = _bear_case_text(
        company_name=company_name,
        caution_theme=caution_theme.theme if caution_theme else None,
        valuation=valuation,
        fundamentals=fundamentals,
        valuation_posture=valuation_posture,
        sentiment_label=sentiment_label,
    )
    risk_evidence = _risk_insights(
        sector=sector,
        outbound_theme=outbound_theme,
        lead_theme=lead_theme,
        caution_theme=caution_theme,
        valuation_evidence=valuation_evidence,
        fundamentals_evidence=fundamentals_evidence,
    )
    key_risks = [item.risk for item in risk_evidence]

    summary_evidence = _dedupe_references(
        (lead_theme.evidence if lead_theme else [])
        + valuation_evidence[:2]
        + fundamentals_evidence[:2]
    )
    investment_takeaway = _investment_takeaway_text(
        company_name=company_name,
        lead_theme=lead_theme.theme if lead_theme else None,
        secondary_theme=top_themes[1].theme if len(top_themes) > 1 else None,
        sentiment_label=sentiment_label,
        valuation_posture=valuation_posture,
        growth_descriptor=growth_descriptor,
    )

    bull_case_evidence = _dedupe_references(
        (lead_theme.evidence if lead_theme else []) + fundamentals_evidence[:3] + valuation_evidence[:1]
    )
    bear_case_evidence = _dedupe_references(
        (caution_theme.evidence if caution_theme else [])
        + valuation_evidence[:2]
        + fundamentals_evidence[:1]
    )
    source_references = _dedupe_references(
        summary_evidence
        + sentiment_evidence
        + valuation_evidence
        + fundamentals_evidence
        + [reference for theme in top_themes for reference in theme.evidence]
    )
    source_links = _unique_urls(source_references)

    return StockAnalysisResponse(
        slug=slug,
        symbol=symbol,
        schema_version=SCHEMA_VERSION,
        generated_at=generated_timestamp,
        summary=investment_takeaway,
        summary_evidence=summary_evidence,
        top_news_themes=top_themes,
        valuation_summary=valuation_summary,
        valuation_evidence=valuation_evidence,
        bull_case=bull_case,
        bull_case_evidence=bull_case_evidence,
        bear_case=bear_case,
        bear_case_evidence=bear_case_evidence,
        key_risks=key_risks,
        risk_evidence=risk_evidence,
        keywords=keywords,
        keyword_insights=keyword_insights,
        sentiment_label=sentiment_label,
        sentiment_score=overall_sentiment,
        sentiment_evidence=sentiment_evidence,
        source_references=source_references,
        source_links=source_links,
    )


def build_ai_methodology() -> AIMethodologyResponse:
    return AIMethodologyResponse(
        schema_version=METHODOLOGY_SCHEMA_VERSION,
        headline="AI is an accelerator for evidence synthesis, not a substitute for investment judgment.",
        sections=[
            AIMethodologySectionResponse(
                title="Strengths of AI in stock analysis",
                body=(
                    "The analysis layer is strongest when it has structured metrics and fresh source coverage. "
                    "It can compress large news sets into a comparable view quickly, keep factor narratives "
                    "consistent across the 15-stock universe, and surface the exact sources behind each claim."
                ),
                bullets=[
                    "Clusters repeated headlines into a small number of decision-useful themes.",
                    "Applies the same deterministic framing to valuation, sentiment, and risk language.",
                    "Keeps source provenance and metric references attached to each narrative block.",
                ],
                tone="strength",
            ),
            AIMethodologySectionResponse(
                title="Limitations of AI",
                body=(
                    "The analysis still inherits the blind spots of the source set and the heuristic rules behind "
                    "the narrative engine. It can overreact to noisy headlines, miss regime shifts, and underweight "
                    "facts that are not yet reflected in company news or reported metrics."
                ),
                bullets=[
                    "Headline sentiment is an input, not a full representation of market positioning.",
                    "Valuation interpretation is heuristic and should not replace full peer or cycle work.",
                    "Sparse or low-quality coverage can make themes look cleaner than reality.",
                ],
                tone="limitation",
            ),
            AIMethodologySectionResponse(
                title="Why human review remains required",
                body=(
                    "Human review is still the final control layer for governance, industry structure, position sizing, "
                    "and macro sensitivity. The app is designed to make that review faster by keeping the recommendation "
                    "auditable rather than by pretending the AI output is self-sufficient."
                ),
                bullets=[
                    "Validate whether the cited evidence is still current and relevant.",
                    "Stress-test the narrative against live valuation, liquidity, and portfolio constraints.",
                    "Challenge the AI framing whenever the market regime or company context has shifted.",
                ],
                tone="human_review",
            ),
        ],
    )


def _normalize_news_items(news_items: list[dict[str, Any] | Any]) -> list[NormalizedNewsItem]:
    normalized: list[NormalizedNewsItem] = []
    for item in news_items:
        title = str(_get_value(item, "title") or "").strip()
        url = str(_get_value(item, "url") or "").strip()
        if not title or not url:
            continue
        summary = str(_get_value(item, "summary") or "").strip()
        reference_id = str(
            _get_value(item, "reference_id")
            or _get_value(item, "external_id")
            or _get_value(item, "id")
            or url
        )
        normalized.append(
            NormalizedNewsItem(
                reference_id=reference_id,
                title=title,
                summary=summary,
                url=url,
                provider=_string_or_none(_get_value(item, "provider")),
                published_at=_coerce_datetime(_get_value(item, "published_at")),
                source_url=_string_or_none(
                    _get_value(item, "source_url")
                    or _get_nested_value(item, "raw_payload", "source_url")
                ),
            )
        )
    return normalized


def _fallback_generated_at(news_items: list[NormalizedNewsItem]) -> datetime:
    latest = max((item.published_at for item in news_items if item.published_at is not None), default=None)
    return latest or datetime.now(UTC)


def _article_sentiment(item: NormalizedNewsItem) -> float:
    tokens = set(_tokenize(f"{item.title} {item.summary}"))
    positive_hits = len(tokens & POSITIVE_WORDS)
    negative_hits = len(tokens & NEGATIVE_WORDS)
    if positive_hits == negative_hits == 0:
        return 0.0
    return round((positive_hits - negative_hits) / max(positive_hits + negative_hits, 1), 4)


def _aggregate_sentiment(scores: Any) -> float:
    score_list = list(scores)
    if not score_list:
        return 0.0
    return round(sum(score_list) / len(score_list), 4)


def _sentiment_label(score: float) -> str:
    if score >= 0.2:
        return "POSITIVE"
    if score <= -0.2:
        return "NEGATIVE"
    return "NEUTRAL"


def _group_themes(
    news_items: list[NormalizedNewsItem],
    article_scores: dict[str, float],
) -> dict[str, list[NormalizedNewsItem]]:
    grouped: dict[str, list[NormalizedNewsItem]] = defaultdict(list)
    for item in news_items:
        grouped[_classify_theme(item)].append(item)
    return grouped


def _build_theme_responses(
    theme_groups: dict[str, list[NormalizedNewsItem]],
) -> list[AnalysisThemeResponse]:
    ranked_groups = sorted(
        theme_groups.items(),
        key=lambda item: (
            -len(item[1]),
            -_latest_timestamp(item[1]).timestamp(),
            item[0],
        ),
    )[:3]

    theme_responses: list[AnalysisThemeResponse] = []
    for label, items in ranked_groups:
        theme_sentiment = _aggregate_sentiment(_article_sentiment(item) for item in items)
        theme_keywords = _extract_keywords(
            [f"{item.title} {item.summary}" for item in items],
            limit=3,
            ignored_tokens=set(),
        )
        evidence = _dedupe_references([_news_reference(item) for item in items[:3]])
        summary = (
            f"{len(items)} recent articles center on {label.lower()} with "
            f"{_sentiment_label(theme_sentiment).lower()} tone"
        )
        if theme_keywords:
            summary += f" and repeated mentions of {', '.join(theme_keywords)}"
        summary += "."
        theme_responses.append(
            AnalysisThemeResponse(
                theme=label,
                article_count=len(items),
                sentiment_score=theme_sentiment,
                sentiment_label=_sentiment_label(theme_sentiment),
                summary=summary,
                evidence=evidence,
            )
        )
    return theme_responses


def _build_keyword_insights(
    news_items: list[NormalizedNewsItem],
    ignored_tokens: set[str],
) -> list[AnalysisKeywordInsightResponse]:
    counter: Counter[str] = Counter()
    evidence_map: dict[str, list[AnalysisEvidenceReferenceResponse]] = defaultdict(list)

    for item in news_items:
        seen_for_article: set[str] = set()
        for token in _tokenize(f"{item.title} {item.summary}"):
            if token in ignored_tokens or len(token) < 4:
                continue
            counter[token] += 1
            if token not in seen_for_article:
                evidence_map[token].append(_news_reference(item))
                seen_for_article.add(token)

    keyword_insights: list[AnalysisKeywordInsightResponse] = []
    for keyword, mentions in counter.most_common(5):
        keyword_insights.append(
            AnalysisKeywordInsightResponse(
                keyword=keyword,
                mentions=mentions,
                evidence=_dedupe_references(evidence_map[keyword][:3]),
            )
        )
    return keyword_insights


def _valuation_summary_text(
    *,
    company_name: str,
    valuation: dict[str, Any] | Any | None,
    fundamentals: dict[str, Any] | Any | None,
    valuation_posture: str,
) -> str:
    pe = _metric_number(valuation, "pe_ttm")
    pb = _metric_number(valuation, "pb")
    ps = _metric_number(valuation, "ps_ttm")
    revenue_growth = _metric_number(fundamentals, "revenue_growth_yoy", percentage=True)
    profit_growth = _metric_number(fundamentals, "net_profit_growth_yoy", percentage=True)

    if pe is None and pb is None and ps is None:
        return f"No valuation snapshot is available yet for {company_name}."

    summary = (
        f"{company_name} screens as {valuation_posture} on current multiples with "
        f"PE {_format_multiple(pe)}, PB {_format_multiple(pb)}, and PS {_format_multiple(ps)}."
    )
    if revenue_growth is not None and profit_growth is not None:
        summary += (
            f" The latest reported growth profile was revenue {revenue_growth:.1f}% and "
            f"net profit {profit_growth:.1f}% year over year."
        )
    return summary


def _bull_case_text(
    *,
    company_name: str,
    lead_theme: str | None,
    fundamentals: dict[str, Any] | Any | None,
    valuation_posture: str,
    sentiment_label: str,
) -> str:
    revenue_growth = _metric_number(fundamentals, "revenue_growth_yoy", percentage=True)
    profit_growth = _metric_number(fundamentals, "net_profit_growth_yoy", percentage=True)
    roe = _metric_number(fundamentals, "roe", percentage=True)

    components: list[str] = []
    if lead_theme:
        components.append(f"{lead_theme.lower()} staying supportive")
    if revenue_growth is not None and profit_growth is not None:
        components.append(
            f"revenue growth of {revenue_growth:.1f}% and net profit growth of {profit_growth:.1f}%"
        )
    if roe is not None:
        components.append(f"ROE of {roe:.1f}%")

    if components:
        sentence = f"{company_name}'s bull case rests on " + ", ".join(components) + "."
    else:
        sentence = (
            f"{company_name}'s bull case depends on the outbound narrative continuing to convert "
            "into consistent execution."
        )
    sentence += (
        f" If execution stays intact and news flow remains {sentiment_label.lower()}, the market can "
        f"continue to accept a {valuation_posture} valuation posture."
    )
    return sentence


def _bear_case_text(
    *,
    company_name: str,
    caution_theme: str | None,
    valuation: dict[str, Any] | Any | None,
    fundamentals: dict[str, Any] | Any | None,
    valuation_posture: str,
    sentiment_label: str,
) -> str:
    pe = _metric_number(valuation, "pe_ttm")
    ps = _metric_number(valuation, "ps_ttm")
    gross_margin = _metric_number(fundamentals, "gross_margin", percentage=True)

    sentence = (
        f"The bear case is that {company_name}'s {valuation_posture} setup leaves less room for error, "
        f"especially with PE {_format_multiple(pe)} and PS {_format_multiple(ps)}."
    )
    if caution_theme:
        sentence += f" Recent coverage around {caution_theme.lower()} raises the risk of expectation reset."
    if gross_margin is not None:
        sentence += f" Gross margin at {gross_margin:.1f}% also leaves the story exposed if pricing pressure rises."
    else:
        sentence += f" A {sentiment_label.lower()} headline mix would matter more if fundamentals soften."
    return sentence


def _risk_insights(
    *,
    sector: str,
    outbound_theme: str,
    lead_theme: AnalysisThemeResponse | None,
    caution_theme: AnalysisThemeResponse | None,
    valuation_evidence: list[AnalysisEvidenceReferenceResponse],
    fundamentals_evidence: list[AnalysisEvidenceReferenceResponse],
) -> list[AnalysisRiskInsightResponse]:
    sector_lower = sector.lower()
    theme_lower = outbound_theme.lower()

    sector_specific_risk = "Sector-specific execution risk"
    if "biopharma" in sector_lower or "medical" in sector_lower:
        sector_specific_risk = "Clinical, regulatory, and commercialization timing risk"
    elif "construction" in sector_lower or "power" in sector_lower or "oilfield" in sector_lower:
        sector_specific_risk = "Global capex-cycle and project timing risk"
    elif "consumer" in sector_lower or "smart home" in sector_lower:
        sector_specific_risk = "Product-cycle and channel inventory risk"
    elif "battery" in sector_lower or "electronics" in sector_lower or "sensor" in sector_lower:
        sector_specific_risk = "Technology transition and pricing pressure risk"

    geography_risk = "Overseas demand execution risk"
    if "export" in theme_lower or "overseas" in theme_lower or "global" in theme_lower:
        geography_risk = "Overseas demand, local execution, and channel scaling risk"

    margin_risk = "Multiple compression and margin pressure risk"
    if caution_theme and "competition" in caution_theme.theme.lower():
        margin_risk = "Competition-driven pricing and multiple compression risk"

    evidence_primary = (lead_theme.evidence if lead_theme else []) + fundamentals_evidence[:2]
    evidence_caution = (caution_theme.evidence if caution_theme else []) + valuation_evidence[:2]

    return [
        AnalysisRiskInsightResponse(
            risk=geography_risk,
            evidence=_dedupe_references(evidence_primary[:3]),
        ),
        AnalysisRiskInsightResponse(
            risk=margin_risk,
            evidence=_dedupe_references(evidence_caution[:3]),
        ),
        AnalysisRiskInsightResponse(
            risk=sector_specific_risk,
            evidence=_dedupe_references(fundamentals_evidence[:2] + valuation_evidence[:1]),
        ),
    ]


def _investment_takeaway_text(
    *,
    company_name: str,
    lead_theme: str | None,
    secondary_theme: str | None,
    sentiment_label: str,
    valuation_posture: str,
    growth_descriptor: str,
) -> str:
    stance = "balanced"
    if sentiment_label == "POSITIVE" and growth_descriptor == "strong" and valuation_posture != "demanding":
        stance = "constructive"
    elif sentiment_label == "NEGATIVE" or valuation_posture == "demanding":
        stance = "cautious"

    summary = f"{company_name} currently reads as a {stance} outbound story."
    theme_clause = ""
    if lead_theme:
        theme_clause = f" The dominant news theme is {lead_theme.lower()}"
    if secondary_theme:
        theme_clause += f", with a secondary focus on {secondary_theme.lower()}"
    if theme_clause:
        summary += f"{theme_clause}."
    summary += (
        f" Sentiment is {sentiment_label.lower()}, valuation looks {valuation_posture}, "
        f"and the latest fundamental profile looks {growth_descriptor}."
    )
    if stance == "constructive":
        summary += " That combination supports leaning positive while keeping an eye on entry discipline."
    elif stance == "cautious":
        summary += " The setup is investable only if execution continues to validate expectations."
    else:
        summary += " The name needs continued evidence on both execution and valuation before conviction rises."
    return summary


def _valuation_posture(valuation: dict[str, Any] | Any | None) -> str:
    pe = _metric_number(valuation, "pe_ttm")
    pb = _metric_number(valuation, "pb")
    ps = _metric_number(valuation, "ps_ttm")

    if pe is None and pb is None and ps is None:
        return "unavailable"
    if (pe is not None and pe <= 18) and ((pb is not None and pb <= 3.5) or (ps is not None and ps <= 2.5)):
        return "relatively attractive"
    if (pe is not None and pe >= 32) or (ps is not None and ps >= 6):
        return "demanding"
    return "balanced"


def _growth_descriptor(fundamentals: dict[str, Any] | Any | None) -> str:
    revenue_growth = _metric_number(fundamentals, "revenue_growth_yoy", percentage=True)
    profit_growth = _metric_number(fundamentals, "net_profit_growth_yoy", percentage=True)
    roe = _metric_number(fundamentals, "roe", percentage=True)

    score = 0
    if revenue_growth is not None and revenue_growth >= 15:
        score += 1
    if profit_growth is not None and profit_growth >= 15:
        score += 1
    if roe is not None and roe >= 15:
        score += 1

    if score >= 2:
        return "strong"
    if score == 1:
        return "mixed"
    return "soft"


def _pick_caution_theme(themes: list[AnalysisThemeResponse]) -> AnalysisThemeResponse | None:
    for theme in themes:
        if theme.sentiment_label == "NEGATIVE" or "competition" in theme.theme.lower():
            return theme
    return themes[-1] if themes else None


def _valuation_metric_references(
    valuation: dict[str, Any] | Any | None,
) -> list[AnalysisEvidenceReferenceResponse]:
    as_of_date = _coerce_date(_get_value(valuation, "as_of_date"))
    metrics = [
        ("market_cap", "Market Cap", _metric_number(valuation, "market_cap"), None),
        ("pe_ttm", "PE (TTM)", _metric_number(valuation, "pe_ttm"), "x"),
        ("pb", "PB", _metric_number(valuation, "pb"), "x"),
        ("ps_ttm", "PS (TTM)", _metric_number(valuation, "ps_ttm"), "x"),
        ("ev_ebitda", "EV / EBITDA", _metric_number(valuation, "ev_ebitda"), "x"),
        (
            "dividend_yield",
            "Dividend Yield",
            _metric_number(valuation, "dividend_yield", percentage=True),
            "%",
        ),
    ]

    references: list[AnalysisEvidenceReferenceResponse] = []
    for metric_key, label, value, unit in metrics:
        if value is None:
            continue
        references.append(
            AnalysisEvidenceReferenceResponse(
                reference_id=f"metric:{metric_key}",
                reference_type="metric",
                label=label,
                metric_key=metric_key,
                metric_value=round(value, 4) if isinstance(value, float) else value,
                metric_unit=unit,
                as_of_date=as_of_date,
            )
        )
    return references


def _fundamental_metric_references(
    fundamentals: dict[str, Any] | Any | None,
) -> list[AnalysisEvidenceReferenceResponse]:
    report_date = _coerce_date(_get_value(fundamentals, "report_date"))
    metrics = [
        (
            "revenue_growth_yoy",
            "Revenue Growth YoY",
            _metric_number(fundamentals, "revenue_growth_yoy", percentage=True),
            "%",
        ),
        (
            "net_profit_growth_yoy",
            "Net Profit Growth YoY",
            _metric_number(fundamentals, "net_profit_growth_yoy", percentage=True),
            "%",
        ),
        ("gross_margin", "Gross Margin", _metric_number(fundamentals, "gross_margin", percentage=True), "%"),
        ("roe", "ROE", _metric_number(fundamentals, "roe", percentage=True), "%"),
    ]

    references: list[AnalysisEvidenceReferenceResponse] = []
    for metric_key, label, value, unit in metrics:
        if value is None:
            continue
        references.append(
            AnalysisEvidenceReferenceResponse(
                reference_id=f"metric:{metric_key}",
                reference_type="metric",
                label=label,
                metric_key=metric_key,
                metric_value=round(value, 4) if isinstance(value, float) else value,
                metric_unit=unit,
                as_of_date=report_date,
            )
        )
    return references


def _classify_theme(item: NormalizedNewsItem) -> str:
    text = f"{item.title} {item.summary}"
    tokens = set(_tokenize(text))
    best_label = ""
    best_score = -1
    for label, keywords in THEME_BUCKETS:
        score = sum(keyword in tokens for keyword in keywords)
        if score > best_score:
            best_label = label
            best_score = score
    if best_score > 0:
        return best_label
    return _fallback_theme_label(item.title)


def _fallback_theme_label(title: str) -> str:
    if ": " in title:
        candidate = title.split(": ", 1)[1]
    else:
        candidate = title
    cleaned = " ".join(token.capitalize() for token in _tokenize(candidate)[:4])
    return cleaned or "Company Update"


def _extract_keywords(
    texts: list[str],
    *,
    limit: int,
    ignored_tokens: set[str],
) -> list[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for token in _tokenize(text):
            if token in ignored_tokens or len(token) < 4:
                continue
            counter[token] += 1
    return [keyword for keyword, _count in counter.most_common(limit)]


def _company_stopwords(
    company_name: str,
    company_name_zh: str | None,
    slug: str,
    symbol: str,
) -> set[str]:
    ignored = set(STOPWORDS)
    ignored.update(_tokenize(company_name))
    ignored.update(_tokenize(company_name_zh or ""))
    ignored.update(_tokenize(slug.replace("-", " ")))
    ignored.update(_tokenize(symbol.replace(".", " ")))
    return ignored


def _tokenize(text: str) -> list[str]:
    normalized = (
        text.lower()
        .replace("’", " ")
        .replace("'", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("/", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("-", " ")
    )
    return [token for token in normalized.split() if token and token not in STOPWORDS and not token.isdigit()]


def _news_reference(item: NormalizedNewsItem) -> AnalysisEvidenceReferenceResponse:
    return AnalysisEvidenceReferenceResponse(
        reference_id=item.reference_id,
        reference_type="news_article",
        label=item.title,
        url=item.url,
        provider=item.provider,
        published_at=item.published_at,
        source_url=item.source_url,
    )


def _dedupe_references(
    references: list[AnalysisEvidenceReferenceResponse],
) -> list[AnalysisEvidenceReferenceResponse]:
    seen: set[str] = set()
    deduped: list[AnalysisEvidenceReferenceResponse] = []
    for reference in references:
        if reference.reference_id in seen:
            continue
        seen.add(reference.reference_id)
        deduped.append(reference)
    return deduped


def _unique_urls(references: list[AnalysisEvidenceReferenceResponse]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for reference in references:
        if reference.url and reference.url not in seen:
            seen.add(reference.url)
            urls.append(reference.url)
    return urls


def _latest_timestamp(items: list[NormalizedNewsItem]) -> datetime:
    latest = max((item.published_at for item in items if item.published_at is not None), default=None)
    return latest or datetime.min.replace(tzinfo=UTC)


def _metric_number(
    source: dict[str, Any] | Any | None,
    key: str,
    *,
    percentage: bool = False,
) -> float | None:
    value = _get_value(source, key)
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric * 100, 4) if percentage else round(numeric, 4)


def _format_multiple(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}x"


def _get_nested_value(source: dict[str, Any] | Any | None, parent: str, child: str) -> Any:
    nested = _get_value(source, parent)
    if isinstance(nested, dict):
        return nested.get(child)
    return getattr(nested, child, None) if nested is not None else None


def _get_value(source: dict[str, Any] | Any | None, key: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


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


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
