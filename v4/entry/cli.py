"""v4 CLI entrypoint.

Input: CLI args for daily run mode.
Output: process exit code.
Does not execute business logic inside CLI.
"""

from __future__ import annotations

import argparse

from .daily import run as run_daily


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WB AI Agent v4")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="Run daily_api_mode pipeline")
    p_daily.add_argument("--seller", required=True)
    p_daily.add_argument("--date", dest="run_date", required=False)
    p_daily.add_argument("--cabinet", dest="cabinet_name", required=False)
    p_daily.add_argument("--timezone", default="Europe/Moscow")
    p_daily.add_argument("--dry-run", action="store_true")
    p_daily.add_argument("--output-dir", dest="output_dir", required=False)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd != "daily":
        parser.error(f"Unsupported command: {args.cmd}")

    payload = {
        "seller_id": args.seller,
        "cabinet_name": args.cabinet_name,
        "run_date": args.run_date,
        "timezone": args.timezone,
        "dry_run": bool(args.dry_run),
        "output_dir": args.output_dir,
    }
    run_daily(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
