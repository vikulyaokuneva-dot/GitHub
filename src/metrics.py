# src/metrics.py
import datetime as dt
import json
import re
from typing import Any, Dict, List, Tuple

from src.cogs import calc_cogs_for_rows


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def _try_json_loads(x: Any) -> Any:
    if isinstance(x, str):
        s = x.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return json.loads(s)
            except Exception:
                return x
    return x


def _find_first_list(obj: Any, max_depth: int = 5) -> List[Dict[str, Any]] | None:
    obj = _try_json_loads(obj)
    if max_depth <= 0:
        return None

    if isinstance(obj, list):
        dicts = []
        for it in obj:
            it = _try_json_loads(it)
            if isinstance(it, dict):
                dicts.append(it)
        return dicts or None

    if isinstance(obj, dict):
        preferred_keys = ["items", "products", "rows", "list", "result", "stocks", "data"]
        for k in preferred_keys:
            if k in obj:
                found = _find_first_list(obj.get(k), max_depth=max_depth - 1)
                if found:
                    return found
        for v in obj.values():
            found = _find_first_list(v, max_depth=max_depth - 1)
            if found:
                return found
    return None


def _normalize_items(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    raw = _try_json_loads(raw)
    found = _find_first_list(raw)
    if found:
        return found
    if isinstance(raw, dict):
        return [raw]
    return []


def _normalize_sku_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = text.replace("\xa0", " ").replace(",", ".").strip()
    try:
        if re.match(r"^\d+(\.0+)?$", cleaned):
            return str(int(float(cleaned)))
    except Exception:
        pass
    return cleaned


def _normalize_seller_token(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip().lower()
    return " ".join(text.split())


# --------------------
# Ads
# --------------------
def calc_ads_metrics(ads_raw: Any) -> Dict[str, Any]:
    items = _normalize_items(ads_raw)

    spend = 0.0
    revenue_attr = 0.0
    clicks = 0
    impressions = 0

    def add_stat(stat: dict):
        nonlocal spend, revenue_attr, clicks, impressions
        spend += float(stat.get("spend", 0) or stat.get("cost", 0) or stat.get("sum", 0) or 0)
        clicks += int(stat.get("clicks", 0) or stat.get("click", 0) or 0)
        impressions += int(stat.get("views", 0) or stat.get("impressions", 0) or stat.get("shows", 0) or 0)
        revenue_attr += float(stat.get("revenue", 0) or stat.get("revenueAttr", 0) or stat.get("orderSum", 0) or 0)

    for it in items:
        if isinstance(it, dict):
            add_stat(it)
            ds = it.get("dailyStats")
            if isinstance(ds, list):
                for d in ds:
                    if isinstance(d, dict) and isinstance(d.get("stat"), dict):
                        add_stat(d["stat"])

    roas = safe_div(revenue_attr, spend)
    ctr = safe_div(clicks, impressions)
    cpc = safe_div(spend, clicks)

    # ВАЖНО: если атрибуции выручки нет (revenue_attr=0) при наличии spend,
    # то ДРР нельзя считать (иначе получится 0 и это вводит в заблуждение).
    drr = None
    if revenue_attr > 0:
        drr = safe_div(spend, revenue_attr)
    cpm = safe_div(spend * 1000.0, impressions)

    return {
        "spend": round(spend, 2),
        "revenue_attr": round(revenue_attr, 2),
        "clicks": clicks,
        "impressions": impressions,
        "roas": round(roas, 3),
        "drr": (round(drr, 4) if isinstance(drr, (int, float)) else None),
        "ctr": round(ctr, 4),
        "cpc": round(cpc, 2),
        "cpm": round(cpm, 2),
        "items_count": len(items),
    }


# --------------------
# Funnel (seller-analytics)
# --------------------
def _pick_stat_block(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    seller-analytics sales-funnel/products часто отдаёт структуру:
    { product: {...}, statistic: { selected: {...}, past: {...}, comparison: {...} } }
    Метрики лежат внутри statistic.selected
    """
    st = item.get("statistic")
    if isinstance(st, dict):
        selected = st.get("selected") or st.get("current") or st.get("now")
        if isinstance(selected, dict):
            return selected
    return item


def calc_funnel_metrics(funnel_raw: Any) -> Dict[str, Any]:
    items = _normalize_items(funnel_raw)

    views = 0
    add_to_cart = 0
    orders = 0
    buys = 0
    revenue_orders = 0.0
    revenue_buyouts = 0.0

    for it in items:
        stat = _pick_stat_block(it)

        # просмотры карточки
        views += int(stat.get("views", 0) or stat.get("openCount", 0) or stat.get("openCardCount", 0) or 0)

        # добавления в корзину
        add_to_cart += int(
            stat.get("add_to_cart", 0) or stat.get("cartCount", 0) or stat.get("addToCartCount", 0) or 0
        )

        # заказы
        orders += int(stat.get("orders", 0) or stat.get("orderCount", 0) or 0)

        # выкупы
        buys += int(stat.get("buys", 0) or stat.get("buyoutCount", 0) or 0)

        # суммы (часто orderSum / buyoutSum)
        revenue_orders += float(stat.get("orderSum", 0) or 0)
        revenue_buyouts += float(stat.get("buyoutSum", 0) or 0)

    cr_cart = safe_div(add_to_cart, views)
    cr_order = safe_div(orders, add_to_cart)
    buyout_rate = safe_div(buys, orders)

    return {
        "views": views,
        "add_to_cart": add_to_cart,
        "orders": orders,
        "buys": buys,
        "revenue_orders": round(revenue_orders, 2),
        "revenue_buyouts": round(revenue_buyouts, 2),
        "cr_cart": round(cr_cart, 4),
        "cr_order": round(cr_order, 4),
        "buyout_rate": round(buyout_rate, 4),
        "items_count": len(items),
    }


# --------------------
# Stocks
# --------------------
def calc_stock_forecast(
    stocks_raw: Any,
    avg_daily_sales: float,
    lead_days: int = 7,
    safety_days: int = 3
) -> Dict[str, Any]:
    items = _normalize_items(stocks_raw)

    def to_int(x) -> int:
        try:
            if x is None or x == "":
                return 0
            return int(float(x))
        except Exception:
            return 0

    # WB stocks часто приходит построчно по складам -> агрегируем по nmId
    per_sku: Dict[int, int] = {}

    for it in items:
        if not isinstance(it, dict):
            continue
        sku = to_int(it.get("nmId") or it.get("nm_id") or it.get("nmID") or it.get("nm") or 0)
        if not sku:
            continue

        q_full = to_int(it.get("quantityFull"))
        q = to_int(it.get("quantity"))
        # Транзитные поля не входят в складской остаток.
        qty = max(q_full, q)

        per_sku[sku] = per_sku.get(sku, 0) + qty

    total_units = sum(per_sku.values())

    days_of_cover = safe_div(total_units, avg_daily_sales)
    threshold = lead_days + safety_days

    return {
        "stock_units": int(total_units),
        "sku_count": int(len(per_sku)),
        "days_of_cover": round(float(days_of_cover or 0.0), 2),
        "risk_of_oos": bool(days_of_cover != 0 and days_of_cover < threshold),
        "threshold_days": int(threshold),
        "items_count": int(len(items)),
    }

def calc_financial_metrics(
    realization_raw: Any,
    tax_rate: float = 0.06,
    cogs_rows: Any | None = None,
    *,
    cogs_file_found: bool | None = None,
) -> Dict[str, Any]:
    """Считает финансы за период по отчету реализации (reportDetailByPeriod) + SKU P&L.

    ВАЖНО:
      - account-level: gross_revenue считается только по продажам (как раньше)
      - returns_qty считается отдельно
      - SKU P&L строится по строкам, где есть nm_id (SKU)
      - Налог распределяем по SKU пропорционально sales_revenue_sku
      - Возвраты уменьшают SKU прибыль через returns_revenue_est (оценка)
    """
    rows = _normalize_items(realization_raw)

    def f(x) -> float:
        try:
            if x is None or x == "":
                return 0.0
            return float(x)
        except Exception:
            return 0.0

    def i(x) -> int:
        try:
            if x is None or x == "":
                return 0
            return int(float(x))
        except Exception:
            return 0

    def s(x) -> str:
        return str(x or "").strip().lower()

    sales_qty = 0
    returns_qty = 0

    gross_revenue = 0.0
    turnover_wb = 0.0
    turnover_wb_rows_count = 0
    commission = 0.0
    base_commission = 0.0
    pvz_compensation = 0.0
    payment_services_compensation = 0.0
    payment_services_compensation_amount = 0.0
    logistics = 0.0
    storage = 0.0
    penalties = 0.0
    payout = 0.0
    storage_rows_nonzero = 0
    storage_source_counts: Dict[str, int] = {}
    storage_source_columns_seen: set[str] = set()

    qty_by_sku: Dict[int, int] = {}
    sku_seller_tokens: Dict[int, set[str]] = {}

    sku_map: Dict[int, Dict[str, float]] = {}

    use_base_before_agent = False
    for probe in rows:
        if not isinstance(probe, dict):
            continue
        if f(probe.get("wb_reward_before_agent")) != 0:
            use_base_before_agent = True
            break

    def sku_get(sku_i: int) -> Dict[str, float]:
        if sku_i not in sku_map:
            sku_map[sku_i] = {
                "sales_qty": 0.0,
                "returns_qty": 0.0,
                "sales_revenue": 0.0,
                "returns_revenue_est": 0.0,
                "commission": 0.0,
                "logistics": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "payout": 0.0,
            }
        return sku_map[sku_i]

    for r in rows:
        if not isinstance(r, dict):
            continue

        oper = s(r.get("supplier_oper_name") or r.get("operationTypeName") or r.get("doc_type_name"))

        sku = (r.get("nm_id") or r.get("nmId") or r.get("nmID") or r.get("nm"))
        sku_i = i(sku)

        qty = i(r.get("quantity") or r.get("qty") or r.get("count") or 0)

        row_amount = f(r.get("retail_amount") or r.get("retailAmount") or r.get("sale_amount") or r.get("saleAmount") or 0)

        unit_price = f(
            r.get("retail_price_withdisc_rub")
            or r.get("retailPriceWithDiscRub")
            or r.get("retail_price")
            or r.get("retailPrice")
            or 0
        )
        row_retail_price = f(r.get("retail_price") or r.get("retailPrice") or 0)

        row_commission = f(
            r.get("ppvz_sales_commission")
            or r.get("ppvzSalesCommission")
            or r.get("commission_amount")
            or r.get("commissionAmount")
            or 0
        )
        row_base_commission = f(r.get("wb_reward_before_agent"))
        if row_base_commission == 0:
            row_base_commission = row_commission if (not use_base_before_agent or row_commission != 0) else 0.0
        row_pvz_compensation = f(r.get("pvz_compensation"))
        row_payment_services_compensation = f(r.get("payment_services_compensation"))
        row_payment_services_compensation_amount = f(r.get("payment_services_compensation_amount"))
        row_commission_total = (
            float(row_base_commission)
            + float(row_pvz_compensation)
            + float(row_payment_services_compensation)
            + float(row_payment_services_compensation_amount)
        )
        row_logistics = f(
            r.get("delivery_rub")
            or r.get("deliveryRub")
            or r.get("logistics")
            or r.get("logistics_cost")
            or 0
        )
        row_storage = f(r.get("storage_fee") or r.get("storageFee") or r.get("storage") or 0)
        storage_source_column_raw = str(r.get("_storage_source_column") or "").strip()
        if storage_source_column_raw:
            storage_source_columns_seen.add(storage_source_column_raw)
        if abs(row_storage) > 1e-9:
            storage_rows_nonzero += 1
            if storage_source_column_raw:
                storage_source_counts[storage_source_column_raw] = storage_source_counts.get(storage_source_column_raw, 0) + 1
        row_penalty = f(r.get("penalty") or r.get("penaltyAmount") or r.get("fine") or 0)
        # payout берется напрямую из finance отчета WB ("К перечислению продавцу"), без перерасчета формулой.
        row_payout = f(r.get("ppvz_for_pay") or r.get("ppvzForPay") or r.get("to_pay") or r.get("toPay") or 0)
        seller_token = _normalize_seller_token(
            r.get("_supplier_article")
            or r.get("supplierArticle")
            or r.get("Артикул поставщика")
            or r.get("Артикул продавца")
            or ""
        )

        is_sale = ("продаж" in oper) and ("возврат" not in oper)
        is_return = ("возврат" in oper) or ("return" in oper)
        is_logistics = "логист" in oper
        is_storage = "хран" in oper
        is_penalty = ("штраф" in oper) or ("penalty" in oper) or ("fine" in oper)

        def est_amount(q: int) -> float:
            q_eff = abs(q) if q else 1
            if row_amount:
                return abs(row_amount)
            return abs(unit_price) * q_eff

        if is_sale:
            if qty > 0:
                sales_qty += qty
                if sku_i:
                    qty_by_sku[sku_i] = qty_by_sku.get(sku_i, 0) + qty
                    if seller_token:
                        sku_seller_tokens.setdefault(sku_i, set()).add(seller_token)

            gross_revenue += row_amount if row_amount else unit_price * (qty if qty else 1)
            # KPI "Оборот как в WB": строго сумма retail_price по операциям Продажа.
            if row_retail_price:
                turnover_wb += row_retail_price
                turnover_wb_rows_count += 1

            commission += row_commission_total
            base_commission += row_base_commission
            pvz_compensation += row_pvz_compensation
            payment_services_compensation += row_payment_services_compensation
            payment_services_compensation_amount += row_payment_services_compensation_amount
            payout += row_payout

            logistics += abs(row_logistics) if row_logistics else 0.0
            storage += abs(row_storage) if row_storage else 0.0
            penalties += abs(row_penalty) if row_penalty else 0.0

            if sku_i:
                m = sku_get(sku_i)
                if qty > 0:
                    m["sales_qty"] += float(qty)
                m["sales_revenue"] += float(row_amount) if row_amount else float(unit_price) * float(qty if qty else 1)
                m["commission"] += float(row_commission_total)
                m["payout"] += float(row_payout)
                if row_logistics:
                    m["logistics"] += float(abs(row_logistics))
                if row_storage:
                    m["storage"] += float(abs(row_storage))
                if row_penalty:
                    m["penalties"] += float(abs(row_penalty))
            continue

        if is_return:
            if qty != 0:
                returns_qty += abs(qty)

            commission += row_commission_total
            base_commission += row_base_commission
            pvz_compensation += row_pvz_compensation
            payment_services_compensation += row_payment_services_compensation
            payment_services_compensation_amount += row_payment_services_compensation_amount
            logistics += abs(row_logistics) if row_logistics else 0.0
            storage += abs(row_storage) if row_storage else 0.0
            penalties += abs(row_penalty) if row_penalty else 0.0
            payout += row_payout

            if sku_i:
                m = sku_get(sku_i)
                if qty != 0:
                    m["returns_qty"] += float(abs(qty))
                m["returns_revenue_est"] += float(est_amount(qty))
                m["commission"] += float(row_commission_total)
                if row_logistics:
                    m["logistics"] += float(abs(row_logistics))
                if row_storage:
                    m["storage"] += float(abs(row_storage))
                if row_penalty:
                    m["penalties"] += float(abs(row_penalty))
                m["payout"] += float(row_payout)
            continue

        if is_logistics:
            logistics += abs(row_logistics) if row_logistics else 0.0
            logistics += abs(f(r.get("rebill_logistic_cost") or 0))
            payout += row_payout

            if sku_i:
                m = sku_get(sku_i)
                if row_logistics:
                    m["logistics"] += float(abs(row_logistics))
                reb = f(r.get("rebill_logistic_cost") or 0)
                if reb:
                    m["logistics"] += float(abs(reb))
                m["payout"] += float(row_payout)
            continue

        if is_storage:
            storage += abs(row_storage) if row_storage else 0.0
            payout += row_payout

            if sku_i:
                m = sku_get(sku_i)
                if row_storage:
                    m["storage"] += float(abs(row_storage))
                m["payout"] += float(row_payout)
            continue

        if is_penalty:
            penalties += abs(row_penalty) if row_penalty else 0.0
            payout += row_payout

            if sku_i:
                m = sku_get(sku_i)
                if row_penalty:
                    m["penalties"] += float(abs(row_penalty))
                m["payout"] += float(row_payout)
            continue

        commission += row_commission_total
        base_commission += row_base_commission
        pvz_compensation += row_pvz_compensation
        payment_services_compensation += row_payment_services_compensation
        payment_services_compensation_amount += row_payment_services_compensation_amount
        logistics += abs(row_logistics) if row_logistics else 0.0
        storage += abs(row_storage) if row_storage else 0.0
        penalties += abs(row_penalty) if row_penalty else 0.0
        payout += row_payout

        if sku_i:
            m = sku_get(sku_i)
            m["commission"] += float(row_commission_total)
            if row_logistics:
                m["logistics"] += float(abs(row_logistics))
            if row_storage:
                m["storage"] += float(abs(row_storage))
            if row_penalty:
                m["penalties"] += float(abs(row_penalty))
            m["payout"] += float(row_payout)

    cogs_by_sku: Dict[int, float] = {}
    missing_sku_qty: Dict[int, int] = {}
    cogs_rows_loaded = 0
    cogs_sku_total = 0
    cogs_matched_sku = 0
    cogs_unmatched_sku: list[int] = []
    cogs_match_key = "nm_id|seller_article"

    legacy_mode = cogs_rows is None and cogs_file_found is None
    file_found = bool(cogs_file_found) if cogs_file_found is not None else bool(cogs_rows is not None)
    if legacy_mode:
        cogs_total, cogs_by_sku, missing_sku_qty = calc_cogs_for_rows(qty_by_sku)
        cogs_status = "legacy_static_map"
        cogs_rows_loaded = int(len(cogs_by_sku))
        cogs_sku_total = int(len(cogs_by_sku))
        cogs_matched_sku = int(len(cogs_by_sku))
        cogs_unmatched_sku = sorted(int(sku) for sku in missing_sku_qty.keys())[:200]
    else:
        cogs_total = 0.0
        parsed_cogs_rows = [row for row in (cogs_rows or []) if isinstance(row, dict)]
        cogs_rows_loaded = int(len(parsed_cogs_rows))
        cogs_by_sku_id: Dict[int, float] = {}
        cogs_by_sku_token: Dict[str, float] = {}
        cogs_by_seller_token: Dict[str, float] = {}
        for item in parsed_cogs_rows:
            cost = f(item.get("cogs"))
            if cost <= 0:
                continue
            sku_token = _normalize_sku_token(item.get("sku_token") or item.get("sku"))
            seller_token = _normalize_seller_token(item.get("seller_sku_token") or item.get("seller_sku"))
            if sku_token:
                cogs_by_sku_token[sku_token] = float(cost)
                try:
                    sku_id = int(float(sku_token))
                    if sku_id > 0:
                        cogs_by_sku_id[sku_id] = float(cost)
                except Exception:
                    pass
            if seller_token:
                cogs_by_seller_token[seller_token] = float(cost)

        cogs_sku_total = int(len(set(list(cogs_by_sku_token.keys()) + list(cogs_by_seller_token.keys()))))
        for sku_i, qty in qty_by_sku.items():
            if int(qty) <= 0:
                continue
            sku_cost = None
            if sku_i in cogs_by_sku_id:
                sku_cost = cogs_by_sku_id.get(sku_i)
            if sku_cost is None:
                sku_token = _normalize_sku_token(sku_i)
                if sku_token and sku_token in cogs_by_sku_token:
                    sku_cost = cogs_by_sku_token.get(sku_token)
            if sku_cost is None:
                for seller_token in sorted(sku_seller_tokens.get(sku_i) or []):
                    if seller_token in cogs_by_seller_token:
                        sku_cost = cogs_by_seller_token.get(seller_token)
                        break
            if sku_cost is None or float(sku_cost or 0.0) <= 0:
                missing_sku_qty[int(sku_i)] = int(qty)
                cogs_unmatched_sku.append(int(sku_i))
                continue
            sku_cost_total = float(sku_cost) * int(qty)
            cogs_by_sku[int(sku_i)] = round(sku_cost_total, 2)
            cogs_total += sku_cost_total

        cogs_total = round(cogs_total, 2)
        cogs_matched_sku = int(len(cogs_by_sku))
        total_sku_with_qty = int(len([sku for sku, qty in qty_by_sku.items() if int(qty) > 0]))
        cogs_unmatched_sku = sorted(set(cogs_unmatched_sku))[:200]
        if not file_found:
            cogs_status = "file_not_found"
        elif cogs_rows_loaded <= 0:
            cogs_status = "file_found_not_read"
        elif total_sku_with_qty > 0 and cogs_matched_sku == 0:
            cogs_status = "file_read_not_matched"
        elif total_sku_with_qty > 0 and cogs_matched_sku < total_sku_with_qty:
            cogs_status = "partial_match"
        else:
            cogs_status = "full_match"

    tax = gross_revenue * float(tax_rate or 0.0)

    profit = gross_revenue - commission - logistics - storage - penalties - tax - cogs_total
    margin = safe_div(profit, gross_revenue)

    sku_financials: Dict[int, Dict[str, Any]] = {}
    total_sku_sales_revenue = sum(float(m.get("sales_revenue", 0.0) or 0.0) for m in sku_map.values())

    for sku_i, m in sku_map.items():
        sales_rev = float(m.get("sales_revenue", 0.0) or 0.0)
        returns_rev_est = float(m.get("returns_revenue_est", 0.0) or 0.0)
        net_rev = sales_rev - returns_rev_est

        sku_tax = (tax * (sales_rev / total_sku_sales_revenue)) if total_sku_sales_revenue else 0.0
        sku_cogs = float(cogs_by_sku.get(int(sku_i), 0.0) or 0.0)

        sku_profit = (
            net_rev
            - float(m.get("commission", 0.0) or 0.0)
            - float(m.get("logistics", 0.0) or 0.0)
            - float(m.get("storage", 0.0) or 0.0)
            - float(m.get("penalties", 0.0) or 0.0)
            - sku_tax
            - sku_cogs
        )
        sku_margin = safe_div(sku_profit, net_rev)

        sku_financials[int(sku_i)] = {
            "sales_qty": int(round(float(m.get("sales_qty", 0.0) or 0.0))),
            "returns_qty": int(round(float(m.get("returns_qty", 0.0) or 0.0))),
            "sales_revenue": round(sales_rev, 2),
            "returns_revenue_est": round(returns_rev_est, 2),
            "net_revenue": round(net_rev, 2),
            "commission": round(float(m.get("commission", 0.0) or 0.0), 2),
            "logistics": round(float(m.get("logistics", 0.0) or 0.0), 2),
            "storage": round(float(m.get("storage", 0.0) or 0.0), 2),
            "penalties": round(float(m.get("penalties", 0.0) or 0.0), 2),
            "payout": round(float(m.get("payout", 0.0) or 0.0), 2),
            "tax_alloc": round(sku_tax, 2),
            "cogs": round(sku_cogs, 2),
            "profit": round(sku_profit, 2),
            "margin": round(float(sku_margin or 0.0), 4),
        }

    sku_items = [{"sku": sku, **v} for sku, v in sku_financials.items()]

    top_sku_by_profit = sorted(sku_items, key=lambda x: float(x.get("profit", 0.0) or 0.0), reverse=True)[:20]
    negative_margin_sku = sorted(
        [x for x in sku_items if float(x.get("margin", 0.0) or 0.0) < 0],
        key=lambda x: float(x.get("profit", 0.0) or 0.0)
    )[:50]
    high_return_sku = sorted(
        [
            {**x, "return_rate": round((float(x.get("returns_qty", 0) or 0) / float(x.get("sales_qty", 0) or 1)), 4)}
            for x in sku_items
            if int(x.get("returns_qty", 0) or 0) > 0
        ],
        key=lambda x: float(x.get("return_rate", 0.0) or 0.0),
        reverse=True
    )[:50]

    profit_without_cogs = cogs_status in {"file_not_found", "file_found_not_read", "file_read_not_matched"}
    commission_delta_vs_base = round(commission - base_commission, 2)
    commission_anomaly = bool(abs(commission_delta_vs_base) > 500.0 and abs(commission_delta_vs_base) > abs(base_commission) * 0.2)
    selected_storage_source_column = None
    if storage_source_counts:
        selected_storage_source_column = sorted(storage_source_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    elif storage_source_columns_seen:
        selected_storage_source_column = sorted(storage_source_columns_seen)[0]

    turnover_wb_value: float | None
    if turnover_wb_rows_count > 0:
        turnover_wb_value = round(turnover_wb, 2)
    else:
        turnover_wb_value = None

    return {
        "rows_count": len(rows),
        "sales_qty": sales_qty,
        "returns_qty": returns_qty,
        "gross_revenue": round(gross_revenue, 2),
        "turnover_wb": turnover_wb_value,
        "turnover_wb_rows_count": int(turnover_wb_rows_count),
        "turnover_wb_note": "Оборот — сумма продаж по полю retail_price (операции Продажа).",
        "commission": round(commission, 2),
        "commission_breakdown": {
            "base_commission": round(base_commission, 2),
            "pvz_compensation": round(pvz_compensation, 2),
            "payment_services_compensation": round(payment_services_compensation, 2),
            "payment_services_compensation_amount": round(payment_services_compensation_amount, 2),
            "total_commission": round(commission, 2),
        },
        "commission_delta_vs_base": commission_delta_vs_base,
        "commission_anomaly": commission_anomaly,
        "logistics": round(logistics, 2),
        "storage": round(storage, 2),
        "storage_debug": {
            "source_column": selected_storage_source_column,
            "rows_with_storage": int(storage_rows_nonzero),
            "storage_total": round(storage, 2),
            "source_columns_detected": sorted(storage_source_columns_seen),
        },
        "penalties": round(penalties, 2),
        "payout": round(payout, 2),
        "tax_rate": float(tax_rate),
        "tax": round(tax, 2),
        "cogs_total": round(cogs_total, 2),
        "cogs_status": cogs_status,
        "profit_without_cogs": bool(profit_without_cogs),
        "cogs_diagnostics": {
            "cogs_file_found": bool(file_found),
            "cogs_rows_loaded": int(cogs_rows_loaded),
            "cogs_sku_total": int(cogs_sku_total),
            "cogs_matched_sku": int(cogs_matched_sku),
            "cogs_unmatched_sku": cogs_unmatched_sku,
            "cogs_match_key": cogs_match_key,
            "cogs_total": round(cogs_total, 2),
            "cogs_coverage_pct": round((float(cogs_matched_sku) / float(len(qty_by_sku)) * 100.0), 2) if len(qty_by_sku) > 0 else None,
        },
        "profit": round(profit, 2),
        "margin": round(margin, 4),
        "cogs_by_sku": cogs_by_sku,
        "missing_sku_qty": missing_sku_qty,

        "sku_financials": sku_financials,
        "top_sku_by_profit": top_sku_by_profit,
        "negative_margin_sku": negative_margin_sku,
        "high_return_sku": high_return_sku,
    }

