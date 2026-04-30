from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

from .artifacts import (
    apply_latest_successful_live_fallback,
    build_debug,
    read_latest_successful_snapshot,
    write_artifacts,
)
from .client import WBApiClient
from .loaders import load_bundle
from .normalize import normalize_bundle
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
    latest_snapshot_cache = read_latest_successful_snapshot(
        repo_root=resolved_repo_root,
        seller_id=seller_id,
    )
    reconcile_result = apply_latest_successful_live_fallback(
        reconcile_result=reconcile_result,
        raw_bundle=raw_bundle,
        latest_snapshot_cache=latest_snapshot_cache,
    )
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
