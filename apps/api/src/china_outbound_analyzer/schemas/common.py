from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PricePoint(APIModel):
    trading_date: date
    close: float | None = None
    volume: int | None = None


class MetricValue(APIModel):
    key: str
    label: str
    value: Decimal | str | None
    unit: str | None = None


class SourceLink(APIModel):
    title: str
    url: str
    published_at: datetime | None = None


class EmptyState(APIModel):
    message: str = Field(default="Data is not available yet for this section.")
