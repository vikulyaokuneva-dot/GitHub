"""Smoke runner for v4 daily pipeline.

Runs v4 daily pipeline end-to-end and validates minimal output invariants.
Does not schedule jobs and does not write outside provided output_dir.
"""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from typing import Any
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.pipeline.runners.daily_runner import run_daily_pipeline


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def run_smoke(*, seller_id: str, run_date: str | None, timezone: str, output_dir: str | None, dry_run: bool) -> int:
    run_context: dict[str, Any] = {
        "seller_id": seller_id,
        "run_date": run_date,
        "timezone": timezone,
        "dry_run": dry_run,
    }
    try:
        result = run_daily_pipeline(run_context=run_context, output_dir=output_dir)
    except Exception:
        traceback.print_exc()
        return 1

    required_keys = {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs"}
    missing_keys = [key for key in required_keys if key not in result]
    if missing_keys:
        print(f"SMOKE FAILED: missing keys in pipeline result: {missing_keys}")
        return 2

    outputs = result.get("outputs", {})
    artifacts = outputs.get("artifacts", {}) if isinstance(outputs, dict) else {}
    saved_files = artifacts.get("saved_files", {}) if isinstance(artifacts, dict) else {}

    if output_dir is None:
        if saved_files:
            print("SMOKE FAILED: output_dir is not set but artifacts were written")
            return 2
    else:
        root = Path(output_dir).resolve()
        for key, path in saved_files.items():
            if not _is_within(root, Path(path)):
                print(f"SMOKE FAILED: artifact '{key}' was written outside output_dir: {path}")
                return 2
            if not Path(path).exists():
                print(f"SMOKE FAILED: artifact '{key}' path does not exist: {path}")
                return 2

    warnings_count = len(result.get("warnings", []))
    summary = result.get("diagnostics", {}).get("summary", {})
    partial_flag = summary.get("partial_flag")
    print("SMOKE OK")
    print(f"seller_id={seller_id}")
    print(f"output_dir={output_dir}")
    print(f"warnings_count={warnings_count}")
    print(f"partial_flag={partial_flag}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v4 daily pipeline smoke run")
    parser.add_argument("--seller", dest="seller_id", default="seller_001")
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--timezone", default="Europe/Moscow")
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_smoke(
        seller_id=str(args.seller_id),
        run_date=args.run_date,
        timezone=str(args.timezone),
        output_dir=args.output_dir,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
