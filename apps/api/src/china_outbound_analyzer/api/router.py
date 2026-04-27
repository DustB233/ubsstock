from fastapi import APIRouter

from china_outbound_analyzer.api.v1.endpoints import (
    admin,
    compare,
    cron,
    dashboard,
    health,
    jobs,
    metadata,
    recommendations,
    stocks,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(metadata.router)
api_router.include_router(admin.router)
api_router.include_router(cron.router)
api_router.include_router(stocks.router)
api_router.include_router(compare.router)
api_router.include_router(recommendations.router)
api_router.include_router(jobs.router)
