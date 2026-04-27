from enum import StrEnum


class IdentifierType(StrEnum):
    A_SHARE = "A_SHARE"
    H_SHARE = "H_SHARE"
    US_LISTING = "US_LISTING"


class DataSourceKind(StrEnum):
    MARKET_DATA = "MARKET_DATA"
    FUNDAMENTALS = "FUNDAMENTALS"
    NEWS = "NEWS"
    ANNOUNCEMENTS = "ANNOUNCEMENTS"
    AI = "AI"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class RefreshJobType(StrEnum):
    DAILY_REFRESH = "DAILY_REFRESH"
    MARKET_DATA_REFRESH = "MARKET_DATA_REFRESH"
    FUNDAMENTALS_REFRESH = "FUNDAMENTALS_REFRESH"
    NEWS_REFRESH = "NEWS_REFRESH"
    ANNOUNCEMENTS_REFRESH = "ANNOUNCEMENTS_REFRESH"
    AI_REFRESH = "AI_REFRESH"
    SCORING_REFRESH = "SCORING_REFRESH"


class PriceInterval(StrEnum):
    DAY_1 = "1d"


def enum_db_values[EnumValue: StrEnum](enum_cls: type[EnumValue]) -> list[str]:
    return [member.value for member in enum_cls]


def coerce_price_interval(value: PriceInterval | str | None) -> PriceInterval:
    if value is None:
        return PriceInterval.DAY_1
    if isinstance(value, PriceInterval):
        return value

    normalized = value.strip()
    for interval in PriceInterval:
        if normalized == interval.value or normalized.upper() == interval.name:
            return interval

    raise ValueError(f"Unsupported price interval: {value}")


class FinancialPeriodType(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    TRAILING_TWELVE_MONTHS = "TRAILING_TWELVE_MONTHS"


class AIArtifactType(StrEnum):
    NEWS_CLUSTER = "NEWS_CLUSTER"
    SENTIMENT_SUMMARY = "SENTIMENT_SUMMARY"
    KEYWORD_EXTRACTION = "KEYWORD_EXTRACTION"
    VALUATION_SUMMARY = "VALUATION_SUMMARY"
    THESIS_SUMMARY = "THESIS_SUMMARY"
    FINAL_RECOMMENDATION = "FINAL_RECOMMENDATION"


class RecommendationSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
