"""Operator smoke script: preflight + dry-run daily."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.entry.smoke import run as run_smoke


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 operator smoke daily (dry-run)")
    parser.add_argument("--seller", required=False)
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--production-mode", choices=["legacy", "v4", "shadow"], required=False)
    parser.add_argument("--shadow", dest="shadow_mode", action="store_true")
    parser.add_argument("--full-email-debug", action="store_true")
    args = parser.parse_args(argv)

    result = run_smoke(
        {
            "mode": "daily",
            "seller_id": args.seller,
            "run_date": args.run_date,
            "output_dir": args.output_dir,
            "production_mode": args.production_mode,
            "shadow_mode": bool(args.shadow_mode),
            "full_email_debug": bool(args.full_email_debug),
        }
    )
    print(f"SMOKE {result.get('status')}")
    return 0 if str(result.get("status")) == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
