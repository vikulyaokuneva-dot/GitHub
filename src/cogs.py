# src/cogs.py
# Себестоимость (итого) по SKU. Значения в рублях за 1 шт.
# Источник: демо-таблица себестоимости (значения синтетические).
# ВАЖНО: если SKU нет в словаре — себестоимость будет 0, и в отчёте появится warning.

from __future__ import annotations

from typing import Dict, Tuple

COGS_TOTAL_BY_SKU: Dict[int, float] = {
    1001004: 200.00,
    1001017: 200.00,
    1001016: 200.00,
    1001008: 200.00,
    1001020: 200.00,
    1001021: 200.00,
    1001009: 200.00,
    1001007: 120.00,
    1001015: 120.00,
    1001019: 120.00,
    1001018: 120.00,
    1001006: 120.00,
    1001005: 180.00,
    1001014: 400.00,
    1001013: 400.00,
    1001011: 400.00,
    1001012: 400.00,
    1001010: 350.00,
    1001002: 300.00,
    1001003: 310.00,
    1001001: 500.00,
}


def get_cogs_total(sku: int) -> float:
    return float(COGS_TOTAL_BY_SKU.get(int(sku), 0.0))


def calc_cogs_for_rows(qty_by_sku: Dict[int, int]) -> Tuple[float, Dict[int, float], Dict[int, int]]:
    """Возвращает:
    - total_cogs
    - cogs_by_sku (руб)
    - missing_sku_qty (шт) — SKU, которых нет в справочнике
    """
    total = 0.0
    cogs_by_sku: Dict[int, float] = {}
    missing: Dict[int, int] = {}

    for sku, qty in qty_by_sku.items():
        cost = get_cogs_total(sku)
        if cost <= 0:
            missing[int(sku)] = int(qty)
            continue
        rub = float(cost) * int(qty)
        cogs_by_sku[int(sku)] = round(rub, 2)
        total += rub

    return round(total, 2), cogs_by_sku, missing
