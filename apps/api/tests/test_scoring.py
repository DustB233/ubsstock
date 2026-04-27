from china_outbound_analyzer.models.entities import AIArtifact
from china_outbound_analyzer.services.recommendation.scoring import (
    FactorScores,
    RankedStock,
    ScoringService,
    percentile_rank_map,
    select_long_and_short,
    weighted_total,
)


def test_percentile_rank_map_rewards_higher_values() -> None:
    ranked = percentile_rank_map({"a": 10.0, "b": 20.0, "c": 30.0}, higher_is_better=True)

    assert ranked["c"] == 100.0
    assert ranked["b"] == 50.0
    assert ranked["a"] == 0.0


def test_percentile_rank_map_rewards_lower_values_when_inverted() -> None:
    ranked = percentile_rank_map(
        {"cheap": 8.0, "mid": 15.0, "expensive": 30.0},
        higher_is_better=False,
    )

    assert ranked["cheap"] == 100.0
    assert ranked["mid"] == 50.0
    assert ranked["expensive"] == 0.0


def test_weighted_total_matches_requested_factor_weights() -> None:
    total = weighted_total(
        {
            "fundamentals_quality": 80.0,
            "valuation_attractiveness": 60.0,
            "price_momentum": 70.0,
            "news_sentiment": 50.0,
            "globalization_strength": 90.0,
        }
    )

    assert total == 69.0


def test_select_long_and_short_picks_extremes() -> None:
    stocks = [
        RankedStock("catl", "CATL", FactorScores(90, 75, 60, 55, 80), 76.25),
        RankedStock("byd", "BYD", FactorScores(85, 72, 75, 65, 78), 76.95),
        RankedStock("jerry-group", "Jerry Group", FactorScores(30, 20, 25, 40, 35), 29.0),
    ]

    long_candidate, short_candidate = select_long_and_short(stocks)

    assert long_candidate.slug == "byd"
    assert short_candidate.slug == "jerry-group"


def test_raw_sentiment_treats_null_scores_as_zero() -> None:
    artifact = AIArtifact(structured_payload={"score": None})

    assert ScoringService._raw_sentiment(artifact) == 0.0
