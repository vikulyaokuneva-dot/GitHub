"""Shadow-mode daily runner.

Runs v4 daily pipeline in isolated shadow output and writes comparison.json.
Does not switch production runtime.
"""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.shadow.runner import run_shadow_daily


def run_smoke_shadow(
    *,
    seller_id: str,
    run_date: str,
    output_root: str,
    run_v4: bool = True,
    run_legacy: bool = False,
) -> int:
    try:
        result = run_shadow_daily(
            seller_id=seller_id,
            run_date=run_date,
            output_root=output_root,
            run_v4=run_v4,
            run_legacy=run_legacy,
        )
    except Exception:
        traceback.print_exc()
        return 1

    comparison = result.get("comparison", {})
    if not isinstance(comparison, dict):
        print("SHADOW FAILED: comparison payload is missing")
        return 2

    comparison_path = Path(output_root).resolve() / "comparison.json"
    if not comparison_path.exists():
        print(f"SHADOW FAILED: comparison.json was not written: {comparison_path}")
        return 2

    print("SHADOW OK")
    print(f"seller_id={seller_id}")
    print(f"run_date={run_date}")
    print(f"output_root={Path(output_root).resolve()}")
    print(f"severity={comparison.get('severity')}")
    print(f"differences={len(comparison.get('differences', []))}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v4 shadow daily run")
    parser.add_argument("--seller", dest="seller_id", required=True)
    parser.add_argument("--date", dest="run_date", required=True)
    parser.add_argument("--output-dir", dest="output_root", required=True)
    parser.add_argument("--run-legacy", action="store_true")
    parser.add_argument("--skip-v4", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_smoke_shadow(
        seller_id=str(args.seller_id),
        run_date=str(args.run_date),
        output_root=str(args.output_root),
        run_v4=not bool(args.skip_v4),
        run_legacy=bool(args.run_legacy),
    )


if __name__ == "__main__":
    raise SystemExit(main())

