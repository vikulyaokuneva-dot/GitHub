# audit/audit_loader.py
import os
from typing import Any, Dict, List, Optional
import pandas as pd


def pick_first_file(dir_path: str) -> Optional[str]:
    if not dir_path or not os.path.isdir(dir_path):
        return None
    for name in os.listdir(dir_path):
        if name.lower().endswith((".xlsx", ".xls", ".csv", ".json")):
            return os.path.join(dir_path, name)
    return None


def _to_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _to_int(x) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


# -------------------------
# ADS (Статистика.xlsx)
# -------------------------
def load_ads_xlsx(path: str) -> List[Dict[str, Any]]:
    """
    Expected sheet: "Статистика"
    Columns typically:
      Номенклатура, Затраты, RUB, Показы, Клики, Заказов на сумму, RUB, ...
    Output rows compatible with src.metrics.calc_ads_metrics
    """
    if not path:
        return []
    df = pd.read_excel(path, sheet_name=0)
    # try exact name
    try:
        df = pd.read_excel(path, sheet_name="Статистика")
    except Exception:
        pass

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        name = str(r.get("Название") or "").strip().lower()
        if name.startswith("всего по кампании"):
            continue
        sku = _to_int(r.get("Номенклатура") or r.get("nmId") or r.get("Код номенклатуры") or 0)

        spend = _to_float(r.get("Затраты, RUB") or r.get("Затраты") or r.get("Расход") or 0)
        impressions = _to_int(r.get("Показы") or r.get("Показы, шт") or r.get("Показов") or 0)
        clicks = _to_int(r.get("Клики") or r.get("Кликов") or 0)
        revenue = _to_float(r.get("Заказов на сумму, RUB") or r.get("Заказов на сумму") or 0)

        rows.append({
            "nmId": sku,
            "spend": spend,
            "impressions": impressions,
            "clicks": clicks,
            "revenueAttr": revenue,
            # calc_ads_metrics also checks "views" as impressions alias
            "views": impressions,
            "name": str(r.get("Название") or ""),
        })
    return rows


# -------------------------
# FINANCE (weekly detailed report)
# -------------------------
def load_finance_xlsx(path: str) -> List[Dict[str, Any]]:
    """
    Takes WB detailed weekly finance report export.
    Output rows compatible with src.metrics.calc_financial_metrics keys.
    """
    if not path:
        return []
    df = pd.read_excel(path, sheet_name=0)

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        doc_type = str(r.get("Тип документа") or r.get("Обоснование для оплаты") or "").strip()

        out.append({
            # operation
            "doc_type_name": doc_type,
            # sku
            "nm_id": _to_int(r.get("Код номенклатуры") or r.get("Артикул WB") or 0),
            # quantity
            "quantity": _to_int(r.get("Кол-во") or r.get("Количество") or 0),

            # amounts
            "retail_amount": _to_float(r.get("Вайлдберриз реализовал Товар (Пр)") or r.get("Вайлдберриз реализовал Товар (Пр)") or 0),
            "retail_price_withdisc_rub": _to_float(r.get("Цена розничная с учетом согласованной скидки") or r.get("Цена розничная") or 0),

            # commission / payout
            "ppvz_sales_commission": _to_float(r.get("Вознаграждение Вайлдберриз (ВВ), без НДС") or 0),
            "ppvz_for_pay": _to_float(r.get("К перечислению Продавцу за реализованный Товар") or 0),

            # logistics / storage / penalties
            "delivery_rub": _to_float(r.get("Услуги по доставке товара покупателю") or r.get("Возмещение за выдачу и возврат товаров на ПВЗ") or 0),
            "storage_fee": _to_float(r.get("Хранение") or 0),
            "penalty": _to_float(r.get("Общая сумма штрафов") or 0),

            # extra fields kept for debugging (optional)
            "_supplier_article": str(r.get("Артикул поставщика") or ""),
            "_name": str(r.get("Название") or ""),
        })
    return out


# -------------------------
# FUNNEL (Воронка продаж по товарам)
# -------------------------
def load_funnel_xlsx(path: str) -> List[Dict[str, Any]]:
    """
    Reads sheet "Товары" with header row at index 1.
    Output rows compatible with src.metrics.calc_funnel_metrics keys.
    """
    if not path:
        return []
    try:
        df = pd.read_excel(path, sheet_name="Товары", header=1)
    except Exception:
        df = pd.read_excel(path, sheet_name=0)

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        nm = _to_int(r.get("Артикул WB") or r.get("Код номенклатуры") or r.get("Номенклатура") or 0)
        views = _to_int(r.get("Переходы в карточку") or r.get("Просмотры") or r.get("Показы") or 0)
        add_to_cart = _to_int(r.get("Положили в корзину") or r.get("Добавлений в корзину") or 0)
        orders = _to_int(r.get("Заказали, шт") or r.get("Заказы") or 0)
        buys = _to_int(r.get("Выкупили, шт") or r.get("Выкупы") or 0)

        order_sum = _to_float(r.get("Заказали на сумму, ₽") or r.get("Заказали на сумму") or 0)
        buyout_sum = _to_float(r.get("Выкупили на сумму, ₽") or r.get("Выкупили на сумму") or 0)

        rows.append({
            "nmId": nm,
            "openCardCount": views,
            "addToCartCount": add_to_cart,
            "orderCount": orders,
            "buyoutCount": buys,
            "orderSum": order_sum,
            "buyoutSum": buyout_sum,
            "name": str(r.get("Название") or ""),
        })
    return rows


# -------------------------
# STOCKS (остатки)
# -------------------------
def load_stocks_xlsx(path: str) -> List[Dict[str, Any]]:
    """
    Stocks export may NOT contain nmId. We still try best-effort:
      - if 'Артикул WB' or 'Код номенклатуры' exists -> use it
      - else create pseudo-sku = 0 and only totals will be meaningful
    Output rows compatible with src.metrics.calc_stock_forecast keys.
    """
    if not path:
        return []
    df = pd.read_excel(path, sheet_name=0)

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        nm = _to_int(r.get("Артикул WB") or r.get("Код номенклатуры") or r.get("Номенклатура") or 0)
        qty_full = _to_int(r.get("Всего находится на складах") or r.get("quantityFull") or r.get("quantity") or 0)

        # in-way fields
        in_way_to_client = _to_int(r.get("В пути до получателей") or 0)
        in_way_from_client = _to_int(r.get("В пути возвраты на склад WB") or 0)

        rows.append({
            "nmId": nm,
            "quantityFull": qty_full,
            "inWayToClient": in_way_to_client,
            "inWayFromClient": in_way_from_client,
            "supplierArticle": str(r.get("Артикул продавца") or r.get("Артикул продавца") or r.get("Артикул поставщика") or ""),
        })
    return rows
