"""v4 CLI entrypoint.

Input: CLI args for daily/audit run modes.
Output: process exit code.
Does not execute business logic inside CLI.
"""

from __future__ import annotations

import argparse

from .audit import run as run_audit
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
    p_daily.add_argument("--render-pdf", action="store_true")
    p_daily.add_argument("--email-preview", action="store_true")

    p_audit = sub.add_parser("audit", help="Run audit_file_mode pipeline")
    p_audit.add_argument("--input-path", dest="input_path", required=True)
    p_audit.add_argument("--seller", default="seller_001")
    p_audit.add_argument("--date", dest="run_date", required=False)
    p_audit.add_argument("--cabinet", dest="cabinet_name", required=False)
    p_audit.add_argument("--timezone", default="Europe/Moscow")
    p_audit.add_argument("--dry-run", action="store_true")
    p_audit.add_argument("--output-dir", dest="output_dir", required=False)
    p_audit.add_argument("--render-pdf", action="store_true")
    p_audit.add_argument("--email-preview", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "daily":
        payload = {
            "seller_id": args.seller,
            "cabinet_name": args.cabinet_name,
            "run_date": args.run_date,
            "timezone": args.timezone,
            "dry_run": bool(args.dry_run),
            "output_dir": args.output_dir,
            "render_pdf": bool(args.render_pdf),
            "email_preview": bool(args.email_preview),
        }
        run_daily(payload)
        return 0

    if args.cmd == "audit":
        payload = {
            "input_path": args.input_path,
            "seller_id": args.seller,
            "cabinet_name": args.cabinet_name,
            "run_date": args.run_date,
            "timezone": args.timezone,
            "dry_run": bool(args.dry_run),
            "output_dir": args.output_dir,
            "render_pdf": bool(args.render_pdf),
            "email_preview": bool(args.email_preview),
        }
        run_audit(payload)
        return 0

    parser.error(f"Unsupported command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
