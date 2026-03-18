"""v4 CLI entrypoint.

Input: CLI args for daily/audit run modes.
Output: process exit code.
Does not execute metrics/facts/outputs logic.
"""

from __future__ import annotations

import argparse

from .audit import run as run_audit
from .daily import run as run_daily


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WB AI Agent v4")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="Run daily_api_mode ingestion")
    p_daily.add_argument("--seller", required=True)
    p_daily.add_argument("--date", dest="run_date", required=False)
    p_daily.add_argument("--cabinet", dest="cabinet_name", required=False)
    p_daily.add_argument("--timezone", default="Europe/Moscow")
    p_daily.add_argument("--dry-run", action="store_true")

    p_audit = sub.add_parser("audit", help="Run audit_file_mode ingestion")
    p_audit.add_argument("--seller", required=True)
    p_audit.add_argument("--date", dest="run_date", required=False)
    p_audit.add_argument("--cabinet", dest="cabinet_name", required=False)
    p_audit.add_argument("--timezone", default="Europe/Moscow")
    p_audit.add_argument("--dry-run", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = {
        "seller_id": args.seller,
        "cabinet_name": args.cabinet_name,
        "run_date": args.run_date,
        "timezone": args.timezone,
        "dry_run": bool(args.dry_run),
    }

    if args.cmd == "daily":
        run_daily(payload)
    elif args.cmd == "audit":
        run_audit(payload)
    else:
        parser.error(f"Unsupported command: {args.cmd}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
