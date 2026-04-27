import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.schemas.stock_views import (
    StockAnalysisResponse,
    StockDetailViewResponse,
    StockListViewResponse,
    StockNewsFeedResponse,
    StockTimeseriesResponse,
)
from china_outbound_analyzer.services.market.read_models import DatabaseMarketReadService

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _list_stocks() -> list[StockListViewResponse]:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).list_stocks()


def _load_stock_detail(symbol: str) -> StockDetailViewResponse | None:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).get_stock_detail(symbol)


def _load_stock_timeseries(symbol: str, range_key: str) -> StockTimeseriesResponse | None:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).get_timeseries(symbol, range_key)


def _load_stock_news(symbol: str) -> StockNewsFeedResponse | None:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).get_news(symbol)


def _load_stock_analysis(symbol: str) -> StockAnalysisResponse | None:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).get_analysis(symbol)


@router.get("", response_model=list[StockListViewResponse])
async def list_stocks() -> list[StockListViewResponse]:
    return await asyncio.to_thread(_list_stocks)


@router.get("/{symbol}/timeseries", response_model=StockTimeseriesResponse)
async def get_stock_timeseries(
    symbol: str,
    range_key: Annotated[Literal["1m", "3m", "6m", "1y"], Query(alias="range")] = "1y",
) -> StockTimeseriesResponse:
    response = await asyncio.to_thread(_load_stock_timeseries, symbol, range_key)
    if response is None:
        raise HTTPException(status_code=404, detail="Stock not found.")
    return response


@router.get("/{symbol}/news", response_model=StockNewsFeedResponse)
async def get_stock_news(symbol: str) -> StockNewsFeedResponse:
    response = await asyncio.to_thread(_load_stock_news, symbol)
    if response is None:
        raise HTTPException(status_code=404, detail="Stock not found.")
    return response


@router.get("/{symbol}/analysis", response_model=StockAnalysisResponse)
async def get_stock_analysis(symbol: str) -> StockAnalysisResponse:
    response = await asyncio.to_thread(_load_stock_analysis, symbol)
    if response is None:
        raise HTTPException(status_code=404, detail="Stock not found.")
    return response


@router.get("/{symbol}", response_model=StockDetailViewResponse)
async def get_stock_detail(symbol: str) -> StockDetailViewResponse:
    response = await asyncio.to_thread(_load_stock_detail, symbol)
    if response is None:
        raise HTTPException(status_code=404, detail="Stock not found.")
    return response
