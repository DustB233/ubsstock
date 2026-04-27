from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from china_outbound_analyzer.models.entities import Stock


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_stocks(self) -> list[Stock]:
        result = await self.session.execute(select(Stock).order_by(Stock.company_name))
        return list(result.scalars())
