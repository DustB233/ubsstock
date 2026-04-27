import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from china_outbound_analyzer.core.config import get_settings
from china_outbound_analyzer.core.database import DatabaseUnavailableError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = None
    settings_error: str | None = None
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - depends on deployed environment
        settings_error = exc.__class__.__name__
        logger.exception("Runtime settings failed to load; starting health-only API shell.")

    app = FastAPI(
        title="China Outbound Stock AI Analyzer API",
        description=(
            "Explainable long/short stock analysis API for a fixed universe of 15 "
            "Chinese outbound-related companies."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings_error = settings_error
    app.state.router_import_error = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins
        if settings is not None
        else ["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = settings.api_v1_prefix if settings is not None else "/api/v1"

    @app.get("/", include_in_schema=False)
    async def root(request: Request) -> dict[str, Any]:
        return _runtime_status(request)

    @app.get(f"{api_prefix}/health", tags=["health"])
    async def healthcheck(request: Request) -> dict[str, Any]:
        return _runtime_status(request)

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(
        request: Request,
        exc: DatabaseUnavailableError,
    ) -> JSONResponse:
        logger.warning("Database unavailable for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Database is unavailable or misconfigured.",
                "type": "database_unavailable",
                "path": request.url.path,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database operation failed for %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Database operation failed.",
                "type": "database_operation_failed",
                "path": request.url.path,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error for %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error.",
                "type": "internal_server_error",
                "path": request.url.path,
            },
        )

    try:
        from china_outbound_analyzer.api.router import api_router

        app.include_router(api_router, prefix=api_prefix)
    except Exception as exc:  # pragma: no cover - protects deployed cold starts
        app.state.router_import_error = exc.__class__.__name__
        logger.exception("API router failed to load; root and health routes remain available.")

        @app.api_route(
            f"{api_prefix}/{{path:path}}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )
        async def api_unavailable(path: str) -> JSONResponse:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "API router failed to load.",
                    "type": "api_router_unavailable",
                    "path": f"{api_prefix}/{path}",
                },
            )

    return app


def _runtime_status(request: Request) -> dict[str, Any]:
    settings_error = getattr(request.app.state, "settings_error", None)
    router_import_error = getattr(request.app.state, "router_import_error", None)
    database_configured = bool(os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL"))
    return {
        "status": "ok" if not settings_error and not router_import_error else "degraded",
        "service": "China Outbound Stock AI Analyzer API",
        "version": request.app.version,
        "environment": os.getenv("APP_ENV", "development"),
        "database_configured": database_configured,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "cron_secret_configured": bool(os.getenv("CRON_SECRET")),
        "settings_loaded": settings_error is None,
        "router_loaded": router_import_error is None,
        "settings_error": settings_error,
        "router_import_error": router_import_error,
    }


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("china_outbound_analyzer.main:app", host="0.0.0.0", port=8000, reload=True)
