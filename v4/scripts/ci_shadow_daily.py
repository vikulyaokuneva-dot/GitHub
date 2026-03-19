"""CI helper for v4 shadow daily mode.

Runs shadow daily and fails CI only when comparison severity is high.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.shadow.runner import run_shadow_daily


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 CI shadow daily")
    parser.add_argument("--seller", dest="seller_id", required=True)
    parser.add_argument("--date", dest="run_date", required=True)
    parser.add_argument("--output-dir", dest="output_root", required=True)
    parser.add_argument("--run-legacy", action="store_true")
    args = parser.parse_args(argv)

    result = run_shadow_daily(
        seller_id=str(args.seller_id),
        run_date=str(args.run_date),
        output_root=str(args.output_root),
        run_v4=True,
        run_legacy=bool(args.run_legacy),
    )

    comparison = result.get("comparison", {})
    severity = str(comparison.get("severity", "low")) if isinstance(comparison, dict) else "low"
    print(f"shadow severity={severity}")
    if severity == "high":
        print("CI SHADOW FAILED: severity is high")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
