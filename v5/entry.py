"""
CLI entry point for v5.

Usage:
  python -m v5 daily --cabinet seller_001
  python -m v5 audit --cabinet seller_001 --date 2024-03-30
  python -m v5 analytics --cabinet seller_001
"""

import argparse
import asyncio
from datetime import datetime, date

from .orchestrator import Orchestrator
from .config import get_config
from .domain import ProcessingStatus


async def main() -> int:
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="WB Analytics v5 – Unified Data Platform"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # daily mode
    daily_parser = subparsers.add_parser("daily", help="Daily API pull")
    daily_parser.add_argument("--cabinet", required=True, help="Cabinet ID (e.g., seller_001)")
    
    # audit mode
    audit_parser = subparsers.add_parser("audit", help="Report audit mode")
    audit_parser.add_argument("--cabinet", required=True, help="Cabinet ID")
    audit_parser.add_argument("--date", default=str(date.today()), help="Report date (YYYY-MM-DD)")
    
    # analytics query
    analytics_parser = subparsers.add_parser("analytics", help="View analytics")
    analytics_parser.add_argument("--cabinet", required=True, help="Cabinet ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Load config
    config = get_config()
    
    # Create orchestrator
    orchestrator = Orchestrator(config)
    
    # Execute command
    if args.command == "daily":
        result = await orchestrator.run_daily(args.cabinet)
        print(result.message)
        return 0 if result.status != ProcessingStatus.FAILED else 1
    elif args.command == "audit":
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        result = await orchestrator.run_audit(args.cabinet, target_date)
        print(result.message)
        return 0 if result.status != ProcessingStatus.FAILED else 1
    elif args.command == "analytics":
        await orchestrator.show_analytics(args.cabinet)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
