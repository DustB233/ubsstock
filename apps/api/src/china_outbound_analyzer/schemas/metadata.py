from pydantic import BaseModel, Field


class AIMethodologySectionResponse(BaseModel):
    title: str
    body: str
    bullets: list[str] = Field(default_factory=list)
    tone: str


class AIMethodologyResponse(BaseModel):
    schema_version: str
    headline: str
    sections: list[AIMethodologySectionResponse]
