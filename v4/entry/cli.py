"""v4 CLI skeleton.

Input: command-line arguments for daily/audit modes.
Output: process exit code.
Does not execute real ingestion/metrics logic in stage 1.
"""

from __future__ import annotations

import argparse

from .daily import run as run_daily
from .audit import run as run_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WB AI Agent v4 skeleton")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="Run daily_api_mode skeleton")
    p_daily.add_argument("--seller", required=True)
    p_daily.add_argument("--date", required=True)

    p_audit = sub.add_parser("audit", help="Run audit_file_mode skeleton")
    p_audit.add_argument("--seller", required=True)
    p_audit.add_argument("--date", required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "daily":
        run_daily({"seller_id": args.seller, "run_date": args.date, "mode": "daily_api_mode"})
    else:
        run_audit({"seller_id": args.seller, "run_date": args.date, "mode": "audit_file_mode"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
