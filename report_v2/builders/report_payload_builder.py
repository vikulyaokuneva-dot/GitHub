from __future__ import annotations

from typing import Any

from ..contracts.report_payload_schema import ReportPayloadV2, WarningItemV2


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _warning(code: str, message: str, *, block: str, level: str = "warning") -> WarningItemV2:
    payload: WarningItemV2 = {
        "code": _safe_str(code),
        "message": _safe_str(message),
        "level": _safe_str(level) or "warning",
        "block": _safe_str(block),
    }
    return payload


def _normalize_debug_warnings(items: Any) -> list[WarningItemV2]:
    warnings: list[WarningItemV2] = []
    if not isinstance(items, list):
        return warnings
    for item in items:
        if isinstance(item, dict):
            message = _safe_str(item.get("message"))
            if not message:
                continue
            warnings.append(
                _warning(
                    _safe_str(item.get("code")) or "debug_warning",
                    message,
                    block=_safe_str(item.get("block")) or "meta",
                    level=_safe_str(item.get("level")) or "warning",
                )
            )
            continue
        message = _safe_str(item)
        if message:
            warnings.append(_warning("debug_warning", message, block="meta"))
    return warnings


def _resolve_buyouts_owner(
    *, cabinet_daily: dict[str, Any], finance_daily: dict[str, Any], warnings: list[WarningItemV2]
) -> tuple[int | None, float | None, str, str]:
    finance_buyouts_count = _safe_int(finance_daily.get("buyouts_count"))
    finance_buyouts_amount = _safe_float(finance_daily.get("buyouts_amount"))
    if finance_buyouts_count is not None or finance_buyouts_amount is not None:
        return (
            finance_buyouts_count,
            finance_buyouts_amount,
            "finance_final_daily",
            _safe_str(finance_daily.get("source")) or "finance_final_daily",
        )

    cabinet_buyouts_count = _safe_int(cabinet_daily.get("buyouts_count"))
    cabinet_buyouts_amount = _safe_float(cabinet_daily.get("buyouts_amount"))
    if cabinet_buyouts_count is not None or cabinet_buyouts_amount is not None:
        warnings.append(
            _warning(
                "buyouts_owner_from_cabinet_commerce",
                "Buyouts are mapped from cabinet_commerce_daily because finance_final_daily does not provide them.",
                block="cabinet_commerce",
            )
        )
        return (
            cabinet_buyouts_count,
            cabinet_buyouts_amount,
            "cabinet_commerce_daily",
            _safe_str(cabinet_daily.get("source")) or "cabinet_commerce_daily",
        )

    warnings.append(
        _warning(
            "buyouts_missing_in_snapshot",
            "Buyouts are missing in both finance_final_daily and cabinet_commerce_daily.",
            block="cabinet_commerce",
        )
    )
    return (None, None, "missing", "missing")


def _build_live_metric(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(block.get("available", False)),
        "source": _safe_str(block.get("source")) or "missing",
        "target_date": _safe_str(block.get("target_date")) or None,
        "count": _safe_int(block.get("count")),
        "amount": _safe_float(block.get("amount")),
        "total_units": _safe_int(block.get("total_units")),
        "snapshot_date": _safe_str(block.get("snapshot_date")) or None,
        "snapshot_kind": _safe_str(block.get("snapshot_kind")) or None,
        "operational_date_reference": _safe_str(block.get("operational_date_reference")) or None,
    }


def build_report_payload_v2(snapshot: dict[str, Any], debug: dict[str, Any] | None = None) -> ReportPayloadV2:
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    if debug is not None and not isinstance(debug, dict):
        raise TypeError("debug must be a dict or None")

    debug_payload = _safe_dict(debug)
    warnings: list[WarningItemV2] = _normalize_debug_warnings(debug_payload.get("warnings"))

    seller_id = _safe_str(snapshot.get("seller_id"))
    report_date = _safe_str(snapshot.get("run_date"))
    operational_date = _safe_str(snapshot.get("operational_date"))
    snapshot_source_mode = _safe_str(snapshot.get("source_mode")) or "unknown"

    cabinet_daily = _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance_daily = _safe_dict(snapshot.get("finance_final_daily"))
    live_daily = _safe_dict(snapshot.get("live_operational"))

    if not cabinet_daily:
        warnings.append(
            _warning(
                "cabinet_commerce_missing",
                "cabinet_commerce_daily block is missing in snapshot.",
                block="cabinet_commerce",
            )
        )
    elif not bool(cabinet_daily.get("available", False)):
        warnings.append(
            _warning(
                "cabinet_commerce_unavailable",
                "cabinet_commerce_daily is present but marked unavailable.",
                block="cabinet_commerce",
            )
        )

    if not finance_daily:
        warnings.append(
            _warning(
                "finance_final_missing",
                "finance_final_daily block is missing in snapshot.",
                block="finance_final",
            )
        )
    elif not bool(finance_daily.get("available", False)):
        warnings.append(
            _warning(
                "finance_final_unavailable",
                "finance_final_daily is present but marked unavailable.",
                block="finance_final",
            )
        )
    elif finance_daily.get("date_aligned") is False:
        warnings.append(
            _warning(
                "finance_final_lagged",
                "finance_final_daily actual_date differs from operational_date.",
                block="finance_final",
            )
        )

    live_orders = _safe_dict(live_daily.get("orders"))
    live_sales = _safe_dict(live_daily.get("sales"))
    live_stocks = _safe_dict(live_daily.get("stocks"))
    if not live_daily:
        warnings.append(
            _warning(
                "live_operational_missing",
                "live_operational block is missing in snapshot.",
                block="live_operational",
            )
        )
    else:
        if not live_orders:
            warnings.append(_warning("live_orders_missing", "live_operational.orders is missing.", block="live_operational"))
        if not live_sales:
            warnings.append(_warning("live_sales_missing", "live_operational.sales is missing.", block="live_operational"))
        if not live_stocks:
            warnings.append(_warning("live_stocks_missing", "live_operational.stocks is missing.", block="live_operational"))

    buyouts_count, buyouts_amount, buyouts_owner, buyouts_source = _resolve_buyouts_owner(
        cabinet_daily=cabinet_daily,
        finance_daily=finance_daily,
        warnings=warnings,
    )

    live_availability_flags = [
        bool(live_orders.get("available", False)),
        bool(live_sales.get("available", False)),
        bool(live_stocks.get("available", False)),
    ]
    if all(live_availability_flags) and live_availability_flags:
        live_status = "ok"
    elif any(live_availability_flags):
        live_status = "partial"
    else:
        live_status = "unavailable"

    payload: ReportPayloadV2 = {
        "meta": {
            "contract_version": "report_payload_v2",
            "seller_id": seller_id,
            "report_date": report_date,
            "operational_date": operational_date,
            "snapshot_source_mode": snapshot_source_mode,
            "debug_available": debug is not None,
        },
        "cabinet_commerce": {
            "available": bool(cabinet_daily.get("available", False)) and bool(cabinet_daily),
            "source": _safe_str(cabinet_daily.get("source")) or "missing",
            "owner_block": "cabinet_commerce_daily",
            "target_date": _safe_str(cabinet_daily.get("target_date")) or None,
            "orders_count": _safe_int(cabinet_daily.get("orders_count")),
            "orders_amount": _safe_float(cabinet_daily.get("orders_amount")),
            "buyouts_count": buyouts_count,
            "buyouts_amount": buyouts_amount,
        },
        "finance_final": {
            "available": bool(finance_daily.get("available", False)) and bool(finance_daily),
            "source": _safe_str(finance_daily.get("source")) or "missing",
            "owner_block": "finance_final_daily",
            "status": (
                "unavailable"
                if not bool(finance_daily.get("available", False))
                else ("lagged" if finance_daily.get("date_aligned") is False else "ok")
            ),
            "target_date": _safe_str(finance_daily.get("target_date")) or None,
            "actual_date": _safe_str(finance_daily.get("actual_date")) or None,
            "date_aligned": finance_daily.get("date_aligned") if "date_aligned" in finance_daily else None,
            "gross_revenue": _safe_float(finance_daily.get("gross_revenue")),
            "seller_payout": _safe_float(finance_daily.get("seller_payout")),
            "wb_commission": _safe_float(finance_daily.get("wb_commission")),
            "logistics": _safe_float(finance_daily.get("logistics")),
            "storage": _safe_float(finance_daily.get("storage")),
            "acquiring": _safe_float(finance_daily.get("acquiring")),
            "penalties": _safe_float(finance_daily.get("penalties")),
            "deductions": _safe_float(finance_daily.get("deductions")),
            "tax": _safe_float(finance_daily.get("tax")),
        },
        "live_operational": {
            "status": live_status,
            "orders": _build_live_metric(live_orders),
            "sales": _build_live_metric(live_sales),
            "stocks": _build_live_metric(live_stocks),
        },
        "warnings": warnings,
        "source_flags": {
            "snapshot_present": True,
            "debug_present": debug is not None,
            "snapshot_source_mode": snapshot_source_mode,
            "buyouts_owner": buyouts_owner,
            "buyouts_source": buyouts_source,
            "warnings_count": len(warnings),
        },
    }

    if debug_payload:
        endpoints = debug_payload.get("endpoints")
        payload["debug_summary"] = {
            "endpoints_present": sorted(endpoints.keys()) if isinstance(endpoints, dict) else [],
            "warnings_count": len(_normalize_debug_warnings(debug_payload.get("warnings"))),
        }

    return payload
