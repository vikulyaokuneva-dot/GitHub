"""v4 CLI entrypoint with operator flow.

Supported operator path:
1) preflight
2) smoke (dry-run)
3) manual daily/audit run
"""

from __future__ import annotations

import argparse
from typing import Any

from ..cabinets.registry import get_enabled_cabinets
from .audit import run as run_audit
from .daily import run as run_daily
from .preflight import run as run_preflight
from .smoke import run as run_smoke


def _configure_common_daily_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seller", required=False)
    parser.add_argument("--sellers", required=False, help="Comma-separated seller ids for batch mode")
    parser.add_argument("--date", dest="run_date", required=False, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--cabinet", dest="cabinet_name", required=False)
    parser.add_argument("--cabinet-id", dest="cabinet_id", required=False)
    parser.add_argument("--timezone", default="Europe/Moscow")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--render-pdf", action="store_true")
    parser.add_argument("--email-preview", action="store_true")
    parser.add_argument(
        "--production-mode",
        dest="production_mode",
        choices=["legacy", "v4", "shadow"],
        required=False,
        help="Controlled production runner mode",
    )
    parser.add_argument("--allow-fallback-to-legacy", action="store_true")
    parser.add_argument("--shadow-mode", action="store_true")


def _configure_common_audit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-path", dest="input_path", required=False)
    parser.add_argument("--input-map", dest="input_map", required=False, help="seller_id=path pairs, comma-separated")
    parser.add_argument("--seller", default="seller_001")
    parser.add_argument("--sellers", required=False, help="Comma-separated seller ids for batch mode")
    parser.add_argument("--date", dest="run_date", required=False, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--cabinet", dest="cabinet_name", required=False)
    parser.add_argument("--cabinet-id", dest="cabinet_id", required=False)
    parser.add_argument("--timezone", default="Europe/Moscow")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--render-pdf", action="store_true")
    parser.add_argument("--email-preview", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WB AI Agent v4 operator CLI (preflight -> smoke -> run)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser(
        "daily",
        help="Manual daily run (real run)",
        description="Run v4 daily pipeline manually.",
    )
    _configure_common_daily_args(p_daily)

    p_audit = sub.add_parser(
        "audit",
        help="Manual audit run (real run)",
        description="Run v4 audit pipeline manually.",
    )
    _configure_common_audit_args(p_audit)

    p_preflight = sub.add_parser(
        "preflight",
        help="Validation checks before run",
        description="Run safe readiness checks: config, features, seller registry, env, paths, mode resolution.",
    )
    p_preflight.add_argument("--mode", choices=["daily", "audit"], default="daily")
    p_preflight.add_argument("--seller", required=False)
    p_preflight.add_argument("--sellers", required=False, help="Comma-separated seller ids (first is used for checks)")
    p_preflight.add_argument("--date", dest="run_date", required=False)
    p_preflight.add_argument("--output-dir", dest="output_dir", required=False)
    p_preflight.add_argument("--production-mode", choices=["legacy", "v4", "shadow"], required=False)
    p_preflight.add_argument("--dry-run", action="store_true")

    p_smoke = sub.add_parser(
        "smoke",
        help="Dry-run smoke validation",
        description="Run preflight + dry-run pipeline with deterministic SUCCESS/FAILED status.",
    )
    p_smoke.add_argument("--mode", choices=["daily", "audit"], default="daily")
    p_smoke.add_argument("--seller", required=False)
    p_smoke.add_argument("--sellers", required=False, help="Comma-separated seller ids (first is used)")
    p_smoke.add_argument("--date", dest="run_date", required=False)
    p_smoke.add_argument("--output-dir", dest="output_dir", required=False)
    p_smoke.add_argument("--input-path", dest="input_path", required=False)
    p_smoke.add_argument("--production-mode", choices=["legacy", "v4", "shadow"], required=False)
    p_smoke.add_argument("--shadow", dest="shadow_mode", action="store_true")
    p_smoke.add_argument("--render-pdf", action="store_true")
    p_smoke.add_argument("--email-preview", action="store_true")

    return parser


def _resolve_default_daily_seller(parser: argparse.ArgumentParser, seller: str | None, sellers: str | None) -> str | None:
    if str(seller or "").strip() or str(sellers or "").strip():
        return seller

    enabled = get_enabled_cabinets()
    if len(enabled) == 1:
        return enabled[0].seller_id
    if len(enabled) == 0:
        parser.error("daily: в seller registry нет включенных seller; укажите --seller явно")
    parser.error("daily: найдено несколько seller; укажите --seller или --sellers")
    return None


def _print_result_summary(command: str, result: dict[str, Any]) -> None:
    if command == "preflight":
        print(f"PREFLIGHT {result.get('status', 'UNKNOWN')}")
        print(f"mode={result.get('mode')} seller_id={result.get('seller_id')} dry_run={bool(result.get('dry_run', False))}")
        print(f"output_dir={result.get('resolved_output_dir')}")
        print(f"errors={len(result.get('errors', []))} warnings={len(result.get('warnings', []))}")
        return

    if command == "smoke":
        print(f"SMOKE {result.get('status', 'UNKNOWN')}")
        print(f"mode={result.get('mode')} dry_run={bool(result.get('dry_run', False))}")
        summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
        print(
            "partial_flag="
            f"{bool(summary.get('partial_flag', False))} "
            f"warnings_count={summary.get('warnings_count')} "
            f"output_dir_label={summary.get('output_dir_label')}"
        )
        return

    production = result.get("production", {}) if isinstance(result.get("production"), dict) else {}
    prod_diag = production.get("diagnostics", {}) if isinstance(production.get("diagnostics"), dict) else {}
    diagnostics = result.get("diagnostics", {}) if isinstance(result.get("diagnostics"), dict) else {}
    summary = diagnostics.get("summary", {}) if isinstance(diagnostics.get("summary"), dict) else {}

    if prod_diag:
        print("RUN SUCCESS")
        print(
            "selected_mode="
            f"{prod_diag.get('selected_mode')} "
            f"reason={prod_diag.get('switch_reason')} "
            f"rollback_happened={bool(prod_diag.get('rollback_happened', False))} "
            f"dry_run={bool(prod_diag.get('dry_run', False))}"
        )
        print(f"seller_id={prod_diag.get('seller_id')} run_date={prod_diag.get('run_date')}")
        print(f"output_dir_label={prod_diag.get('output_dir_label')}")
        return

    print("RUN SUCCESS")
    print(
        f"mode={summary.get('mode')} "
        f"seller_id={summary.get('seller_id')} "
        f"partial_flag={bool(summary.get('partial_flag', False))} "
        f"warnings_count={summary.get('warnings_count')}"
    )
    print(
        "selected_mode="
        f"{summary.get('selected_production_mode', 'v4_direct')} "
        f"dry_run={bool(summary.get('dry_run', False))}"
    )
    print(f"output_dir_label={summary.get('output_dir_label')}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "daily":
            seller_id = _resolve_default_daily_seller(parser, args.seller, args.sellers)
            payload = {
                "seller_id": seller_id,
                "seller_ids": args.sellers,
                "cabinet_name": args.cabinet_name,
                "cabinet_id": args.cabinet_id,
                "run_date": args.run_date,
                "timezone": args.timezone,
                "dry_run": bool(args.dry_run),
                "output_dir": args.output_dir,
                "render_pdf": bool(args.render_pdf),
                "email_preview": bool(args.email_preview),
                "production_mode": args.production_mode,
                "allow_fallback_to_legacy": bool(args.allow_fallback_to_legacy),
                "shadow_mode": bool(args.shadow_mode),
            }
            result = run_daily(payload)
            _print_result_summary("daily", result if isinstance(result, dict) else {})
            return 0

        if args.cmd == "audit":
            if not str(args.input_path or "").strip() and not str(args.input_map or "").strip():
                parser.error("audit requires --input-path or --input-map")
            payload = {
                "input_path": args.input_path,
                "input_map": args.input_map,
                "seller_id": args.seller,
                "seller_ids": args.sellers,
                "cabinet_name": args.cabinet_name,
                "cabinet_id": args.cabinet_id,
                "run_date": args.run_date,
                "timezone": args.timezone,
                "dry_run": bool(args.dry_run),
                "output_dir": args.output_dir,
                "render_pdf": bool(args.render_pdf),
                "email_preview": bool(args.email_preview),
            }
            result = run_audit(payload)
            _print_result_summary("audit", result if isinstance(result, dict) else {})
            return 0

        if args.cmd == "preflight":
            payload = {
                "mode": args.mode,
                "seller_id": args.seller,
                "seller_ids": args.sellers,
                "run_date": args.run_date,
                "output_dir": args.output_dir,
                "production_mode": args.production_mode,
                "dry_run": bool(args.dry_run),
            }
            result = run_preflight(payload)
            _print_result_summary("preflight", result)
            return 0 if bool(result.get("ok", False)) else 2

        if args.cmd == "smoke":
            if args.mode == "audit" and not str(args.input_path or "").strip():
                parser.error("smoke --mode audit requires --input-path")
            payload = {
                "mode": args.mode,
                "seller_id": args.seller,
                "seller_ids": args.sellers,
                "run_date": args.run_date,
                "output_dir": args.output_dir,
                "input_path": args.input_path,
                "production_mode": args.production_mode,
                "shadow_mode": bool(args.shadow_mode),
                "render_pdf": bool(args.render_pdf),
                "email_preview": bool(args.email_preview),
            }
            result = run_smoke(payload)
            _print_result_summary("smoke", result)
            return 0 if str(result.get("status")) == "SUCCESS" else 2

        parser.error(f"Unsupported command: {args.cmd}")
        return 2
    except Exception as exc:
        print(f"RUN FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

