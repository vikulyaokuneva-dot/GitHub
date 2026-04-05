"""WB logistics formula model (IL/IRP) with safe partial computations."""

from __future__ import annotations

from typing import Any

DELIVERY_FIRST_LITER_RUB = 46.0
DELIVERY_ADDITIONAL_LITER_RUB = 14.0
STORAGE_BOX_FIRST_LITER_RUB_PER_DAY = 0.08
STORAGE_BOX_ADDITIONAL_LITER_RUB_PER_DAY = 0.08
STORAGE_MONOPALLET_RUB_PER_DAY = 25.0

SUPPLY_TYPE_BOX = "box"
SUPPLY_TYPE_MONOPALLET = "monopallet"

SMALL_VOLUME_TARIFFS: tuple[tuple[float, float, float], ...] = (
    (0.001, 0.200, 23.0),
    (0.201, 0.400, 26.0),
    (0.401, 0.600, 29.0),
    (0.601, 0.800, 30.0),
    (0.801, 1.000, 32.0),
)

LOCALIZATION_TO_INDICES: tuple[tuple[float, float, float, float], ...] = (
    (95.00, 100.00, 0.50, 0.00),
    (90.00, 94.99, 0.60, 0.00),
    (85.00, 89.99, 0.70, 0.00),
    (80.00, 84.99, 0.80, 0.00),
    (75.00, 79.99, 0.90, 0.00),
    (70.00, 74.99, 1.00, 0.00),
    (65.00, 69.99, 1.00, 0.00),
    (60.00, 64.99, 1.00, 0.00),
    (55.00, 59.99, 1.05, 2.00),
    (50.00, 54.99, 1.10, 2.05),
    (45.00, 49.99, 1.20, 2.05),
    (40.00, 44.99, 1.30, 2.10),
    (35.00, 39.99, 1.40, 2.10),
    (30.00, 34.99, 1.50, 2.15),
    (25.00, 29.99, 1.55, 2.20),
    (20.00, 24.99, 1.60, 2.25),
    (15.00, 19.99, 1.70, 2.30),
    (10.00, 14.99, 1.75, 2.35),
    (5.00, 9.99, 1.80, 2.45),
    (0.00, 4.99, 2.00, 2.50),
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


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def normalize_supply_type(supply_type: str | None) -> str:
    text = str(supply_type or "").strip().lower()
    if text in {"monopallet", "mono", "pallet", "монопаллета", "монопалета"}:
        return SUPPLY_TYPE_MONOPALLET
    return SUPPLY_TYPE_BOX


def tariff_per_liter_for_volume(volume_liters: float | None) -> float | None:
    volume = _to_float_or_none(volume_liters)
    if volume is None or volume <= 0:
        return None
    if volume > 1.0:
        return None
    for low, high, tariff in SMALL_VOLUME_TARIFFS:
        if (volume + 1e-9) >= low and (volume - 1e-9) <= high:
            return tariff
    # Tiny positive values (<0.001L) keep minimal tariff as fallback.
    return SMALL_VOLUME_TARIFFS[0][2]


def localization_indices_by_share(localization_share_pct: float | None) -> tuple[float | None, float | None]:
    share = _to_float_or_none(localization_share_pct)
    if share is None:
        return None, None
    share = min(max(share, 0.0), 100.0)
    for low, high, loc_idx, sales_idx_pct in LOCALIZATION_TO_INDICES:
        if (share + 1e-9) >= low and (share - 1e-9) <= high:
            return loc_idx, sales_idx_pct
    # Defensive fallback to the worst bucket.
    return 2.0, 2.5


def calculate_base_logistics(
    *,
    volume_liters: float | None,
    warehouse_coef: float = 1.0,
    localization_index: float = 1.0,
    tariff_per_liter: float | None = None,
) -> float | None:
    volume = _to_float_or_none(volume_liters)
    if volume is None or volume <= 0:
        return None
    coef = _to_float_or_none(warehouse_coef) or 1.0
    loc_idx = _to_float_or_none(localization_index) or 1.0

    if volume <= 1.0:
        tariff = _to_float_or_none(tariff_per_liter)
        if tariff is None:
            tariff = tariff_per_liter_for_volume(volume)
        if tariff is None:
            return None
        return float(volume * tariff * coef * loc_idx)

    additional_liters = max(volume - 1.0, 0.0)
    return float((DELIVERY_FIRST_LITER_RUB + DELIVERY_ADDITIONAL_LITER_RUB * additional_liters) * coef * loc_idx)


def calculate_reverse_logistics(volume_liters: float | None) -> float | None:
    volume = _to_float_or_none(volume_liters)
    if volume is None or volume <= 0:
        return None
    additional_liters = max(volume - 1.0, 0.0)
    return float(DELIVERY_FIRST_LITER_RUB + DELIVERY_ADDITIONAL_LITER_RUB * additional_liters)


def calculate_storage_daily(
    *,
    volume_liters: float | None,
    warehouse_coef: float = 1.0,
    supply_type: str = SUPPLY_TYPE_BOX,
) -> float | None:
    coef = _to_float_or_none(warehouse_coef) or 1.0
    normalized_supply_type = normalize_supply_type(supply_type)
    if normalized_supply_type == SUPPLY_TYPE_MONOPALLET:
        return float(STORAGE_MONOPALLET_RUB_PER_DAY * coef)

    volume = _to_float_or_none(volume_liters)
    if volume is None or volume <= 0:
        return None
    additional_liters = max(volume - 1.0, 0.0)
    return float(
        (STORAGE_BOX_FIRST_LITER_RUB_PER_DAY + STORAGE_BOX_ADDITIONAL_LITER_RUB_PER_DAY * additional_liters) * coef
    )


def _warehouse_coef_to_multiplier(value: float | None) -> float:
    parsed = _to_float_or_none(value)
    if parsed is None or parsed <= 0:
        return 1.0
    # In some sources warehouse coefficient is stored as percent (e.g. 155 -> 1.55).
    if parsed > 10.0:
        return parsed / 100.0
    return parsed


def compute_wb_logistics_estimate(
    volume_liters: float | None,
    item_price: float | None,
    warehouse_coef: float = 1.0,
    localization_share_pct: float | None = None,
    supply_type: str = SUPPLY_TYPE_BOX,
    is_sgt: bool = False,
    is_courier_wb: bool = False,
) -> dict[str, Any]:
    volume = _to_float_or_none(volume_liters)
    price = _to_float_or_none(item_price)
    localization_share = _to_float_or_none(localization_share_pct)
    coef_multiplier = _warehouse_coef_to_multiplier(warehouse_coef)
    supply_kind = normalize_supply_type(supply_type)

    missing_inputs: list[str] = []
    if volume is None or volume <= 0:
        missing_inputs.append("volume_liters")
    if price is None or price <= 0:
        missing_inputs.append("item_price")
    if localization_share is None:
        missing_inputs.append("localization_share_pct")

    localization_index, sales_distribution_index_pct = localization_indices_by_share(localization_share)
    assumptions: list[str] = []
    if localization_index is None:
        localization_index = 1.0
        assumptions.append("localization_index_assumed_1_0")
    if sales_distribution_index_pct is None:
        sales_distribution_index_pct = 0.0
        assumptions.append("sales_distribution_index_pct_assumed_0")

    tariff = tariff_per_liter_for_volume(volume)
    base_logistics = calculate_base_logistics(
        volume_liters=volume,
        warehouse_coef=coef_multiplier,
        localization_index=localization_index,
        tariff_per_liter=tariff,
    )

    # ИЛ используем как множитель к логистической части (базовый тариф * складской коэффициент * ИЛ).
    # ИРП храним в процентах и в расчёте переводим в долю.
    # ИРП применяем как процент от цены товара.
    sales_distribution_component = (
        float(price * (sales_distribution_index_pct / 100.0))
        if price is not None and sales_distribution_index_pct is not None
        else None
    )
    if sales_distribution_index_pct == 0.0 and sales_distribution_component is None:
        sales_distribution_component = 0.0

    estimated_delivery_cost = None
    if base_logistics is not None and sales_distribution_component is not None:
        estimated_delivery_cost = float(base_logistics + sales_distribution_component)

    neutral_base_logistics = calculate_base_logistics(
        volume_liters=volume,
        warehouse_coef=coef_multiplier,
        localization_index=1.0,
        tariff_per_liter=tariff,
    )
    neutral_estimated_delivery_cost = neutral_base_logistics
    overpayment_absolute = None
    overpayment_pct_vs_neutral = None
    if estimated_delivery_cost is not None and neutral_estimated_delivery_cost is not None:
        overpayment_absolute = float(estimated_delivery_cost - neutral_estimated_delivery_cost)
        if neutral_estimated_delivery_cost > 0:
            overpayment_pct_vs_neutral = float((overpayment_absolute / neutral_estimated_delivery_cost) * 100.0)

    reverse_logistics = calculate_reverse_logistics(volume)
    storage_daily = calculate_storage_daily(
        volume_liters=volume,
        warehouse_coef=coef_multiplier,
        supply_type=supply_kind,
    )

    if not missing_inputs:
        status = "complete"
    elif base_logistics is None and reverse_logistics is None and storage_daily is None:
        status = "missing_inputs"
    else:
        status = "partial"

    if status == "complete":
        explanation = "Расчёт выполнен полностью по формуле WB (базовая логистика + ИЛ/ИРП + хранение + обратная логистика)."
    elif status == "partial":
        explanation = (
            "Расчёт выполнен частично: часть входов отсутствует, поэтому отдельные компоненты оценки недоступны. "
            f"Не хватает: {', '.join(missing_inputs)}."
        )
    else:
        explanation = (
            "Расчёт не выполнен: недостаточно входных данных для оценки по формуле WB. "
            f"Не хватает: {', '.join(missing_inputs)}."
        )

    return {
        "status": status,
        "inputs_available": {
            "volume_liters": volume is not None and volume > 0,
            "item_price": price is not None and price > 0,
            "warehouse_coef": True,
            "localization_share_pct": localization_share is not None,
            "supply_type": bool(supply_kind),
        },
        "missing_inputs": missing_inputs,
        "volume_liters": _round_or_none(volume, 4),
        "item_price": _round_or_none(price, 2),
        "warehouse_coef": _round_or_none(coef_multiplier, 4),
        "supply_type": supply_kind,
        "tariff_per_liter": _round_or_none(tariff, 2),
        "base_logistics": _round_or_none(base_logistics, 2),
        "localization_share_pct": _round_or_none(localization_share, 2),
        "localization_index": _round_or_none(localization_index, 4),
        "sales_distribution_index_pct": _round_or_none(sales_distribution_index_pct, 4),
        "sales_distribution_component": _round_or_none(sales_distribution_component, 2),
        "estimated_delivery_cost": _round_or_none(estimated_delivery_cost, 2),
        "neutral_estimated_delivery_cost": _round_or_none(neutral_estimated_delivery_cost, 2),
        "overpayment_absolute": _round_or_none(overpayment_absolute, 2),
        "overpayment_pct_vs_neutral": _round_or_none(overpayment_pct_vs_neutral, 2),
        "estimated_reverse_logistics": _round_or_none(reverse_logistics, 2),
        "estimated_storage_daily": _round_or_none(storage_daily, 4),
        "diagnostics": {
            "assumptions": assumptions,
            "flags": {
                "is_sgt": bool(is_sgt),
                "is_courier_wb": bool(is_courier_wb),
                "volume_missing": bool(volume is None or volume <= 0),
            },
        },
        "explanation": explanation,
    }


__all__ = [
    "SMALL_VOLUME_TARIFFS",
    "LOCALIZATION_TO_INDICES",
    "SUPPLY_TYPE_BOX",
    "SUPPLY_TYPE_MONOPALLET",
    "tariff_per_liter_for_volume",
    "localization_indices_by_share",
    "calculate_base_logistics",
    "calculate_reverse_logistics",
    "calculate_storage_daily",
    "compute_wb_logistics_estimate",
]
