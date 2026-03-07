# src/cogs.py
# Себестоимость (итого) по SKU. Значения в рублях за 1 шт.
# Источник: таблица Сергея (Итого_себес).
# ВАЖНО: если SKU нет в словаре — себестоимость будет 0, и в отчёте появится warning.

from __future__ import annotations

from typing import Dict, Tuple

COGS_TOTAL_BY_SKU: Dict[int, float] = {
    333615320: 210.00,
    584904841: 210.00,
    583633646: 210.00,
    452102417: 210.00,
    739377515: 210.00,
    739384273: 210.00,
    453526507: 210.00,
    430679462: 150.00,
    583470321: 150.00,
    590614192: 150.00,
    584925420: 150.00,
    414589567: 150.00,
    411974544: 200.00,
    551253854: 436.50,
    551251065: 436.50,
    547274690: 436.50,
    550928555: 436.50,
    473036762: 365.50,
    291361554: 305.00,
    295325676: 315.00,
    283212418: 600.00,
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
