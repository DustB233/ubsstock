"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-13 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _named_enum(*values: str, name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


identifier_type = _named_enum("A_SHARE", "H_SHARE", "US_LISTING", name="identifier_type")
data_source_kind = _named_enum(
    "MARKET_DATA", "FUNDAMENTALS", "NEWS", "ANNOUNCEMENTS", "AI", name="data_source_kind"
)
job_status = _named_enum("PENDING", "RUNNING", "SUCCESS", "FAILED", "PARTIAL", name="job_status")
refresh_job_type = _named_enum(
    "DAILY_REFRESH",
    "MARKET_DATA_REFRESH",
    "FUNDAMENTALS_REFRESH",
    "NEWS_REFRESH",
    "AI_REFRESH",
    "SCORING_REFRESH",
    name="refresh_job_type",
)
price_interval = _named_enum("1d", name="price_interval")
financial_period_type = _named_enum(
    "ANNUAL",
    "QUARTERLY",
    "TRAILING_TWELVE_MONTHS",
    name="financial_period_type",
)
ai_artifact_type = _named_enum(
    "NEWS_CLUSTER",
    "SENTIMENT_SUMMARY",
    "KEYWORD_EXTRACTION",
    "VALUATION_SUMMARY",
    "THESIS_SUMMARY",
    "FINAL_RECOMMENDATION",
    name="ai_artifact_type",
)
recommendation_side = _named_enum("LONG", "SHORT", name="recommendation_side")

NAMED_ENUMS = (
    identifier_type,
    data_source_kind,
    job_status,
    refresh_job_type,
    price_interval,
    financial_period_type,
    ai_artifact_type,
    recommendation_side,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    bind = op.get_bind()
    for enum_type in NAMED_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "stocks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("company_name_zh", sa.String(length=255), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=False),
        sa.Column("outbound_theme", sa.Text(), nullable=False),
        sa.Column("primary_exchange", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_stocks_slug", "stocks", ["slug"], unique=True)

    op.create_table(
        "data_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("kind", data_source_kind, nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_key", name="uq_data_sources_source_key"),
    )

    op.create_table(
        "refresh_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_type", refresh_job_type, nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "trigger_source",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("stage_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "stock_identifiers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identifier_type", identifier_type, nullable=False),
        sa.Column("exchange_code", sa.String(length=32), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("composite_symbol", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("composite_symbol", name="uq_stock_identifiers_composite_symbol"),
    )
    op.create_index(
        "ix_stock_identifiers_stock_id", "stock_identifiers", ["stock_id"], unique=False
    )

    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "refresh_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dataset_name", sa.String(length=64), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_read", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_ingestion_runs_refresh_job_id", "ingestion_runs", ["refresh_job_id"], unique=False
    )

    op.create_table(
        "price_bars",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "identifier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_identifiers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("interval", price_interval, nullable=False, server_default=sa.text("'1d'")),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=True),
        sa.Column("high", sa.Numeric(18, 6), nullable=True),
        sa.Column("low", sa.Numeric(18, 6), nullable=True),
        sa.Column("close", sa.Numeric(18, 6), nullable=True),
        sa.Column("adjusted_close", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("turnover", sa.Numeric(24, 4), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "identifier_id", "source_id", "interval", "trading_date", name="uq_price_bars_snapshot"
        ),
    )
    op.create_index("ix_price_bars_identifier_id", "price_bars", ["identifier_id"], unique=False)
    op.create_index("ix_price_bars_trading_date", "price_bars", ["trading_date"], unique=False)

    op.create_table(
        "valuation_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("market_cap", sa.Numeric(24, 4), nullable=True),
        sa.Column("pe_ttm", sa.Numeric(18, 6), nullable=True),
        sa.Column("pe_forward", sa.Numeric(18, 6), nullable=True),
        sa.Column("pb", sa.Numeric(18, 6), nullable=True),
        sa.Column("ps_ttm", sa.Numeric(18, 6), nullable=True),
        sa.Column("ev_ebitda", sa.Numeric(18, 6), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(10, 6), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "stock_id", "source_id", "as_of_date", name="uq_valuation_snapshots_asof"
        ),
    )
    op.create_index(
        "ix_valuation_snapshots_stock_id", "valuation_snapshots", ["stock_id"], unique=False
    )
    op.create_index(
        "ix_valuation_snapshots_as_of_date", "valuation_snapshots", ["as_of_date"], unique=False
    )

    op.create_table(
        "financial_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period_type", financial_period_type, nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("revenue", sa.Numeric(24, 4), nullable=True),
        sa.Column("net_profit", sa.Numeric(24, 4), nullable=True),
        sa.Column("gross_margin", sa.Numeric(10, 6), nullable=True),
        sa.Column("roe", sa.Numeric(10, 6), nullable=True),
        sa.Column("revenue_growth_yoy", sa.Numeric(10, 6), nullable=True),
        sa.Column("net_profit_growth_yoy", sa.Numeric(10, 6), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "stock_id",
            "source_id",
            "period_type",
            "fiscal_year",
            "fiscal_period",
            name="uq_financial_metrics_period",
        ),
    )
    op.create_index(
        "ix_financial_metrics_stock_id", "financial_metrics", ["stock_id"], unique=False
    )

    op.create_table(
        "news_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False, server_default=sa.text("'zh'")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_news_items_external"),
    )
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"], unique=False)

    op.create_table(
        "stock_news_mentions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "news_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("stock_id", "news_item_id", name="uq_stock_news_mentions_pair"),
    )
    op.create_index(
        "ix_stock_news_mentions_stock_id", "stock_news_mentions", ["stock_id"], unique=False
    )
    op.create_index(
        "ix_stock_news_mentions_news_item_id", "stock_news_mentions", ["news_item_id"], unique=False
    )

    op.create_table(
        "announcements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "stock_id", "source_id", "external_id", name="uq_announcements_external"
        ),
    )
    op.create_index("ix_announcements_stock_id", "announcements", ["stock_id"], unique=False)
    op.create_index(
        "ix_announcements_published_at", "announcements", ["published_at"], unique=False
    )

    op.create_table(
        "news_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cluster_label", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("sentiment_label", sa.String(length=32), nullable=True),
        sa.Column("keyword_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_news_clusters_stock_id", "news_clusters", ["stock_id"], unique=False)

    op.create_table(
        "news_cluster_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("news_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "news_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_representative", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("cluster_id", "news_item_id", name="uq_news_cluster_items_pair"),
    )

    op.create_table(
        "ai_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "refresh_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("artifact_type", ai_artifact_type, nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("status", job_status, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("structured_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_ai_artifacts_stock_id", "ai_artifacts", ["stock_id"], unique=False)
    op.create_index(
        "ix_ai_artifacts_refresh_job_id", "ai_artifacts", ["refresh_job_id"], unique=False
    )

    op.create_table(
        "scoring_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "refresh_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("weights_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_scoring_runs_refresh_job_id", "scoring_runs", ["refresh_job_id"], unique=False
    )
    op.create_index("ix_scoring_runs_run_date", "scoring_runs", ["run_date"], unique=False)

    op.create_table(
        "stock_scores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scoring_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scoring_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fundamentals_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("valuation_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("momentum_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("globalization_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("total_score", sa.Numeric(10, 6), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("scoring_run_id", "stock_id", name="uq_stock_scores_run_stock"),
    )
    op.create_index(
        "ix_stock_scores_scoring_run_id", "stock_scores", ["scoring_run_id"], unique=False
    )
    op.create_index("ix_stock_scores_stock_id", "stock_scores", ["stock_id"], unique=False)

    op.create_table(
        "recommendation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scoring_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scoring_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", job_status, nullable=False),
        sa.Column("explanation_markdown", sa.Text(), nullable=True),
        sa.Column("trace_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("scoring_run_id", name="uq_recommendation_runs_scoring_run"),
    )

    op.create_table(
        "recommendation_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "recommendation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", recommendation_side, nullable=False),
        sa.Column("confidence_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("rationale_markdown", sa.Text(), nullable=False),
        sa.Column("bull_case", sa.Text(), nullable=True),
        sa.Column("bear_case", sa.Text(), nullable=True),
        sa.Column("key_risks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("supporting_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("recommendation_run_id", "side", name="uq_recommendation_items_side"),
    )
    op.create_index(
        "ix_recommendation_items_recommendation_run_id",
        "recommendation_items",
        ["recommendation_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_items_recommendation_run_id", table_name="recommendation_items"
    )
    op.drop_table("recommendation_items")
    op.drop_table("recommendation_runs")
    op.drop_index("ix_stock_scores_stock_id", table_name="stock_scores")
    op.drop_index("ix_stock_scores_scoring_run_id", table_name="stock_scores")
    op.drop_table("stock_scores")
    op.drop_index("ix_scoring_runs_run_date", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_refresh_job_id", table_name="scoring_runs")
    op.drop_table("scoring_runs")
    op.drop_index("ix_ai_artifacts_refresh_job_id", table_name="ai_artifacts")
    op.drop_index("ix_ai_artifacts_stock_id", table_name="ai_artifacts")
    op.drop_table("ai_artifacts")
    op.drop_table("news_cluster_items")
    op.drop_index("ix_news_clusters_stock_id", table_name="news_clusters")
    op.drop_table("news_clusters")
    op.drop_index("ix_announcements_published_at", table_name="announcements")
    op.drop_index("ix_announcements_stock_id", table_name="announcements")
    op.drop_table("announcements")
    op.drop_index("ix_stock_news_mentions_news_item_id", table_name="stock_news_mentions")
    op.drop_index("ix_stock_news_mentions_stock_id", table_name="stock_news_mentions")
    op.drop_table("stock_news_mentions")
    op.drop_index("ix_news_items_published_at", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_financial_metrics_stock_id", table_name="financial_metrics")
    op.drop_table("financial_metrics")
    op.drop_index("ix_valuation_snapshots_as_of_date", table_name="valuation_snapshots")
    op.drop_index("ix_valuation_snapshots_stock_id", table_name="valuation_snapshots")
    op.drop_table("valuation_snapshots")
    op.drop_index("ix_price_bars_trading_date", table_name="price_bars")
    op.drop_index("ix_price_bars_identifier_id", table_name="price_bars")
    op.drop_table("price_bars")
    op.drop_index("ix_ingestion_runs_refresh_job_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index("ix_stock_identifiers_stock_id", table_name="stock_identifiers")
    op.drop_table("stock_identifiers")
    op.drop_table("refresh_jobs")
    op.drop_table("data_sources")
    op.drop_index("ix_stocks_slug", table_name="stocks")
    op.drop_table("stocks")

    bind = op.get_bind()
    for enum_type in reversed(NAMED_ENUMS):
        enum_type.drop(bind, checkfirst=True)
