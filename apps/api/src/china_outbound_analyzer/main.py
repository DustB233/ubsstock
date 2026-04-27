from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from china_outbound_analyzer.api.router import api_router
from china_outbound_analyzer.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="China Outbound Stock AI Analyzer API",
        description=(
            "Explainable long/short stock analysis API for a fixed universe of 15 "
            "Chinese outbound-related companies."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"message": "China Outbound Stock AI Analyzer API"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("china_outbound_analyzer.main:app", host="0.0.0.0", port=8000, reload=True)
