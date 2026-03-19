"""Smoke runner for v4 delivery PDF rendering.

Runs pipeline to obtain outputs payload, then runs delivery_stage PDF rendering.
Does not change business logic and does not write outside provided output_dir.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import traceback
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.pipeline.runners.audit_runner import run_audit_pipeline
from v4.pipeline.runners.daily_runner import run_daily_pipeline
from v4.pipeline.stages.delivery_stage import run_delivery_stage


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def run_smoke(
    *,
    mode: str,
    seller_id: str,
    run_date: str | None,
    timezone: str,
    input_path: str | None,
    output_dir: str,
    dry_run: bool,
) -> int:
    normalized_mode = "audit" if str(mode).strip().lower() == "audit" else "daily"

    try:
        if normalized_mode == "daily":
            result = run_daily_pipeline(
                run_context={
                    "seller_id": seller_id,
                    "run_date": run_date,
                    "timezone": timezone,
                    "dry_run": dry_run,
                },
                output_dir=None,
            )
        else:
            if not str(input_path or "").strip():
                print("SMOKE FAILED: input_path is required for audit mode")
                return 2
            result = run_audit_pipeline(
                input_path=str(input_path),
                run_context={
                    "seller_id": seller_id,
                    "run_date": run_date,
                    "timezone": timezone,
                    "dry_run": dry_run,
                },
                output_dir=None,
            )
    except Exception:
        traceback.print_exc()
        return 1

    try:
        delivery = run_delivery_stage(
            outputs=result.get("outputs", {}),
            output_dir=output_dir,
            enable_pdf_render=True,
            enable_email_preview=False,
        )
    except Exception:
        traceback.print_exc()
        return 1

    pdf_path = delivery.get("pdf_path")
    if not pdf_path:
        print("SMOKE FAILED: pdf_path is missing")
        return 2

    root = Path(output_dir).resolve()
    target = Path(str(pdf_path)).resolve()
    if not _is_within(root, target):
        print(f"SMOKE FAILED: rendered PDF is outside output_dir: {target}")
        return 2
    if not target.exists():
        print(f"SMOKE FAILED: rendered PDF does not exist: {target}")
        return 2

    print("SMOKE OK")
    print(f"mode={normalized_mode}")
    print(f"pdf_path={target}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v4 delivery PDF render smoke run")
    parser.add_argument("--mode", choices=["daily", "audit"], default="daily")
    parser.add_argument("--seller", dest="seller_id", default="seller_001")
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--timezone", default="Europe/Moscow")
    parser.add_argument("--input-path", dest="input_path", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_smoke(
        mode=str(args.mode),
        seller_id=str(args.seller_id),
        run_date=args.run_date,
        timezone=str(args.timezone),
        input_path=args.input_path,
        output_dir=str(args.output_dir),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
