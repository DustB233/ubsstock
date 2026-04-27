from pydantic import BaseModel


class ComparisonMetricDefinition(BaseModel):
    key: str
    label: str
    category: str


class ComparisonRow(BaseModel):
    slug: str
    company_name: str
    metrics: dict[str, float | str | None]


class ComparisonResponse(BaseModel):
    requested_slugs: list[str]
    metrics: list[ComparisonMetricDefinition]
    rows: list[ComparisonRow]
