"""Financial aggregation helpers for WB finance rows.

This module keeps v5 architecture intact and restores v2-like financial logic:
- parse and classify WB operations
- aggregate full finance basis (not sales-only)
- calculate profit from a consistent base
- expose partial/final status with diagnostics
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..domain import RawMarginsData, RawOrdersData

try:
    from src.cogs import calc_cogs_for_rows as _legacy_calc_cogs_for_rows
except Exception:  # pragma: no cover - fallback path
    _legacy_calc_cogs_for_rows = None


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if abs(float(b or 0.0)) > 1e-12 else 0.0


def _classify_operation(operation_text: str) -> List[str]:
    text = _safe_str(operation_text).lower()
    classes: List[str] = []

    is_sale = ("продаж" in text) and ("возврат" not in text)
    is_return = ("возврат" in text) or ("return" in text)
    is_logistics = (
        ("логист" in text)
        or ("доставк" in text)
        or ("перевозк" in text)
        or ("пвз" in text)
    )
    is_storage = "хран" in text
    is_penalty = ("штраф" in text) or ("penalty" in text) or ("fine" in text)
    is_deduction = ("удерж" in text) or ("deduction" in text) or ("withhold" in text)
    is_loyalty = ("лояль" in text) or ("балл" in text) or ("софинанс" in text)
    is_acquiring = ("эквайр" in text) or ("платеж" in text) or ("платёж" in text)
    is_compensation = ("компенсац" in text) or ("возмещен" in text) or ("возмещение" in text)

    if is_sale:
        classes.append("sale")
    if is_return:
        classes.append("return")
    if is_logistics:
        classes.append("logistics")
    if is_storage:
        classes.append("storage")
    if is_penalty:
        classes.append("penalty")
    if is_deduction:
        classes.append("deduction")
    if is_loyalty:
        classes.append("loyalty")
    if is_acquiring:
        classes.append("acquiring")
    if is_compensation:
        classes.append("compensation")
    if not classes:
        classes.append("other")
    return classes


def _component_available(value: float, source_rows: int) -> bool:
    return abs(float(value or 0.0)) > 1e-9 or int(source_rows or 0) > 0


def aggregate_financial_summary(
    orders: List[RawOrdersData],
    margins: List[RawMarginsData] | None = None,
    tax_rate: float = 0.06,
    loader_debug: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    margins = margins or []
    loader_debug = loader_debug or {}

    rows_count = int(len(orders))
    rows_read = int(loader_debug.get("rows_total", rows_count) or rows_count)
    rows_dropped = int(loader_debug.get("rows_dropped", 0) or 0)
    dropped_reasons = dict(loader_debug.get("dropped_reasons") or {})

    sales_qty = 0
    returns_qty = 0

    gross_revenue = 0.0
    revenue_buyouts = 0.0
    payout = 0.0

    commission = 0.0
    logistics = 0.0
    storage = 0.0
    penalties = 0.0
    deductions = 0.0
    loyalty_program = 0.0
    loyalty_points_withheld = 0.0
    acquiring = 0.0
    pvz_service = 0.0
    other_adjustments = 0.0

    component_nonzero_rows: Dict[str, int] = {
        "gross_revenue": 0,
        "realized_revenue": 0,
        "seller_payout": 0,
        "commission": 0,
        "logistics": 0,
        "storage": 0,
        "penalties": 0,
        "deductions": 0,
        "loyalty_program": 0,
        "loyalty_points_withheld": 0,
        "acquiring": 0,
        "pvz_service": 0,
        "other_adjustments": 0,
    }
    operation_classification: Dict[str, int] = {}
    operation_basis_detected: Dict[str, int] = {}

    sku_map: Dict[str, Dict[str, float]] = {}
    row_debug: List[Dict[str, Any]] = []

    def _sku_payload(sku_id: str) -> Dict[str, float]:
        if sku_id not in sku_map:
            sku_map[sku_id] = {
                "sales_qty": 0.0,
                "returns_qty": 0.0,
                "gross_revenue": 0.0,
                "revenue_buyouts": 0.0,
                "payout": 0.0,
                "commission": 0.0,
                "logistics": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "deductions": 0.0,
                "loyalty_program": 0.0,
                "loyalty_points_withheld": 0.0,
                "acquiring": 0.0,
                "pvz_service": 0.0,
                "other_adjustments": 0.0,
            }
        return sku_map[sku_id]

    for item in orders:
        sku = _safe_str(item.sku_id)
        qty = _safe_int(item.quantity)

        operation_basis = _safe_str(item.operation_basis)
        operation_type = _safe_str(item.operation_type or item.document_type)
        operation_text = " ".join([x for x in [operation_type, operation_basis] if x]).strip()
        classes = _classify_operation(operation_text)
        for cls in classes:
            operation_classification[cls] = int(operation_classification.get(cls, 0) or 0) + 1
        if operation_basis:
            operation_basis_detected[operation_basis] = int(operation_basis_detected.get(operation_basis, 0) or 0) + 1

        gross_component = _safe_float(item.gross_revenue)
        realized_component = _safe_float(item.realized_revenue)
        payout_component = _safe_float(item.seller_payout if abs(_safe_float(item.seller_payout)) > 1e-9 else item.revenue)
        commission_component = abs(_safe_float(item.commission))
        logistics_component = abs(_safe_float(item.logistics)) + abs(_safe_float(item.rebill_logistic_cost))
        storage_component = abs(_safe_float(item.storage))
        penalties_component = abs(_safe_float(item.penalties))
        deductions_component = abs(_safe_float(item.deductions))
        loyalty_program_component = abs(_safe_float(item.loyalty_program))
        loyalty_points_component = abs(_safe_float(item.loyalty_points_withheld))
        acquiring_component = abs(_safe_float(item.acquiring))
        pvz_component = abs(_safe_float(item.pvz_service))
        other_component = abs(_safe_float(item.other_adjustments))

        if abs(gross_component) > 1e-9:
            component_nonzero_rows["gross_revenue"] += 1
        if abs(realized_component) > 1e-9:
            component_nonzero_rows["realized_revenue"] += 1
        if abs(payout_component) > 1e-9:
            component_nonzero_rows["seller_payout"] += 1
        if commission_component > 1e-9:
            component_nonzero_rows["commission"] += 1
        if logistics_component > 1e-9:
            component_nonzero_rows["logistics"] += 1
        if storage_component > 1e-9:
            component_nonzero_rows["storage"] += 1
        if penalties_component > 1e-9:
            component_nonzero_rows["penalties"] += 1
        if deductions_component > 1e-9:
            component_nonzero_rows["deductions"] += 1
        if loyalty_program_component > 1e-9:
            component_nonzero_rows["loyalty_program"] += 1
        if loyalty_points_component > 1e-9:
            component_nonzero_rows["loyalty_points_withheld"] += 1
        if acquiring_component > 1e-9:
            component_nonzero_rows["acquiring"] += 1
        if pvz_component > 1e-9:
            component_nonzero_rows["pvz_service"] += 1
        if other_component > 1e-9:
            component_nonzero_rows["other_adjustments"] += 1

        # v2-like logic: gross revenue is recognized from sales rows only.
        is_sale = "sale" in classes
        is_return = "return" in classes

        if is_sale:
            if qty > 0:
                sales_qty += qty
            # Keep v2-compatible preference: realized row amount first, then retail gross.
            sale_gross = realized_component if abs(realized_component) > 1e-9 else gross_component
            if abs(sale_gross) <= 1e-9:
                sale_gross = payout_component
            gross_revenue += sale_gross
            revenue_buyouts += realized_component if abs(realized_component) > 1e-9 else payout_component
        elif is_return:
            if qty != 0:
                returns_qty += abs(qty)
            ret_base = realized_component if abs(realized_component) > 1e-9 else payout_component
            revenue_buyouts -= abs(ret_base)

        payout += payout_component
        commission += commission_component
        logistics += logistics_component
        storage += storage_component
        penalties += penalties_component
        deductions += deductions_component
        loyalty_program += loyalty_program_component
        loyalty_points_withheld += loyalty_points_component
        acquiring += acquiring_component
        pvz_service += pvz_component
        other_adjustments += other_component

        if sku:
            sku_payload = _sku_payload(sku)
            if is_sale and qty > 0:
                sku_payload["sales_qty"] += float(qty)
            if is_return and qty != 0:
                sku_payload["returns_qty"] += float(abs(qty))
            if is_sale:
                sku_payload["gross_revenue"] += float(
                    realized_component
                    if abs(realized_component) > 1e-9
                    else (gross_component if abs(gross_component) > 1e-9 else payout_component)
                )
                sku_payload["revenue_buyouts"] += float(
                    realized_component if abs(realized_component) > 1e-9 else payout_component
                )
            elif is_return:
                sku_payload["revenue_buyouts"] -= float(abs(
                    realized_component if abs(realized_component) > 1e-9 else payout_component
                ))
            sku_payload["payout"] += float(payout_component)
            sku_payload["commission"] += float(commission_component)
            sku_payload["logistics"] += float(logistics_component)
            sku_payload["storage"] += float(storage_component)
            sku_payload["penalties"] += float(penalties_component)
            sku_payload["deductions"] += float(deductions_component)
            sku_payload["loyalty_program"] += float(loyalty_program_component)
            sku_payload["loyalty_points_withheld"] += float(loyalty_points_component)
            sku_payload["acquiring"] += float(acquiring_component)
            sku_payload["pvz_service"] += float(pvz_component)
            sku_payload["other_adjustments"] += float(other_component)

        row_debug.append(
            {
                "raw_row_index": int(getattr(item, "raw_row_index", -1) or -1),
                "source_file": _safe_str(getattr(item, "source_file", "")),
                "sku": sku or None,
                "operation_basis": operation_basis,
                "operation_type": operation_type,
                "operation_classes": list(classes),
                "gross_revenue_component": round(gross_component, 2),
                "realized_revenue_component": round(realized_component, 2),
                "seller_payout_component": round(payout_component, 2),
                "commission_component": round(commission_component, 2),
                "logistics_component": round(logistics_component, 2),
                "storage_component": round(storage_component, 2),
                "penalties_component": round(penalties_component, 2),
                "deductions_component": round(deductions_component, 2),
                "loyalty_program_component": round(loyalty_program_component, 2),
                "loyalty_points_withheld_component": round(loyalty_points_component, 2),
                "acquiring_component": round(acquiring_component, 2),
                "pvz_service_component": round(pvz_component, 2),
                "other_adjustments_component": round(other_component, 2),
                "excluded": bool(getattr(item, "excluded_reason", "")),
                "excluded_reason": _safe_str(getattr(item, "excluded_reason", "")) or None,
            }
        )

    cost_by_sku: Dict[str, float] = {}
    for margin in margins:
        sku = _safe_str(margin.sku_id)
        if not sku:
            continue
        cp = _safe_float(margin.cost_price)
        if cp > 0:
            cost_by_sku[sku] = cp

    cogs_total = 0.0
    cogs_by_sku: Dict[str, float] = {}
    missing_cogs_sku: Dict[str, float] = {}
    for sku, payload in sku_map.items():
        sales_qty_sku = _safe_float(payload.get("sales_qty", 0.0))
        cp = _safe_float(cost_by_sku.get(sku))
        if sales_qty_sku > 0 and cp > 0:
            sku_cogs = sales_qty_sku * cp
            cogs_by_sku[sku] = sku_cogs
            cogs_total += sku_cogs
        elif sales_qty_sku > 0:
            missing_cogs_sku[sku] = sales_qty_sku

    if cogs_total <= 1e-9 and callable(_legacy_calc_cogs_for_rows):
        qty_by_sku_numeric: Dict[int, int] = {}
        for sku, payload in sku_map.items():
            if not str(sku).isdigit():
                continue
            qty = int(round(_safe_float(payload.get("sales_qty", 0.0))))
            if qty > 0:
                qty_by_sku_numeric[int(sku)] = qty
        if qty_by_sku_numeric:
            legacy_total, legacy_by_sku, legacy_missing = _legacy_calc_cogs_for_rows(qty_by_sku_numeric)
            cogs_total = _safe_float(legacy_total)
            cogs_by_sku = {str(k): _safe_float(v) for k, v in dict(legacy_by_sku or {}).items()}
            missing_cogs_sku = {str(k): _safe_float(v) for k, v in dict(legacy_missing or {}).items()}

    tax = gross_revenue * float(tax_rate or 0.0)
    profit = (
        gross_revenue
        - commission
        - acquiring
        - pvz_service
        - logistics
        - storage
        - penalties
        - deductions
        - loyalty_program
        - loyalty_points_withheld
        - other_adjustments
        - tax
        - cogs_total
    )
    margin = _safe_div(profit, gross_revenue)

    sku_financials: Dict[str, Dict[str, Any]] = {}
    total_sku_gross = sum(_safe_float(payload.get("gross_revenue")) for payload in sku_map.values())
    for sku, payload in sku_map.items():
        sku_gross = _safe_float(payload.get("gross_revenue"))
        sku_tax = tax * (sku_gross / total_sku_gross) if total_sku_gross > 0 else 0.0
        sku_cogs = _safe_float(cogs_by_sku.get(sku, 0.0))
        sku_profit = (
            sku_gross
            - _safe_float(payload.get("commission"))
            - _safe_float(payload.get("acquiring"))
            - _safe_float(payload.get("pvz_service"))
            - _safe_float(payload.get("logistics"))
            - _safe_float(payload.get("storage"))
            - _safe_float(payload.get("penalties"))
            - _safe_float(payload.get("deductions"))
            - _safe_float(payload.get("loyalty_program"))
            - _safe_float(payload.get("loyalty_points_withheld"))
            - _safe_float(payload.get("other_adjustments"))
            - sku_tax
            - sku_cogs
        )
        sku_margin = _safe_div(sku_profit, sku_gross)
        sku_financials[sku] = {
            "sales_qty": int(round(_safe_float(payload.get("sales_qty")))),
            "returns_qty": int(round(_safe_float(payload.get("returns_qty")))),
            "gross_revenue": round(sku_gross, 2),
            "revenue_buyouts": round(_safe_float(payload.get("revenue_buyouts")), 2),
            "payout": round(_safe_float(payload.get("payout")), 2),
            "commission": round(_safe_float(payload.get("commission")), 2),
            "acquiring": round(_safe_float(payload.get("acquiring")), 2),
            "pvz_service": round(_safe_float(payload.get("pvz_service")), 2),
            "logistics": round(_safe_float(payload.get("logistics")), 2),
            "storage": round(_safe_float(payload.get("storage")), 2),
            "penalties": round(_safe_float(payload.get("penalties")), 2),
            "deductions": round(_safe_float(payload.get("deductions")), 2),
            "loyalty_program": round(_safe_float(payload.get("loyalty_program")), 2),
            "loyalty_points_withheld": round(_safe_float(payload.get("loyalty_points_withheld")), 2),
            "other_adjustments": round(_safe_float(payload.get("other_adjustments")), 2),
            "tax_alloc": round(sku_tax, 2),
            "cogs": round(sku_cogs, 2),
            "profit": round(sku_profit, 2),
            "margin": round(sku_margin, 4),
        }

    component_matrix = {
        "gross_revenue": (gross_revenue, component_nonzero_rows["gross_revenue"]),
        "revenue_buyouts": (revenue_buyouts, component_nonzero_rows["realized_revenue"]),
        "seller_payout": (payout, component_nonzero_rows["seller_payout"]),
        "commission": (commission, component_nonzero_rows["commission"]),
        "acquiring": (acquiring, component_nonzero_rows["acquiring"]),
        "pvz_service": (pvz_service, component_nonzero_rows["pvz_service"]),
        "logistics": (logistics, component_nonzero_rows["logistics"]),
        "storage": (storage, component_nonzero_rows["storage"]),
        "penalties": (penalties, component_nonzero_rows["penalties"]),
        "deductions": (deductions, component_nonzero_rows["deductions"]),
        "loyalty_program": (loyalty_program, component_nonzero_rows["loyalty_program"]),
        "loyalty_points_withheld": (
            loyalty_points_withheld,
            component_nonzero_rows["loyalty_points_withheld"],
        ),
        "other_adjustments": (other_adjustments, component_nonzero_rows["other_adjustments"]),
        "tax": (tax, 1 if abs(gross_revenue) > 1e-9 else 0),
        "cogs_total": (cogs_total, len(cogs_by_sku)),
    }
    components = {}
    available_components = 0
    for name, (value, source_rows) in component_matrix.items():
        available = _component_available(value, source_rows)
        if available:
            available_components += 1
        components[name] = {
            "available": bool(available),
            "source_rows": int(source_rows),
            "value": round(float(value), 2),
        }

    total_components = len(component_matrix)
    completeness_pct = round(_safe_div(float(available_components), float(total_components)) * 100.0, 2)

    if rows_count <= 0:
        financial_finality_status = "unavailable"
    elif rows_dropped > 0 or completeness_pct < 95.0:
        financial_finality_status = "partial"
    else:
        financial_finality_status = "final"

    financial_partial = bool(financial_finality_status != "final")
    financial_status = "ok" if financial_finality_status == "final" else "partial"

    financial_debug = {
        "rows_read": rows_read,
        "rows_loaded": rows_count,
        "rows_dropped": rows_dropped,
        "dropped_reasons": dropped_reasons,
        "operation_basis_detected": operation_basis_detected,
        "operation_classification_counts": operation_classification,
        "component_nonzero_rows": component_nonzero_rows,
        "row_debug": row_debug,
    }

    diagnostics = {
        "rows_read": rows_read,
        "rows_loaded": rows_count,
        "rows_dropped": rows_dropped,
        "dropped_reasons": dropped_reasons,
        "operation_basis_detected_count": len(operation_basis_detected),
        "available_components": available_components,
        "total_components": total_components,
        "completeness_pct": completeness_pct,
        "financial_finality_status": financial_finality_status,
    }

    return {
        "rows_count": rows_count,
        "rows_read": rows_read,
        "rows_dropped": rows_dropped,
        "sales_qty": int(sales_qty),
        "returns_qty": int(returns_qty),
        "gross_revenue": round(gross_revenue, 2),
        "revenue_buyouts": round(revenue_buyouts, 2),
        "realized_revenue": round(revenue_buyouts, 2),
        "payout": round(payout, 2),
        "seller_payout": round(payout, 2),
        "commission": round(commission, 2),
        "acquiring": round(acquiring, 2),
        "pvz_service": round(pvz_service, 2),
        "logistics": round(logistics, 2),
        "storage": round(storage, 2),
        "penalties": round(penalties, 2),
        "deductions": round(deductions, 2),
        "loyalty_program": round(loyalty_program, 2),
        "loyalty_points_withheld": round(loyalty_points_withheld, 2),
        "other_adjustments": round(other_adjustments, 2),
        "tax_rate": float(tax_rate),
        "tax": round(tax, 2),
        "cogs_total": round(cogs_total, 2),
        "profit": round(profit, 2),
        "margin": round(margin, 4),
        "revenue_basis": "gross_revenue_v2",
        "completeness_pct": completeness_pct,
        "available_components": available_components,
        "total_components": total_components,
        "components": components,
        "financial_finality_status": financial_finality_status,
        "is_partial": financial_partial,
        "financial_status": financial_status,
        "financial_partial": financial_partial,
        "confirmed": bool(financial_finality_status == "final"),
        "cogs_by_sku": {k: round(v, 2) for k, v in cogs_by_sku.items()},
        "missing_cogs_sku": {k: round(v, 2) for k, v in missing_cogs_sku.items()},
        "sku_financials": sku_financials,
        "net_profit_formula": {
            "revenue_basis": round(gross_revenue, 2),
            "commission": round(commission, 2),
            "acquiring": round(acquiring, 2),
            "pvz_service": round(pvz_service, 2),
            "logistics": round(logistics, 2),
            "storage": round(storage, 2),
            "penalties": round(penalties, 2),
            "deductions": round(deductions, 2),
            "loyalty_program": round(loyalty_program, 2),
            "loyalty_points_withheld": round(loyalty_points_withheld, 2),
            "other_adjustments": round(other_adjustments, 2),
            "tax": round(tax, 2),
            "cogs_total": round(cogs_total, 2),
            "profit": round(profit, 2),
        },
        "debug": financial_debug,
        "diagnostics": diagnostics,
    }
