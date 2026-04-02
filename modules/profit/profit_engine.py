"""Profit calculations by SKU (MVP layer)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COMMISSION_PCT = 0.15
LOGISTICS_PCT = 0.05

DELAYED_FINANCE_MESSAGE = (
    "Прибыль предварительная, фин данные WB не подтверждены"
)


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _norm_sku(value: Any) -> str:
    return str(value or "").strip()


def _pick_value(row: dict[str, Any], keys: tuple[str, ...], default: Any = 0) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return default


def _iter_sku_rows_from_facts(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the best available per-SKU basis from facts."""
    sku_rows: list[dict[str, Any]] = []

    # Primary source: sku_performance.rows (already normalized in v2 facts).
    perf_rows = ((facts.get("sku_performance") or {}).get("rows") or [])
    if isinstance(perf_rows, list):
        for row in perf_rows:
            if not isinstance(row, dict):
                continue
            sku = _pick_value(row, ("sku", "wb_sku", "nmId", "nm_id"), "")
            seller_sku = _pick_value(
                row,
                ("seller_sku", "supplier_sku", "supplierSku", "vendor_code", "vendorCode"),
                "",
            )
            sku_rows.append(
                {
                    "sku": _norm_sku(sku),
                    "seller_sku": _norm_sku(seller_sku),
                    "revenue_total": _to_float(
                        _pick_value(row, ("revenue_total", "revenue", "net_revenue", "sales_revenue"), 0)
                    ),
                    "orders_count": _to_int(_pick_value(row, ("orders_count", "orders"), 0)),
                    "ad_spend": _to_float(_pick_value(row, ("ad_spend", "spend"), 0)),
                    "ad_revenue": _to_float(
                        _pick_value(
                            row,
                            ("ad_revenue", "ad_revenue_attr", "ad_attributed_revenue", "revenue_attr"),
                            0,
                        )
                    ),
                }
            )
        if sku_rows:
            return sku_rows

    # Fallback source: financial_summary.sku_financials
    fin_rows = ((facts.get("financial_summary") or {}).get("sku_financials") or {})
    if isinstance(fin_rows, dict):
        for sku, row in fin_rows.items():
            if not isinstance(row, dict):
                continue
            seller_sku = _pick_value(
                row,
                ("seller_sku", "supplier_sku", "supplierSku", "vendor_code", "vendorCode"),
                "",
            )
            sku_rows.append(
                {
                    "sku": _norm_sku(sku),
                    "seller_sku": _norm_sku(seller_sku),
                    "revenue_total": _to_float(
                        _pick_value(row, ("revenue_total", "net_revenue", "sales_revenue", "gross_revenue"), 0)
                    ),
                    "orders_count": _to_int(_pick_value(row, ("orders_count", "sales_qty"), 0)),
                    "ad_spend": 0.0,
                    "ad_revenue": 0.0,
                }
            )

    return sku_rows


def build_sku_profit(
    *,
    facts: dict[str, Any],
    cogs_by_seller_sku: dict[str, float],
) -> dict[str, Any]:
    """Build final sku_profit payload."""
    rows = _iter_sku_rows_from_facts(facts if isinstance(facts, dict) else {})
    finance_status = str((facts or {}).get("finance_status") or "missing")
    report_date = str((facts or {}).get("report_date") or (facts or {}).get("date") or "")
    warnings: list[str] = []

    profit_status = "final" if finance_status == "ok" else "preliminary"
    finance_message = DELAYED_FINANCE_MESSAGE if finance_status == "delayed" else ""

    items: list[dict[str, Any]] = []
    for row in rows:
        sku = _norm_sku(row.get("sku"))
        seller_sku = _norm_sku(row.get("seller_sku"))
        revenue_total = round(_to_float(row.get("revenue_total")), 2)
        orders_count = _to_int(row.get("orders_count"))
        units_sold = orders_count  # MVP rule
        ad_spend = round(_to_float(row.get("ad_spend")), 2)
        ad_revenue = round(_to_float(row.get("ad_revenue")), 2)

        cogs_unit = cogs_by_seller_sku.get(seller_sku.lower()) if seller_sku else None
        cogs_total = round((float(cogs_unit) * units_sold), 2) if cogs_unit is not None else 0.0
        if cogs_unit is None:
            warnings.append(
                f"COGS not found for seller_sku='{seller_sku or '<empty>'}' (sku='{sku or '<empty>'}')"
            )

        commission = round(revenue_total * COMMISSION_PCT, 2)
        logistics = round(revenue_total * LOGISTICS_PCT, 2)
        profit = round(revenue_total - cogs_total - commission - logistics, 2)
        margin_pct = round((profit / revenue_total) * 100.0, 2) if revenue_total > 0 else None

        drr_ads = round((ad_spend / ad_revenue) * 100.0, 2) if ad_revenue > 0 else None
        drr_total = round((ad_spend / revenue_total) * 100.0, 2) if revenue_total > 0 else None

        items.append(
            {
                "sku": sku,
                "seller_sku": seller_sku,
                "revenue_total": revenue_total,
                "orders_count": orders_count,
                "units_sold": units_sold,
                "cogs_unit": round(float(cogs_unit), 2) if cogs_unit is not None else None,
                "cogs_total": cogs_total,
                "commission": commission,
                "logistics": logistics,
                "profit": profit,
                "margin_pct": margin_pct,
                "ad_spend": ad_spend,
                "ad_revenue": ad_revenue,
                "drr_ads": drr_ads,
                "drr_total": drr_total,
                "is_profitable": bool(profit > 0),
            }
        )

    # De-duplicate warnings while preserving order.
    dedup_warnings: list[str] = []
    seen = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        dedup_warnings.append(warning)

    return {
        "status": "ok",
        "report_date": report_date,
        "finance_status": finance_status,
        "finance_message": finance_message,
        "profit_status": profit_status,
        "items": items,
        "warnings": dedup_warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "profit_module",
    }

