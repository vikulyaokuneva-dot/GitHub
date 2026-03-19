"""Scheduled daily wrapper with preflight gate.

Intended for cron/GitHub Actions operator usage.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from v4.entry.daily import run as run_daily
from v4.entry.preflight import run as run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 scheduled daily run")
    parser.add_argument("--seller", required=False)
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--production-mode", choices=["legacy", "v4", "shadow"], required=False)
    parser.add_argument("--allow-fallback-to-legacy", action="store_true")
    parser.add_argument("--shadow", dest="shadow_mode", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full-email-debug", action="store_true")
    args = parser.parse_args(argv)

    preflight = run_preflight(
        {
            "mode": "daily",
            "seller_id": args.seller,
            "run_date": args.run_date,
            "output_dir": args.output_dir,
            "production_mode": args.production_mode,
            "dry_run": bool(args.dry_run),
            "full_email_debug": bool(args.full_email_debug),
        }
    )
    if not preflight.get("ok", False):
        print("SCHEDULED RUN FAILED: preflight")
        print(f"errors={preflight.get('errors', [])}")
        return 2

    payload = {
        "seller_id": preflight.get("seller_id"),
        "run_date": args.run_date,
        "output_dir": preflight.get("resolved_output_dir"),
        "dry_run": bool(args.dry_run),
        "production_mode": args.production_mode,
        "allow_fallback_to_legacy": bool(args.allow_fallback_to_legacy),
        "shadow_mode": bool(args.shadow_mode),
        "full_email_debug": bool(args.full_email_debug),
    }
    result = run_daily(payload)

    production = result.get("production", {}) if isinstance(result, dict) else {}
    prod_diag = production.get("diagnostics", {}) if isinstance(production.get("diagnostics"), dict) else {}
    diagnostics = result.get("diagnostics", {}) if isinstance(result, dict) else {}
    summary = diagnostics.get("summary", {}) if isinstance(diagnostics.get("summary"), dict) else {}

    print("SCHEDULED RUN SUCCESS")
    if prod_diag:
        print(
            f"selected_mode={prod_diag.get('selected_mode')} "
            f"rollback_happened={prod_diag.get('rollback_happened')} "
            f"dry_run={prod_diag.get('dry_run')}"
        )
    else:
        print(
            f"mode={summary.get('mode')} "
            f"selected_mode={summary.get('selected_production_mode', 'v4_direct')} "
            f"dry_run={summary.get('dry_run')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
