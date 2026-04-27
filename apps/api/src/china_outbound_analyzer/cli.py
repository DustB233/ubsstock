import argparse
import asyncio
import logging

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.services.ai.live_pipeline import LiveAIAnalysisService
from china_outbound_analyzer.services.ai.mock_pipeline import MockAIAnalysisService
from china_outbound_analyzer.services.ingestion.announcements_refresh import (
    AnnouncementRefreshService,
)
from china_outbound_analyzer.services.ingestion.fundamentals_refresh import (
    FundamentalsRefreshService,
)
from china_outbound_analyzer.services.ingestion.mock_refresh import MockRefreshService
from china_outbound_analyzer.services.ingestion.news_refresh import NewsRefreshService
from china_outbound_analyzer.services.ingestion.price_refresh import PriceRefreshService
from china_outbound_analyzer.services.ingestion.seeder import seed_universe
from china_outbound_analyzer.services.jobs.scheduler import SchedulerService
from china_outbound_analyzer.services.recommendation.scoring import ScoringService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="China Outbound Stock AI Analyzer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("seed-universe", help="Seed the 15-stock universe and mock data sources")

    refresh_parser = subparsers.add_parser(
        "refresh-mock", help="Run deterministic mock market/news ingestion"
    )
    refresh_parser.add_argument("--lookback-days", type=int, default=400)
    refresh_prices_parser = subparsers.add_parser(
        "refresh-prices",
        help="Refresh price history using the configured provider with mock fallback",
    )
    refresh_prices_parser.add_argument("--lookback-days", type=int, default=400)
    refresh_news_parser = subparsers.add_parser(
        "refresh-news",
        help="Refresh recent news using the configured provider with mock fallback",
    )
    refresh_news_parser.add_argument("--limit", type=int, default=10)
    refresh_announcements_parser = subparsers.add_parser(
        "refresh-announcements",
        help="Refresh company announcements using the configured provider with mock fallback",
    )
    refresh_announcements_parser.add_argument("--limit", type=int, default=12)
    refresh_announcements_parser.add_argument("--lookback-days", type=int, default=365)
    subparsers.add_parser(
        "refresh-fundamentals",
        help="Refresh valuation and financial snapshots using the configured provider with mock fallback",
    )
    subparsers.add_parser(
        "analyze-mock",
        help="Generate deterministic AI artifacts from seeded mock data",
    )
    subparsers.add_parser(
        "analyze-live",
        help="Generate live AI artifacts from stored prices, news, fundamentals, and scores",
    )
    subparsers.add_parser(
        "score-universe",
        help="Compute factor scores and select the long/short recommendations",
    )
    scheduler_parser = subparsers.add_parser(
        "run-scheduler",
        help="Start the periodic refresh scheduler",
    )
    scheduler_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scheduler cycle and exit",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run-scheduler":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        scheduler = SchedulerService()
        if args.once:
            print([result.__dict__ for result in scheduler.run_pending_cycle()])
            return
        scheduler.run_forever()
        return

    with get_sync_session() as session:
        if args.command == "seed-universe":
            result = seed_universe(session)
            print(result)
            return

        if args.command == "refresh-mock":
            result = asyncio.run(MockRefreshService(session).run(lookback_days=args.lookback_days))
            print(result)
            return

        if args.command == "refresh-prices":
            result = asyncio.run(PriceRefreshService(session).run(lookback_days=args.lookback_days))
            print(result)
            return

        if args.command == "refresh-news":
            result = asyncio.run(NewsRefreshService(session).run(limit_per_symbol=args.limit))
            print(result)
            return

        if args.command == "refresh-announcements":
            result = asyncio.run(
                AnnouncementRefreshService(session).run(
                    limit_per_symbol=args.limit,
                    lookback_days=args.lookback_days,
                )
            )
            print(result)
            return

        if args.command == "refresh-fundamentals":
            result = asyncio.run(FundamentalsRefreshService(session).run())
            print(result)
            return

        if args.command == "analyze-mock":
            result = MockAIAnalysisService(session).run()
            print(result)
            return

        if args.command == "analyze-live":
            result = asyncio.run(LiveAIAnalysisService(session).run())
            print(result)
            return

        if args.command == "score-universe":
            result = ScoringService(session).run()
            print(result)
            return


if __name__ == "__main__":
    main()
