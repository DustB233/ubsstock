import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.enums import (
    AIArtifactType,
    DataSourceKind,
    FinancialPeriodType,
    IdentifierType,
    JobStatus,
    PriceInterval,
    RecommendationSide,
    RefreshJobType,
    enum_db_values,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Stock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stocks"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name_zh: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str] = mapped_column(String(128), nullable=False)
    outbound_theme: Mapped[str] = mapped_column(Text, nullable=False)
    primary_exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StockIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_identifiers"

    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier_type: Mapped[IdentifierType] = mapped_column(
        Enum(IdentifierType, name="identifier_type"), nullable=False
    )
    exchange_code: Mapped[str] = mapped_column(String(32), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    composite_symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    source_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[DataSourceKind] = mapped_column(
        Enum(DataSourceKind, name="data_source_kind"), nullable=False
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class RefreshJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_jobs"

    job_name: Mapped[str] = mapped_column(String(64), nullable=False, default="manual-job")
    job_type: Mapped[RefreshJobType] = mapped_column(
        Enum(RefreshJobType, name="refresh_job_type"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    stage_status: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)


class IngestionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_runs"

    refresh_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_jobs.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)


class PriceBar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_bars"

    identifier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_identifiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    interval: Mapped[PriceInterval] = mapped_column(
        Enum(
            PriceInterval,
            name="price_interval",
            values_callable=enum_db_values,
            validate_strings=True,
        ),
        nullable=False,
        default=PriceInterval.DAY_1,
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[int | None] = mapped_column()
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ValuationSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "valuation_snapshots"
    __table_args__ = (
        UniqueConstraint("stock_id", "source_id", "as_of_date", name="uq_valuation_snapshots_asof"),
    )

    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str | None] = mapped_column(String(8))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    pe_ttm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pe_forward: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ps_ttm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    enterprise_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    ev_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class FinancialMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_metrics"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "source_id",
            "period_type",
            "fiscal_year",
            "fiscal_period",
            name="uq_financial_metrics_period",
        ),
    )

    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    period_type: Mapped[FinancialPeriodType] = mapped_column(
        Enum(FinancialPeriodType, name="financial_period_type"), nullable=False
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    net_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    roa: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    overseas_revenue_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    revenue_growth_yoy: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    net_profit_growth_yoy: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class NewsItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_news_items_external"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="zh", nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class StockNewsMention(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_news_mentions"
    __table_args__ = (
        UniqueConstraint("stock_id", "news_item_id", name="uq_stock_news_mentions_pair"),
    )

    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    news_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))


class Announcement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("stock_id", "source_id", "external_id", name="uq_announcements_external"),
    )

    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128))
    exchange_code: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    as_of_date: Mapped[date | None] = mapped_column(Date, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class NewsCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_clusters"

    stock_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="SET NULL"), index=True
    )
    cluster_label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    sentiment_label: Mapped[str | None] = mapped_column(String(32))
    keyword_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NewsClusterItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_cluster_items"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    news_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    is_representative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_artifacts"

    stock_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="SET NULL"), index=True
    )
    refresh_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_jobs.id", ondelete="SET NULL"), index=True
    )
    artifact_type: Mapped[AIArtifactType] = mapped_column(
        Enum(AIArtifactType, name="ai_artifact_type"), nullable=False
    )
    model_provider: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_markdown: Mapped[str | None] = mapped_column(Text)
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_links: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trace_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)


class ScoringRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scoring_runs"

    refresh_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_jobs.id", ondelete="SET NULL"), index=True
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class StockScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_scores"

    scoring_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fundamentals_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    valuation_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    momentum_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    sentiment_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    globalization_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class RecommendationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_runs"

    scoring_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False)
    explanation_markdown: Mapped[str | None] = mapped_column(Text)
    trace_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class RecommendationItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_items"

    recommendation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[RecommendationSide] = mapped_column(
        Enum(RecommendationSide, name="recommendation_side"), nullable=False
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rationale_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    bull_case: Mapped[str | None] = mapped_column(Text)
    bear_case: Mapped[str | None] = mapped_column(Text)
    key_risks: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    supporting_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_links: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
