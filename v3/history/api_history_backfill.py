from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable
from zoneinfo import ZoneInfo

from wb_api_core.client import WBApiClient
from wb_api_core.loaders import load_cabinet_commerce

from .history_store import load_history_index, update_history_index


MOSCOW_TIMEZONE = "Europe/Moscow"


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _selected(row: Dict[str, Any]) -> Dict[str, Any]:
    statistic = row.get("statistic")
    if not isinstance(statistic, dict):
        return {}
    selected = statistic.get("selected")
    return selected if isinstance(selected, dict) else {}


def _sum_selected(rows: Iterable[Dict[str, Any]], *keys: str) -> Decimal:
    total = Decimal("0")
    for row in rows:
        selected = _selected(row)
        for key in keys:
            if key in selected and selected.get(key) not in (None, ""):
                total += _decimal(selected.get(key))
                break
    return total


def _count_text(value: Decimal) -> int | str:
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    return _decimal_text(value)


def _operational_date(run_date: str, *, now: datetime | None = None) -> date:
    requested = date.fromisoformat(run_date)
    local_now = now or datetime.now(ZoneInfo(MOSCOW_TIMEZONE))
    local_today = local_now.astimezone(ZoneInfo(MOSCOW_TIMEZONE)).date()
    return local_today - timedelta(days=1) if requested >= local_today else requested


def _has_snapshot_for_date(history_dir: Path, target_date: str) -> bool:
    snapshots = load_history_index(history_dir).get("snapshots", [])
    if not isinstance(snapshots, list):
        return False
    return any(
        isinstance(item, dict) and str(item.get("date") or "") == target_date
        for item in snapshots
    )


def backfill_previous_operational_day(
    *,
    seller_id: str,
    run_date: str,
    repo_root: Path,
    client: WBApiClient | None = None,
    now: datetime | None = None,
) -> Dict[str, Any]:
    operational_date = _operational_date(run_date, now=now)
    target_date = (operational_date - timedelta(days=1)).isoformat()
    history_dir = Path(repo_root) / "cabinets" / seller_id / "history"

    if _has_snapshot_for_date(history_dir, target_date):
        return {
            "status": "skipped_existing",
            "seller_id": seller_id,
            "operational_date": operational_date.isoformat(),
            "target_date": target_date,
        }

    api_client = client or WBApiClient()
    bundle = load_cabinet_commerce(
        api_client,
        target_date,
        seller_id=seller_id,
        repo_root=str(repo_root),
    )
    debug = bundle.get("debug", {}) if isinstance(bundle.get("debug"), dict) else {}
    if not bool(debug.get("success", False)):
        return {
            "status": "source_unavailable",
            "seller_id": seller_id,
            "operational_date": operational_date.isoformat(),
            "target_date": target_date,
            "source": "sales_funnel_api_v3",
            "error": str(debug.get("final_failure_reason") or debug.get("error_text") or ""),
        }

    rows = [row for row in bundle.get("rows_raw", []) if isinstance(row, dict)]
    open_count = _sum_selected(rows, "openCount", "openCardCount")
    cart_count = _sum_selected(rows, "cartCount", "addToCartCount")
    orders_count = _sum_selected(rows, "orderCount")
    orders_amount = _sum_selected(rows, "orderSum")
    buyouts_count = _sum_selected(rows, "buyoutCount")
    buyouts_amount = _sum_selected(rows, "buyoutSum")

    source_dir = history_dir / "api_backfill" / target_date
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "sales_funnel_api_v3.json"
    fetched_at = datetime.now(timezone.utc).isoformat()
    raw_path.write_text(
        json.dumps(
            {
                "source": "sales_funnel_api",
                "api_version": "v3",
                "endpoint": "/api/analytics/v3/sales-funnel/products",
                "target_date": target_date,
                "fetched_at_utc": fetched_at,
                "rows": rows,
                "debug": debug,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    sku_ids = {
        str((row.get("product") or {}).get("nmId") or "").strip()
        for row in rows
        if isinstance(row.get("product"), dict)
        and str((row.get("product") or {}).get("nmId") or "").strip()
    }
    snapshot_meta = {
        "date": target_date,
        "path": f"api_backfill/{target_date}",
        "files": [raw_path.name],
        "kpi": {
            "revenue": _decimal_text(buyouts_amount),
            "profit": None,
            "buyouts": _count_text(buyouts_count),
            "ads_spend": None,
            "funnel": {
                "impressions": None,
                "open_count": _count_text(open_count),
                "cart_count": _count_text(cart_count),
                "orders_count": _count_text(orders_count),
                "buyouts_count": _count_text(buyouts_count),
                "clicks": _count_text(open_count),
                "cart": _count_text(cart_count),
                "orders": _count_text(orders_count),
                "buyouts": _count_text(buyouts_count),
                "orders_amount": _decimal_text(orders_amount),
                "buyouts_amount": _decimal_text(buyouts_amount),
            },
            "orders": _count_text(orders_count),
            "orders_amount": _decimal_text(orders_amount),
            "sku_count": len(sku_ids),
            "valid_sku_count": len(sku_ids),
            "invalid_sku_rows": 0,
        },
        "seller_id": seller_id,
        "source": {
            "name": "sales_funnel_api",
            "api_version": "v3",
            "fetched_at_utc": fetched_at,
            "raw_payload": f"api_backfill/{target_date}/{raw_path.name}",
        },
    }
    update_history_index(history_dir, snapshot_meta)
    return {
        "status": "backfilled",
        "seller_id": seller_id,
        "operational_date": operational_date.isoformat(),
        "target_date": target_date,
        "rows": len(rows),
        "snapshot": snapshot_meta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the missing previous operational day from the WB sales-funnel API."
    )
    parser.add_argument("--seller", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    result = backfill_previous_operational_day(
        seller_id=str(args.seller),
        run_date=str(args.date),
        repo_root=Path(args.repo_root).resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
