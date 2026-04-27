from dataclasses import dataclass


@dataclass(frozen=True)
class IdentifierSeed:
    composite_symbol: str
    exchange_code: str
    identifier_type: str
    currency: str
    is_primary: bool = False


@dataclass(frozen=True)
class StockUniverseSeed:
    slug: str
    company_name: str
    company_name_zh: str
    sector: str
    outbound_theme: str
    primary_exchange: str
    identifiers: tuple[IdentifierSeed, ...]


UNIVERSE: tuple[StockUniverseSeed, ...] = (
    StockUniverseSeed(
        slug="catl",
        company_name="CATL",
        company_name_zh="宁德时代",
        sector="Battery Systems",
        outbound_theme="Global EV battery leadership and cross-border manufacturing expansion.",
        primary_exchange="SZSE",
        identifiers=(
            IdentifierSeed("300750.SZ", "SZSE", "A_SHARE", "CNY", True),
            IdentifierSeed("3750.HK", "HKEX", "H_SHARE", "HKD"),
        ),
    ),
    StockUniverseSeed(
        slug="byd",
        company_name="BYD",
        company_name_zh="比亚迪",
        sector="EV + Energy Storage",
        outbound_theme="China auto export scale, overseas assembly, and battery ecosystem reach.",
        primary_exchange="HKEX",
        identifiers=(
            IdentifierSeed("002594.SZ", "SZSE", "A_SHARE", "CNY"),
            IdentifierSeed("1211.HK", "HKEX", "H_SHARE", "HKD", True),
        ),
    ),
    StockUniverseSeed(
        slug="sany-heavy",
        company_name="Sany Heavy",
        company_name_zh="三一重工",
        sector="Construction Machinery",
        outbound_theme="Infrastructure equipment exports and global dealer network strength.",
        primary_exchange="SSE",
        identifiers=(
            IdentifierSeed("600031.SH", "SSE", "A_SHARE", "CNY", True),
            IdentifierSeed("6031.HK", "HKEX", "H_SHARE", "HKD"),
        ),
    ),
    StockUniverseSeed(
        slug="roborock",
        company_name="Roborock",
        company_name_zh="石头科技",
        sector="Smart Home Hardware",
        outbound_theme="Premium robotics brand with growing international channel penetration.",
        primary_exchange="SSE",
        identifiers=(IdentifierSeed("688169.SH", "SSE", "A_SHARE", "CNY", True),),
    ),
    StockUniverseSeed(
        slug="pop-mart",
        company_name="Pop Mart",
        company_name_zh="泡泡玛特",
        sector="IP Consumer Brands",
        outbound_theme="Global fan IP monetization and overseas store expansion.",
        primary_exchange="HKEX",
        identifiers=(IdentifierSeed("9992.HK", "HKEX", "H_SHARE", "HKD", True),),
    ),
    StockUniverseSeed(
        slug="miniso",
        company_name="Miniso",
        company_name_zh="名创优品",
        sector="Consumer Retail",
        outbound_theme="Asset-light global retail franchising and product localization.",
        primary_exchange="HKEX",
        identifiers=(
            IdentifierSeed("9896.HK", "HKEX", "H_SHARE", "HKD", True),
            IdentifierSeed("MNSO", "NYSE", "US_LISTING", "USD"),
        ),
    ),
    StockUniverseSeed(
        slug="xiaomi",
        company_name="Xiaomi",
        company_name_zh="小米集团",
        sector="Consumer Electronics",
        outbound_theme="International smartphone and IoT share gains with ecosystem optionality.",
        primary_exchange="HKEX",
        identifiers=(IdentifierSeed("1810.HK", "HKEX", "H_SHARE", "HKD", True),),
    ),
    StockUniverseSeed(
        slug="zhongji-innolight",
        company_name="Zhongji Innolight",
        company_name_zh="中际旭创",
        sector="Optical Components",
        outbound_theme="Data-center optical export leverage tied to global AI capex.",
        primary_exchange="SZSE",
        identifiers=(IdentifierSeed("300308.SZ", "SZSE", "A_SHARE", "CNY", True),),
    ),
    StockUniverseSeed(
        slug="will-semiconductor",
        company_name="Will Semiconductor",
        company_name_zh="韦尔股份",
        sector="Image Sensors",
        outbound_theme="OmniVision sensor franchise exposed to international handset and automotive demand.",
        primary_exchange="SSE",
        identifiers=(IdentifierSeed("603501.SH", "SSE", "A_SHARE", "CNY", True),),
    ),
    StockUniverseSeed(
        slug="beigene",
        company_name="BeiGene",
        company_name_zh="百济神州",
        sector="Biopharma",
        outbound_theme="Global oncology commercialization and international clinical expansion.",
        primary_exchange="HKEX",
        identifiers=(
            IdentifierSeed("688235.SH", "SSE", "A_SHARE", "CNY"),
            IdentifierSeed("6160.HK", "HKEX", "H_SHARE", "HKD", True),
        ),
    ),
    StockUniverseSeed(
        slug="microport-robotics",
        company_name="MicroPort Robotics",
        company_name_zh="微创机器人",
        sector="Medical Devices",
        outbound_theme="Surgical robotics platform with overseas regulatory and commercial optionality.",
        primary_exchange="HKEX",
        identifiers=(IdentifierSeed("2252.HK", "HKEX", "H_SHARE", "HKD", True),),
    ),
    StockUniverseSeed(
        slug="aier-eye-hospital",
        company_name="Aier Eye Hospital",
        company_name_zh="爱尔眼科",
        sector="Healthcare Services",
        outbound_theme="Cross-border ophthalmology network and international hospital footprint.",
        primary_exchange="SZSE",
        identifiers=(IdentifierSeed("300015.SZ", "SZSE", "A_SHARE", "CNY", True),),
    ),
    StockUniverseSeed(
        slug="siyuan-electric",
        company_name="Siyuan Electric",
        company_name_zh="思源电气",
        sector="Grid Equipment",
        outbound_theme="International power equipment orders tied to global grid upgrades.",
        primary_exchange="SZSE",
        identifiers=(IdentifierSeed("002028.SZ", "SZSE", "A_SHARE", "CNY", True),),
    ),
    StockUniverseSeed(
        slug="dongfang-electric",
        company_name="Dongfang Electric",
        company_name_zh="东方电气",
        sector="Power Equipment",
        outbound_theme="Overseas turbine, nuclear, and energy engineering project exposure.",
        primary_exchange="SSE",
        identifiers=(
            IdentifierSeed("600875.SH", "SSE", "A_SHARE", "CNY", True),
            IdentifierSeed("1072.HK", "HKEX", "H_SHARE", "HKD"),
        ),
    ),
    StockUniverseSeed(
        slug="jerry-group",
        company_name="Jerry Group",
        company_name_zh="杰瑞股份",
        sector="Oilfield Services Equipment",
        outbound_theme="Overseas oilfield equipment and services revenue leveraged to global energy spending.",
        primary_exchange="SZSE",
        identifiers=(IdentifierSeed("002353.SZ", "SZSE", "A_SHARE", "CNY", True),),
    ),
)
