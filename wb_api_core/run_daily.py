from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

from .artifacts import (
    apply_latest_successful_live_fallback,
    build_debug,
    read_latest_finance_cache,
    read_latest_successful_snapshot,
    write_artifacts,
    write_finance_cache,
)
from .client import WBApiClient
from .loaders import load_bundle
from .normalize import normalize_bundle
from .pricing import PriceSnapshotStore, build_price_analytics, write_raw_price_payloads
from .reconcile import reconcile_bundle
from .snapshot import build_snapshot

DEFAULT_TIMEZONE = "Europe/Moscow"


def _resolve_run_date(run_date: str) -> str:
    return datetime.strptime(str(run_date or "").strip(), "%Y-%m-%d").date().isoformat()


def _resolve_operational_date(run_date: str, timezone_name: str) -> str:
    requested_date = datetime.strptime(run_date, "%Y-%m-%d").date()
    try:
        local_today = datetime.now(ZoneInfo(timezone_name)).date()
    except Exception:
        local_today = date.today()
    effective_date = requested_date
    if requested_date >= local_today:
        effective_date = local_today - timedelta(days=1)
    return effective_date.isoformat()


def run_daily(*, seller: str, run_date: str, repo_root: str | None = None) -> Dict[str, Any]:
    seller_id = str(seller or "").strip()
    if not seller_id:
        raise ValueError("--seller is required")

    resolved_run_date = _resolve_run_date(run_date)
    timezone_name = str(os.getenv("TZ", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    operational_date = _resolve_operational_date(resolved_run_date, timezone_name)
    resolved_repo_root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    wb_api_token_value = os.getenv("WB_API_TOKEN", "")
    print(
        "[wb_api_core-entry] WB_API_TOKEN "
        f"present={str(bool(wb_api_token_value)).lower()} "
        f"len={len(wb_api_token_value)}"
    )
    client = WBApiClient()
    print(
        "[wb_api_core] token_resolution "
        f"token_present={str(client.has_token()).lower()} "
        f"token_env_name_used={client.token_env_name_used or '<none>'}"
    )
    raw_bundle = load_bundle(client, operational_date, seller_id=seller_id, repo_root=resolved_repo_root)
    normalized_bundle = normalize_bundle(raw_bundle)
    reconcile_result = reconcile_bundle(
        raw_bundle=raw_bundle,
        normalized_bundle=normalized_bundle,
        target_date=operational_date,
    )
    price_store = PriceSnapshotStore.for_seller(repo_root=resolved_repo_root, seller_id=seller_id)
    price_warnings = list(reconcile_result.get("warnings", []) or [])
    try:
        price_store.upsert_current_prices(
            seller_id=seller_id,
            rows=normalized_bundle.get("product_price_rows", []),
        )
        price_store.upsert_fbs_orders(
            seller_id=seller_id,
            rows=normalized_bundle.get("fbs_order_price_rows", []),
        )
        captured_at = str((raw_bundle.get("product_prices") or {}).get("captured_at") or "")
        raw_paths = write_raw_price_payloads(
            repo_root=resolved_repo_root,
            seller_id=seller_id,
            captured_at=captured_at,
            goods_payload=(raw_bundle.get("product_prices") or {}).get("raw_payload"),
            fbs_payload=(raw_bundle.get("fbs_order_prices") or {}).get("raw_payload"),
        )
        price_analytics = build_price_analytics(
            seller_id=seller_id,
            operational_date=operational_date,
            store_rows=price_store.rows(seller_id=seller_id),
            finance_rows=(reconcile_result.get("finance_final_daily") or {}).get("rows", []),
        )
        price_analytics["raw_payload_paths"] = raw_paths
        reconcile_result["price_analytics"] = price_analytics
    except Exception as exc:
        price_warnings.append(
            {
                "code": "price_analytics_unavailable",
                "message": f"Price analytics could not be built: {exc}",
                "level": "warning",
                "block": "price_analytics",
            }
        )
        reconcile_result["price_analytics"] = {
            "available": False,
            "sku_rows": [],
            "changes": {"rows": [], "automatic_price_changes": False},
            "reconciliation": {"status": "unavailable"},
        }
    reconcile_result["warnings"] = price_warnings
    latest_snapshot_cache = read_latest_successful_snapshot(
        repo_root=resolved_repo_root,
        seller_id=seller_id,
    )
    reconcile_result = apply_latest_successful_live_fallback(
        reconcile_result=reconcile_result,
        raw_bundle=raw_bundle,
        latest_snapshot_cache=latest_snapshot_cache,
    )

    finance_daily = reconcile_result.get("finance_final_daily", {})
    if isinstance(finance_daily, dict) and finance_daily.get("available"):
        write_finance_cache(
            repo_root=resolved_repo_root,
            seller_id=seller_id,
            finance_block=finance_daily,
        )
    elif isinstance(finance_daily, dict) and not finance_daily.get("available"):
        warnings = list(reconcile_result.get("warnings", []) or [])
        warnings.append({
            "code": "finance_final_unavailable_for_date",
            "message": f"Finance data not available for {resolved_run_date}. No fallback applied.",
            "level": "warning",
            "block": "finance_final",
        })
        reconcile_result["warnings"] = warnings

    snapshot = build_snapshot(
        seller_id=seller_id,
        run_date=resolved_run_date,
        operational_date=operational_date,
        timezone_name=timezone_name,
        reconcile_result=reconcile_result,
    )
    debug = build_debug(
        seller_id=seller_id,
        run_date=resolved_run_date,
        operational_date=operational_date,
        timezone_name=timezone_name,
        raw_bundle=raw_bundle,
        normalized_bundle=normalized_bundle,
        reconcile_result=reconcile_result,
    )
    artifacts_dir = write_artifacts(
        repo_root=resolved_repo_root,
        seller_id=seller_id,
        run_date=resolved_run_date,
        snapshot=snapshot,
        debug=debug,
        reconcile_result=reconcile_result,
    )
    return {
        "seller_id": seller_id,
        "run_date": resolved_run_date,
        "operational_date": operational_date,
        "artifacts_dir": artifacts_dir,
        "snapshot": snapshot,
        "debug": debug,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal WB API core daily flow (first wave).")
    parser.add_argument("--seller", required=True, help="seller id")
    parser.add_argument("--date", required=True, help="requested run date YYYY-MM-DD")
    args = parser.parse_args()

    result = run_daily(seller=args.seller, run_date=args.date)
    print(
        "[wb_api_core] "
        f"seller={result.get('seller_id')} "
        f"run_date={result.get('run_date')} "
        f"operational_date={result.get('operational_date')}"
    )
    print(f"[wb_api_core] artifacts_dir={result.get('artifacts_dir')}")


if __name__ == "__main__":
    main()
