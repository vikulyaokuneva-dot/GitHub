"""Deterministic estimation of money impact from poor localization."""

from __future__ import annotations

from typing import Any

from audit.logistics_model import (
    calculate_base_logistics,
    localization_indices_by_share,
    tariff_per_liter_for_volume,
)


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(" ", "").replace(",", ".")
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _norm_mode(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"full_rub", "partial_rub", "score_only", "insufficient_data"}:
        return text
    return "insufficient_data"


def _risk_label_from_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 25.0:
        return "low"
    if score < 50.0:
        return "medium"
    if score < 75.0:
        return "high"
    return "critical"


def estimate_loss_per_order(
    *,
    volume_liters: float | None,
    item_price: float | None,
    warehouse_coef: float = 1.0,
    localization_share_pct: float | None,
) -> dict[str, Any]:
    volume = _to_float_or_none(volume_liters)
    price = _to_float_or_none(item_price)
    coef = _to_float_or_none(warehouse_coef) or 1.0
    if coef > 10.0:
        coef = coef / 100.0

    localization_share = _to_float_or_none(localization_share_pct)
    localization_index, sales_distribution_index_pct = localization_indices_by_share(localization_share)

    missing_inputs: list[str] = []
    if volume is None or volume <= 0:
        missing_inputs.append("volume_liters")
    if price is None or price <= 0:
        missing_inputs.append("item_price")
    if localization_share is None:
        missing_inputs.append("localization_share_pct")

    current_delivery_cost = None
    baseline_delivery_cost = None
    loss_per_order_rub = None
    raw_delta_rub = None

    if volume is not None and volume > 0 and price is not None and price > 0 and localization_index is not None:
        tariff = tariff_per_liter_for_volume(volume)
        current_base = calculate_base_logistics(
            volume_liters=volume,
            warehouse_coef=coef,
            localization_index=localization_index,
            tariff_per_liter=tariff,
        )
        baseline_base = calculate_base_logistics(
            volume_liters=volume,
            warehouse_coef=coef,
            localization_index=1.0,
            tariff_per_liter=tariff,
        )
        current_distribution = price * ((sales_distribution_index_pct or 0.0) / 100.0)
        baseline_distribution = 0.0
        if current_base is not None and baseline_base is not None:
            current_delivery_cost = float(current_base + current_distribution)
            baseline_delivery_cost = float(baseline_base + baseline_distribution)
            raw_delta_rub = float(current_delivery_cost - baseline_delivery_cost)
            loss_per_order_rub = float(max(raw_delta_rub, 0.0))

    status = "ok" if loss_per_order_rub is not None else "partial"
    return {
        "status": status,
        "missing_inputs": missing_inputs,
        "volume_liters": round(volume, 4) if volume is not None else None,
        "item_price": round(price, 2) if price is not None else None,
        "warehouse_coef": round(coef, 4),
        "localization_share_pct": round(localization_share, 2) if localization_share is not None else None,
        "localization_index": round(localization_index, 4) if localization_index is not None else None,
        "sales_distribution_index_pct": round(sales_distribution_index_pct, 4) if sales_distribution_index_pct is not None else None,
        "current_delivery_cost": round(current_delivery_cost, 2) if current_delivery_cost is not None else None,
        "baseline_delivery_cost": round(baseline_delivery_cost, 2) if baseline_delivery_cost is not None else None,
        "raw_delta_rub": round(raw_delta_rub, 2) if raw_delta_rub is not None else None,
        "loss_per_order_rub": round(loss_per_order_rub, 2) if loss_per_order_rub is not None else None,
    }


def estimate_total_localization_loss_for_sku(
    *,
    sku: Any,
    orders_count: Any,
    localization_share_pct: float | None,
    volume_liters: float | None = None,
    item_price: float | None = None,
    warehouse_coef: float = 1.0,
    avg_price_fallback: float | None = None,
) -> dict[str, Any]:
    sku_id = _to_int(sku)
    orders = max(_to_int(orders_count), 0)
    share = _to_float_or_none(localization_share_pct)
    volume = _to_float_or_none(volume_liters)
    price = _to_float_or_none(item_price)
    fallback_price = _to_float_or_none(avg_price_fallback)

    if orders <= 0:
        il, irp = localization_indices_by_share(share)
        return {
            "sku": sku_id,
            "orders": 0,
            "mode": "insufficient_data",
            "localization_share_pct": round(share, 2) if share is not None else None,
            "localization_index": il,
            "sales_distribution_index_pct": irp,
            "loss_per_order_rub": None,
            "total_loss_rub": None,
            "risk_score": None,
            "risk_level": "unknown",
            "missing_inputs": ["orders_count"],
            "conclusion": "Заказы отсутствуют, денежные потери по SKU за период не формируются.",
        }

    rub_mode = "full_rub"
    price_for_calc = price
    missing_inputs: list[str] = []
    if price_for_calc is None and fallback_price is not None:
        price_for_calc = fallback_price
        rub_mode = "partial_rub"
        missing_inputs.append("item_price")
    if price_for_calc is None:
        rub_mode = "score_only"
        missing_inputs.append("item_price")
    if volume is None or volume <= 0:
        rub_mode = "score_only"
        missing_inputs.append("volume_liters")
    if share is None:
        missing_inputs.append("localization_share_pct")

    il, irp = localization_indices_by_share(share)
    score_price = price_for_calc if price_for_calc is not None else fallback_price
    price_weight = _clamp((float(score_price or 0.0) / 5000.0), 0.0, 1.0)
    orders_weight = _clamp((float(orders) / 100.0), 0.0, 1.0)
    il_penalty = max((float(il or 1.0) - 1.0), 0.0)
    irp_penalty = _clamp(float(irp or 0.0) / 2.5, 0.0, 1.0)
    raw_score = (il_penalty * 45.0) + (irp_penalty * 35.0) + (orders_weight * 15.0) + (price_weight * 5.0)
    risk_score = round(_clamp(raw_score, 0.0, 100.0), 1)
    risk_level = _risk_label_from_score(risk_score)

    if _norm_mode(rub_mode) in {"full_rub", "partial_rub"}:
        loss = estimate_loss_per_order(
            volume_liters=volume,
            item_price=price_for_calc,
            warehouse_coef=warehouse_coef,
            localization_share_pct=share,
        )
        loss_per_order = _to_float_or_none(loss.get("loss_per_order_rub"))
        if loss_per_order is None:
            rub_mode = "score_only"
        else:
            total_loss = max(loss_per_order, 0.0) * float(orders)
            conclusion = (
                "Потери по SKU близки к нулю при текущей локализации."
                if total_loss <= 0
                else "SKU формирует ощутимые потери из-за невыгодной локализации."
            )
            return {
                "sku": sku_id,
                "orders": orders,
                "mode": _norm_mode(rub_mode),
                "localization_share_pct": round(share, 2) if share is not None else None,
                "localization_index": round(float(il), 4) if il is not None else None,
                "sales_distribution_index_pct": round(float(irp), 4) if irp is not None else None,
                "loss_per_order_rub": round(float(loss_per_order), 2),
                "total_loss_rub": round(total_loss, 2),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "missing_inputs": sorted(set(missing_inputs + (loss.get("missing_inputs") or []))),
                "conclusion": conclusion,
            }

    if share is None:
        risk_level = "unknown"
    conclusion = "Точная рублевая оценка недоступна; использован риск-скор по ИЛ/ИРП и объему заказов."
    return {
        "sku": sku_id,
        "orders": orders,
        "mode": "score_only",
        "localization_share_pct": round(share, 2) if share is not None else None,
        "localization_index": round(float(il), 4) if il is not None else None,
        "sales_distribution_index_pct": round(float(irp), 4) if irp is not None else None,
        "loss_per_order_rub": None,
        "total_loss_rub": None,
        "risk_score": risk_score if share is not None else None,
        "risk_level": risk_level,
        "missing_inputs": sorted(set(missing_inputs)),
        "conclusion": conclusion,
    }


def estimate_total_localization_loss(
    *,
    sku_rows: list[dict[str, Any]],
    localization_share_pct: float | None,
    non_local_orders_share: float | None,
    default_volume_liters: float | None,
    default_item_price: float | None,
    warehouse_coef: float = 1.0,
    revenue_total: float | None = None,
) -> dict[str, Any]:
    rows = sku_rows if isinstance(sku_rows, list) else []
    global_share = _to_float_or_none(localization_share_pct)
    non_local_share = _to_float_or_none(non_local_orders_share)
    if non_local_share is None and global_share is not None:
        non_local_share = _clamp(1.0 - (global_share / 100.0), 0.0, 1.0)

    default_price = _to_float_or_none(default_item_price)
    default_volume = _to_float_or_none(default_volume_liters)
    revenue = _to_float_or_none(revenue_total)

    sku_results: list[dict[str, Any]] = []
    orders_total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku") or row.get("nmId") or row.get("nm_id"))
        orders = max(
            _to_int(row.get("orders")),
            _to_int(row.get("buyouts")),
            _to_int(row.get("buyoutCount")),
        )
        if sku <= 0:
            continue
        orders_total += orders
        row_revenue = _to_float_or_none(row.get("revenue"))
        row_price = _to_float_or_none(row.get("item_price"))
        if row_price is None and row_revenue is not None and orders > 0:
            row_price = row_revenue / float(orders)
        row_share = _to_float_or_none(row.get("localization_share_pct"))
        if row_share is None:
            row_share = global_share
        row_volume = _to_float_or_none(row.get("volume_liters"))
        if row_volume is None:
            row_volume = default_volume
        sku_result = estimate_total_localization_loss_for_sku(
            sku=sku,
            orders_count=orders,
            localization_share_pct=row_share,
            volume_liters=row_volume,
            item_price=row_price,
            warehouse_coef=warehouse_coef,
            avg_price_fallback=default_price,
        )
        sku_results.append(sku_result)

    if orders_total <= 0:
        return {
            "status": "insufficient_data",
            "estimation_mode": "insufficient_data",
            "total_estimated_loss_rub": None,
            "loss_share_of_revenue": None,
            "non_local_orders_share": non_local_share,
            "affected_sku_count": 0,
            "top_loss_sku": [],
            "missing_inputs": ["orders_count"],
            "recommendations": [],
        }

    full_count = sum(1 for x in sku_results if _norm_mode(x.get("mode")) == "full_rub")
    partial_count = sum(1 for x in sku_results if _norm_mode(x.get("mode")) == "partial_rub")
    score_count = sum(1 for x in sku_results if _norm_mode(x.get("mode")) == "score_only")
    rub_rows = [x for x in sku_results if _to_float_or_none(x.get("total_loss_rub")) is not None]

    if full_count > 0 and full_count == len(sku_results):
        estimation_mode = "full_rub"
    elif full_count > 0 or partial_count > 0:
        estimation_mode = "partial_rub"
    elif score_count > 0:
        estimation_mode = "score_only"
    else:
        estimation_mode = "insufficient_data"

    total_estimated_loss_rub = None
    if rub_rows:
        total_estimated_loss_rub = round(sum(max(_to_float_or_none(x.get("total_loss_rub")) or 0.0, 0.0) for x in rub_rows), 2)

    loss_share_of_revenue = None
    if total_estimated_loss_rub is not None and revenue is not None and revenue > 0:
        loss_share_of_revenue = round(total_estimated_loss_rub / revenue, 4)

    affected_sku_count = 0
    for row in sku_results:
        total_loss = _to_float_or_none(row.get("total_loss_rub")) or 0.0
        if total_loss > 0:
            affected_sku_count += 1
            continue
        if str(row.get("risk_level") or "").lower() in {"high", "critical"}:
            affected_sku_count += 1

    if rub_rows:
        top_loss = sorted(
            rub_rows,
            key=lambda x: _to_float_or_none(x.get("total_loss_rub")) or 0.0,
            reverse=True,
        )[:10]
    else:
        top_loss = sorted(
            sku_results,
            key=lambda x: _to_float_or_none(x.get("risk_score")) or 0.0,
            reverse=True,
        )[:10]

    missing_inputs: set[str] = set()
    for row in sku_results:
        for key in (row.get("missing_inputs") or []):
            if isinstance(key, str) and key:
                missing_inputs.add(key)

    recommendations: list[dict[str, Any]] = []
    if total_estimated_loss_rub is not None and total_estimated_loss_rub > 0:
        recommendations.append(
            {
                "priority": "P1",
                "area": "logistics",
                "action": "Протестировать дополнительное размещение в целевых регионах",
                "why": "Есть прямая оценка потерь из-за текущей локализации",
                "expected_effect": "Снижение логистической переплаты",
            }
        )
    if non_local_share is not None and non_local_share > 0.4:
        recommendations.append(
            {
                "priority": "P1",
                "area": "logistics",
                "action": "Пересмотреть карту распределения остатков по складам",
                "why": "Высокая доля нелокальных заказов увеличивает риск логистической переплаты",
                "expected_effect": "Снижение доли нелокальных заказов и стабилизация маржи",
            }
        )
    if global_share is not None and global_share < 40.0:
        recommendations.append(
            {
                "priority": "P0",
                "area": "logistics",
                "action": "Срочно перераспределить поставки в регионы основного спроса",
                "why": "Локализация ниже 40% соответствует высокому штрафному профилю ИЛ/ИРП",
                "expected_effect": "Снижение давления логистики на прибыль",
            }
        )

    status = "ok" if estimation_mode in {"full_rub", "partial_rub", "score_only"} else "insufficient_data"
    return {
        "status": status,
        "estimation_mode": estimation_mode,
        "total_estimated_loss_rub": total_estimated_loss_rub,
        "loss_share_of_revenue": loss_share_of_revenue,
        "non_local_orders_share": round(non_local_share, 4) if non_local_share is not None else None,
        "affected_sku_count": int(affected_sku_count),
        "top_loss_sku": top_loss,
        "missing_inputs": sorted(missing_inputs),
        "recommendations": recommendations,
    }


__all__ = [
    "estimate_loss_per_order",
    "estimate_total_localization_loss_for_sku",
    "estimate_total_localization_loss",
]
