from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringWeights:
    fundamentals_quality: float = 0.25
    valuation_attractiveness: float = 0.25
    price_momentum: float = 0.15
    news_sentiment: float = 0.20
    globalization_strength: float = 0.15


DEFAULT_SCORING_WEIGHTS = ScoringWeights()
