from dataclasses import dataclass


@dataclass(frozen=True)
class ExplainableArtifact:
    artifact_type: str
    summary: str
    source_links: list[str]
    trace_references: list[str]


class AIAnalysisPipeline:
    async def cluster_news(self, slug: str) -> ExplainableArtifact:
        raise NotImplementedError

    async def summarize_valuation(self, slug: str) -> ExplainableArtifact:
        raise NotImplementedError

    async def generate_final_thesis(self, slug: str) -> ExplainableArtifact:
        raise NotImplementedError
