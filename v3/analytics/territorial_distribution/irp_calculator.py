from __future__ import annotations

from datetime import date
from typing import Any, Dict, Mapping, Tuple

from .coefficients import lookup_distribution_coefficients


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace(' ', '').replace(',', '.')
    try:
        return float(candidate)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        year, month, day = text.split('-')[:3]
        return date(int(year), int(month), int(day))
    except Exception:
        return None


def is_effective_date_applied(report_date: str, effective_date: str) -> bool:
    report = _parse_date(report_date)
    effective = _parse_date(effective_date)
    if report is None or effective is None:
        return False
    return report >= effective


def resolve_average_retail_price(
    sku_metrics_row: Mapping[str, Any],
    *,
    total_orders: float,
) -> Tuple[float | None, str, str | None]:
    row = sku_metrics_row if isinstance(sku_metrics_row, Mapping) else {}

    direct_candidates = (
        'retail_price_before_discount',
        'price_before_wb_discount',
        'seller_price_before_discount',
        'average_retail_price',
        'retail_price',
    )
    for key in direct_candidates:
        parsed = _as_float_or_none(row.get(key))
        if parsed is not None and parsed > 0:
            return round(parsed, 4), key, None

    revenue = _as_float_or_none(row.get('revenue'))
    if revenue is not None and revenue > 0 and total_orders > 0:
        return round(revenue / total_orders, 4), 'revenue_div_total_orders', 'price_fallback_revenue_div_orders'

    buys = _as_float_or_none(row.get('buys'))
    if revenue is not None and revenue > 0 and buys is not None and buys > 0:
        return round(revenue / buys, 4), 'revenue_div_buys', 'price_fallback_revenue_div_buys'

    snapshot_candidates = (
        'current_price',
        'price',
        'selling_price',
    )
    for key in snapshot_candidates:
        parsed = _as_float_or_none(row.get(key))
        if parsed is not None and parsed > 0:
            return round(parsed, 4), key, 'price_fallback_snapshot'

    return None, 'missing', 'average_retail_price_missing'


def estimate_irp_penalty(
    *,
    localization_share: float | None,
    total_orders: float,
    average_retail_price: float | None,
    report_date: str,
    effective_date: str,
) -> Dict[str, Any]:
    coefficients = lookup_distribution_coefficients(localization_share)
    effective_applied = is_effective_date_applied(report_date, effective_date)

    if not effective_applied:
        return {
            'ktr': float(coefficients.ktr),
            'krp': float(coefficients.krp),
            'irp_penalty_per_order': 0.0,
            'estimated_irp_penalty_total': 0.0,
            'effective_date_applied': False,
        }

    if total_orders <= 0 or coefficients.krp <= 0:
        return {
            'ktr': float(coefficients.ktr),
            'krp': float(coefficients.krp),
            'irp_penalty_per_order': 0.0,
            'estimated_irp_penalty_total': 0.0,
            'effective_date_applied': True,
        }

    if average_retail_price is None or average_retail_price <= 0:
        return {
            'ktr': float(coefficients.ktr),
            'krp': float(coefficients.krp),
            'irp_penalty_per_order': None,
            'estimated_irp_penalty_total': 0.0,
            'effective_date_applied': True,
        }

    penalty_per_order = round(float(average_retail_price) * float(coefficients.krp), 6)
    penalty_total = round(float(total_orders) * penalty_per_order, 6)
    return {
        'ktr': float(coefficients.ktr),
        'krp': float(coefficients.krp),
        'irp_penalty_per_order': penalty_per_order,
        'estimated_irp_penalty_total': penalty_total,
        'effective_date_applied': True,
    }