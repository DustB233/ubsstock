from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import Announcement, DataSource, Stock, StockIdentifier
from china_outbound_analyzer.models.enums import DataSourceKind, IdentifierType
from china_outbound_analyzer.services.adapters.base import AnnouncementAdapter, AnnouncementRecord
from china_outbound_analyzer.services.ingestion.announcements_refresh import (
    CNINFO_ANNOUNCEMENTS_SOURCE_KEY,
    MOCK_ANNOUNCEMENTS_SOURCE_KEY,
    AnnouncementRefreshService,
)
from china_outbound_analyzer.services.ingestion.cninfo_announcements_adapter import (
    CNINFO_QUERY_URL,
    CninfoAnnouncementAdapter,
    deduplicate_announcement_records,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


class StubAnnouncementAdapter(AnnouncementAdapter):
    async def fetch_announcements(
        self,
        symbol: str,
        limit: int = 20,
        lookback_days: int | None = None,
    ) -> list[AnnouncementRecord]:
        if symbol == "300750.SZ":
            published = datetime(2026, 4, 14, 2, 15, tzinfo=UTC)
            return [
                AnnouncementRecord(
                    symbol=symbol,
                    title="宁德时代:关于投资设立全资子公司的公告",
                    url="https://static.cninfo.com.cn/finalpage/2026-04-14/1224899411.PDF",
                    published_at=published,
                    category=None,
                    summary=None,
                    external_id="cninfo:1224899411",
                    provider="CNInfo Disclosures",
                    exchange="SZSE",
                    language="zh",
                    as_of_date=date(2026, 4, 14),
                    source_url="https://www.cninfo.com.cn/new/disclosure/detail?stockCode=300750&announcementId=1224899411",
                    raw_payload={"source_name": "CNInfo Disclosures"},
                )
            ]
        if symbol == "3750.HK":
            published = datetime(2026, 4, 14, 2, 10, tzinfo=UTC)
            return [
                AnnouncementRecord(
                    symbol=symbol,
                    title="关于投资设立全资子公司的公告",
                    url="https://static.cninfo.com.cn/finalpage/2026-04-14/1224899555.PDF",
                    published_at=published,
                    category=None,
                    summary=None,
                    external_id="cninfo:1224899555",
                    provider="CNInfo Disclosures",
                    exchange="HKEX",
                    language="zh",
                    as_of_date=date(2026, 4, 14),
                    source_url="https://www.cninfo.com.cn/new/disclosure/detail?stockCode=03750&announcementId=1224899555",
                    raw_payload={"source_name": "CNInfo Disclosures"},
                ),
                AnnouncementRecord(
                    symbol=symbol,
                    title="临时股东会投票表决结果",
                    url="https://static.cninfo.com.cn/finalpage/2026-04-14/1224899556.PDF",
                    published_at=datetime(2026, 4, 13, 21, 0, tzinfo=UTC),
                    category=None,
                    summary=None,
                    external_id="cninfo:1224899556",
                    provider="CNInfo Disclosures",
                    exchange="HKEX",
                    language="zh",
                    as_of_date=date(2026, 4, 14),
                    source_url="https://www.cninfo.com.cn/new/disclosure/detail?stockCode=03750&announcementId=1224899556",
                    raw_payload={"source_name": "CNInfo Disclosures"},
                ),
            ]
        if symbol == "1211.HK":
            return [
                AnnouncementRecord(
                    symbol=symbol,
                    title="临时股东会投票表决结果",
                    url="https://static.cninfo.com.cn/finalpage/2026-04-13/1224856392.PDF",
                    published_at=datetime(2026, 4, 13, 12, 30, tzinfo=UTC),
                    category=None,
                    summary=None,
                    external_id="cninfo:1224856392",
                    provider="CNInfo Disclosures",
                    exchange="HKEX",
                    language="zh",
                    as_of_date=date(2026, 4, 13),
                    source_url="https://www.cninfo.com.cn/new/disclosure/detail?stockCode=01211&announcementId=1224856392",
                    raw_payload={"source_name": "CNInfo Disclosures"},
                )
            ]
        return []


class FailingAnnouncementAdapter(AnnouncementAdapter):
    def __init__(self, failing_symbol: str) -> None:
        self.failing_symbol = failing_symbol

    async def fetch_announcements(
        self,
        symbol: str,
        limit: int = 20,
        lookback_days: int | None = None,
    ) -> list[AnnouncementRecord]:
        if symbol == self.failing_symbol:
            raise RuntimeError("primary provider failure")
        return await StubAnnouncementAdapter().fetch_announcements(
            symbol,
            limit=limit,
            lookback_days=lookback_days,
        )


class SymbolFailingAnnouncementRefreshService(AnnouncementRefreshService):
    def __init__(self, *args, failing_stock_slug: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.failing_stock_slug = failing_stock_slug

    def _ingest_announcements(
        self,
        *,
        stock_id,
        stock_slug: str,
        fetched,
        source_ids,
        ingestion_runs,
    ) -> int:
        rows_written = super()._ingest_announcements(
            stock_id=stock_id,
            stock_slug=stock_slug,
            fetched=fetched,
            source_ids=source_ids,
            ingestion_runs=ingestion_runs,
        )
        if stock_slug == self.failing_stock_slug:
            raise RuntimeError("intentional symbol failure")
        return rows_written


def _build_test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)()


def _seed_announcement_universe(session: Session, symbols: list[list[str]]) -> None:
    session.add_all(
        [
            DataSource(
                source_key=CNINFO_ANNOUNCEMENTS_SOURCE_KEY,
                display_name="CNInfo Disclosures",
                kind=DataSourceKind.ANNOUNCEMENTS,
                is_mock=False,
                base_url="https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            ),
            DataSource(
                source_key=MOCK_ANNOUNCEMENTS_SOURCE_KEY,
                display_name="Mock Announcements",
                kind=DataSourceKind.ANNOUNCEMENTS,
                is_mock=True,
                base_url="https://demo.local/announcements",
            ),
        ]
    )
    session.flush()

    for index, identifier_symbols in enumerate(symbols):
        stock = Stock(
            slug=f"stock-{index}",
            company_name=f"Stock {index}",
            company_name_zh=f"示例公司{index}",
            sector="Industrial",
            outbound_theme="Test universe for announcement refresh coverage.",
            primary_exchange="SZSE",
            is_active=True,
        )
        session.add(stock)
        session.flush()

        for identifier_index, symbol in enumerate(identifier_symbols):
            is_hk = symbol.endswith(".HK")
            session.add(
                StockIdentifier(
                    stock_id=stock.id,
                    identifier_type=IdentifierType.H_SHARE if is_hk else IdentifierType.A_SHARE,
                    exchange_code="HKEX" if is_hk else ("SSE" if symbol.endswith(".SH") else "SZSE"),
                    ticker=symbol.split(".")[0],
                    composite_symbol=symbol,
                    currency="HKD" if is_hk else "CNY",
                    is_primary=identifier_index == 0,
                )
            )
        session.flush()


def _cninfo_transport(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path.endswith("/new/data/szse_stock.json"):
        return httpx.Response(
            200,
            json={
                "stockList": [
                    {"code": "300750", "orgId": "GD165627"},
                ]
            },
        )
    if request.method == "GET" and request.url.path.endswith("/new/data/hke_stock.json"):
        return httpx.Response(
            200,
            json={
                "stockList": [
                    {"code": "01810", "orgId": "9900037222"},
                ]
            },
        )
    if request.method == "POST" and str(request.url) == CNINFO_QUERY_URL:
        body = request.content.decode()
        if "stock=300750%2CGD165627" in body:
            return httpx.Response(
                200,
                json={
                    "announcements": [
                        {
                            "secCode": "300750",
                            "secName": "宁德时代",
                            "orgId": "GD165627",
                            "announcementId": "1224899411",
                            "announcementTitle": "关于投资设立全资子公司的公告",
                            "announcementTime": 1713262509000,
                            "adjunctUrl": "finalpage/2026-04-16/1224899411.PDF",
                            "announcementTypeName": None,
                            "announcementContent": "",
                        }
                    ],
                    "totalpages": 1,
                },
            )
        if "stock=01810%2C9900037222" in body:
            return httpx.Response(
                200,
                json={
                    "announcements": [
                        {
                            "secCode": "01810",
                            "secName": "小米集团-W",
                            "orgId": "9900037222",
                            "announcementId": "1224912857",
                            "announcementTitle": "翌日披露报表",
                            "announcementTime": 1713197771000,
                            "adjunctUrl": "finalpage/2026-04-15/1224912857.PDF",
                            "announcementTypeName": None,
                            "announcementContent": "",
                        }
                    ],
                    "totalpages": 1,
                },
            )
    return httpx.Response(404, json={"detail": "not found"})


@pytest.mark.asyncio
async def test_cninfo_adapter_normalizes_a_share_and_hk_announcements() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_cninfo_transport))
    adapter = CninfoAnnouncementAdapter(client=client)

    a_share_records = await adapter.fetch_announcements("300750.SZ", limit=5, lookback_days=365)
    hk_records = await adapter.fetch_announcements("1810.HK", limit=5, lookback_days=365)

    assert a_share_records[0].external_id == "cninfo:1224899411"
    assert a_share_records[0].provider == "CNInfo Disclosures"
    assert a_share_records[0].exchange == "SZSE"
    assert a_share_records[0].language == "zh"
    assert a_share_records[0].source_url
    assert a_share_records[0].url.startswith("https://static.cninfo.com.cn/")

    assert hk_records[0].external_id == "cninfo:1224912857"
    assert hk_records[0].exchange == "HKEX"
    assert hk_records[0].as_of_date is not None

    await adapter.aclose()


def test_announcement_deduplication_merges_near_duplicate_cross_listing_titles() -> None:
    published_at = datetime(2026, 4, 14, 2, 15, tzinfo=UTC)
    records = [
        AnnouncementRecord(
            symbol="300750.SZ",
            title="宁德时代:关于投资设立全资子公司的公告",
            url="https://example.com/a",
            published_at=published_at,
            external_id="cninfo:1",
            provider="CNInfo Disclosures",
            exchange="SZSE",
            language="zh",
            as_of_date=date(2026, 4, 14),
        ),
        AnnouncementRecord(
            symbol="3750.HK",
            title="关于投资设立全资子公司的公告",
            url="https://example.com/b",
            published_at=published_at,
            external_id="cninfo:2",
            provider="CNInfo Disclosures",
            exchange="HKEX",
            language="zh",
            as_of_date=date(2026, 4, 14),
        ),
        AnnouncementRecord(
            symbol="3750.HK",
            title="临时股东会投票表决结果",
            url="https://example.com/c",
            published_at=datetime(2026, 4, 13, 12, 30, tzinfo=UTC),
            external_id="cninfo:3",
            provider="CNInfo Disclosures",
            exchange="HKEX",
            language="zh",
            as_of_date=date(2026, 4, 13),
        ),
    ]

    deduped = deduplicate_announcement_records(records)

    assert len(deduped) == 2
    assert {item.external_id for item in deduped} == {"cninfo:1", "cninfo:3"}


@pytest.mark.asyncio
async def test_announcements_refresh_service_persists_deduplicated_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_test_session()
    _seed_announcement_universe(session, [["300750.SZ", "3750.HK"]])

    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.announcements_refresh.seed_universe",
        lambda _session: None,
    )

    service = AnnouncementRefreshService(
        session=session,
        settings=Settings(announcements_data_provider="cninfo"),
        primary_announcement_adapter=StubAnnouncementAdapter(),
        fallback_announcement_adapter=StubAnnouncementAdapter(),
        primary_source_key=CNINFO_ANNOUNCEMENTS_SOURCE_KEY,
        fallback_source_key=MOCK_ANNOUNCEMENTS_SOURCE_KEY,
    )

    result = await service.run(limit_per_symbol=10, lookback_days=365)
    rows = session.query(Announcement).order_by(Announcement.published_at.desc()).all()

    assert result["status"] == "SUCCESS"
    assert result["announcements"] == 2
    assert len(rows) == 2
    assert rows[0].provider == "CNInfo Disclosures"
    assert rows[0].language == "zh"
    assert rows[0].exchange_code in {"SZSE", "HKEX"}
    assert rows[0].raw_payload["stock_slug"] == "stock-0"


@pytest.mark.asyncio
async def test_announcements_refresh_service_continues_after_symbol_level_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_test_session()
    _seed_announcement_universe(session, [["300750.SZ"], ["1211.HK"]])

    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.announcements_refresh.seed_universe",
        lambda _session: None,
    )

    service = SymbolFailingAnnouncementRefreshService(
        session=session,
        settings=Settings(announcements_data_provider="cninfo"),
        primary_announcement_adapter=StubAnnouncementAdapter(),
        fallback_announcement_adapter=StubAnnouncementAdapter(),
        primary_source_key=CNINFO_ANNOUNCEMENTS_SOURCE_KEY,
        fallback_source_key=MOCK_ANNOUNCEMENTS_SOURCE_KEY,
        failing_stock_slug="stock-0",
    )

    result = await service.run(limit_per_symbol=5, lookback_days=365)
    rows = session.query(Announcement).all()

    assert result["status"] == "PARTIAL"
    assert result["failed_symbols"] == 1
    assert len(rows) == 1
