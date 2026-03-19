"""Operator preflight script for daily mode."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.entry.preflight import run as run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 daily preflight")
    parser.add_argument("--seller", required=False)
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--production-mode", choices=["legacy", "v4", "shadow"], required=False)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    result = run_preflight(
        {
            "mode": "daily",
            "seller_id": args.seller,
            "run_date": args.run_date,
            "output_dir": args.output_dir,
            "production_mode": args.production_mode,
            "dry_run": bool(args.dry_run),
        }
    )

    print(f"PREFLIGHT {result.get('status')}")
    print(f"seller_id={result.get('seller_id')}")
    print(f"output_dir={result.get('resolved_output_dir')}")
    print(f"errors={len(result.get('errors', []))} warnings={len(result.get('warnings', []))}")
    return 0 if bool(result.get("ok", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())

