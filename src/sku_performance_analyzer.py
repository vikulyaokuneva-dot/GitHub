# src/sku_performance_analyzer.py
"""SKU performance + ABC analysis.

Цель:
  - собрать единую метрику по каждому SKU (nmId)
  - построить ABC по прибыли

Источники (best-effort):
  - finance.sku_financials (из calc_financial_metrics)
  - sales-funnel/products (funnel_raw)
  - stocks (stocks_raw)
  - ads (ads_raw) — если доступна привязка к nmId, иначе будет 0
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def _safe_div(a: float, b: float) -> float:
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
        out: List[Dict[str, Any]] = []
        for it in obj:
            it = _try_json_loads(it)
            if isinstance(it, dict):
                out.append(it)
        return out or None

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


def _to_int(x: Any) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


def _to_float(x: Any) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _pick_funnel_stat_block(item: Dict[str, Any]) -> Dict[str, Any]:
    """seller-analytics sales-funnel/products часто отдаёт структуру:
    { product: {...}, statistic: { selected: {...}, ... } }
    """
    st = item.get("statistic")
    if isinstance(st, dict):
        selected = st.get("selected") or st.get("current") or st.get("now")
        if isinstance(selected, dict):
            return selected
    return item


def _extract_sku_from_funnel_item(item: Dict[str, Any]) -> int:
    prod = item.get("product")
    if isinstance(prod, dict):
        sku = _to_int(prod.get("nmId") or prod.get("nm_id") or prod.get("nmID") or prod.get("sku"))
        if sku:
            return sku
    return _to_int(item.get("nmId") or item.get("nm_id") or item.get("nmID") or item.get("sku"))


def _agg_funnel_per_sku(funnel_raw: Any) -> Dict[int, Dict[str, Any]]:
    items = _normalize_items(funnel_raw)
    out: Dict[int, Dict[str, Any]] = {}

    for it in items:
        if not isinstance(it, dict):
            continue
        sku = _extract_sku_from_funnel_item(it)
        if not sku:
            continue
        stat = _pick_funnel_stat_block(it)

        views = _to_int(stat.get("views") or stat.get("openCount") or stat.get("openCardCount"))
        add_to_cart = _to_int(stat.get("add_to_cart") or stat.get("cartCount") or stat.get("addToCartCount"))
        orders = _to_int(stat.get("orders") or stat.get("orderCount"))
        buys = _to_int(stat.get("buys") or stat.get("buyoutCount"))

        m = out.setdefault(sku, {"views": 0, "add_to_cart": 0, "orders": 0, "buys": 0})
        m["views"] += views
        m["add_to_cart"] += add_to_cart
        m["orders"] += orders
        m["buys"] += buys

    # derived
    for sku, m in out.items():
        v = int(m.get("views", 0) or 0)
        c = int(m.get("add_to_cart", 0) or 0)
        o = int(m.get("orders", 0) or 0)
        b = int(m.get("buys", 0) or 0)
        m["cr_cart"] = round(_safe_div(c, v), 4)
        m["cr_order"] = round(_safe_div(o, c), 4)
        m["buyout_rate"] = round(_safe_div(b, o), 4)
        m["conversion"] = round(_safe_div(b, v), 4)

    return out


def _agg_stock_per_sku(stocks_raw: Any) -> Dict[int, int]:
    items = _normalize_items(stocks_raw)
    per_sku: Dict[int, int] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        sku = _to_int(it.get("nmId") or it.get("nm_id") or it.get("nmID") or it.get("nm") or 0)
        if not sku:
            continue
        q_full = _to_int(it.get("quantityFull"))
        q = _to_int(it.get("quantity"))
        q_client = _to_int(it.get("inWayToClient"))
        q_from = _to_int(it.get("inWayFromClient"))
        qty = max(q_full, q, q + q_client + q_from)
        per_sku[sku] = per_sku.get(sku, 0) + qty
    return per_sku


def _extract_sku_from_ads_item(item: Dict[str, Any]) -> int:
    # best-effort: разные выгрузки/ответы могут содержать nmId рядом со stat
    sku = _to_int(item.get("nmId") or item.get("nm_id") or item.get("nmID") or item.get("sku"))
    if sku:
        return sku
    # иногда product может лежать как вложенный объект
    prod = item.get("product")
    if isinstance(prod, dict):
        sku = _to_int(prod.get("nmId") or prod.get("nm_id") or prod.get("sku"))
        if sku:
            return sku
    return 0


def _agg_ads_per_sku(ads_raw: Any) -> Dict[int, Dict[str, Any]]:
    items = _normalize_items(ads_raw)
    out: Dict[int, Dict[str, Any]] = {}

    def add_stat(sku: int, stat: Dict[str, Any]):
        m = out.setdefault(sku, {"spend": 0.0, "revenue_attr": 0.0, "clicks": 0, "impressions": 0})
        m["spend"] += _to_float(stat.get("spend") or stat.get("cost") or stat.get("sum"))
        m["revenue_attr"] += _to_float(stat.get("revenue") or stat.get("revenueAttr") or stat.get("orderSum"))
        m["clicks"] += _to_int(stat.get("clicks") or stat.get("click"))
        m["impressions"] += _to_int(stat.get("views") or stat.get("impressions") or stat.get("shows"))

    for it in items:
        if not isinstance(it, dict):
            continue
        sku = _extract_sku_from_ads_item(it)
        if sku:
            add_stat(sku, it)
        ds = it.get("dailyStats")
        if isinstance(ds, list):
            for d in ds:
                if not isinstance(d, dict):
                    continue
                stat = d.get("stat")
                if isinstance(stat, dict):
                    sku2 = sku or _extract_sku_from_ads_item(d) or _extract_sku_from_ads_item(stat)
                    if sku2:
                        add_stat(sku2, stat)

    # derived
    for sku, m in out.items():
        spend = float(m.get("spend", 0.0) or 0.0)
        rev = float(m.get("revenue_attr", 0.0) or 0.0)
        clicks = int(m.get("clicks", 0) or 0)
        imps = int(m.get("impressions", 0) or 0)
        m["roas"] = round(_safe_div(rev, spend), 4)
        m["ctr"] = round(_safe_div(clicks, imps), 4)
        m["cpc"] = round(_safe_div(spend, clicks), 2)
    return out


def _abc_by_profit(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # используем только положительную прибыль как "вклад" (иначе ABC ломается на минусах)
    contribs = [max(float(r.get("profit", 0.0) or 0.0), 0.0) for r in rows]
    total_pos = sum(contribs)

    rows_sorted = sorted(rows, key=lambda r: float(r.get("profit", 0.0) or 0.0), reverse=True)

    if total_pos <= 0:
        # fallback: ранжирование по profit (без долей). A=топ20%, B=след30%, C=остальное
        n = len(rows_sorted) or 1
        a_cut = max(int(round(n * 0.2)), 1)
        b_cut = max(int(round(n * 0.5)), a_cut)
        for idx, r in enumerate(rows_sorted):
            if idx < a_cut:
                r["abc"] = "A"
            elif idx < b_cut:
                r["abc"] = "B"
            else:
                r["abc"] = "C"
        summary = {"method": "rank_fallback", "total_positive_profit": round(total_pos, 2)}
        return rows_sorted, summary

    cum = 0.0
    for r in rows_sorted:
        p = max(float(r.get("profit", 0.0) or 0.0), 0.0)
        cum += p
        share = cum / total_pos
        if share <= 0.80:
            r["abc"] = "A"
        elif share <= 0.95:
            r["abc"] = "B"
        else:
            r["abc"] = "C"

    summary = {
        "method": "cumulative_profit_share",
        "total_positive_profit": round(total_pos, 2),
        "a_threshold": 0.80,
        "b_threshold": 0.95,
    }
    return rows_sorted, summary


def analyze_sku_performance(
    *,
    finance_summary: Dict[str, Any],
    funnel_raw: Any,
    stocks_raw: Any,
    ads_raw: Any,
    period_days: int = 1,
) -> Dict[str, Any]:
    sku_fin: Dict[int, Dict[str, Any]] = {}
    raw_sf = finance_summary.get("sku_financials") or {}
    if isinstance(raw_sf, dict):
        for k, v in raw_sf.items():
            try:
                sku = int(k)
            except Exception:
                continue
            if isinstance(v, dict):
                sku_fin[sku] = v

    funnel_by_sku = _agg_funnel_per_sku(funnel_raw)
    stock_by_sku = _agg_stock_per_sku(stocks_raw)
    ads_by_sku = _agg_ads_per_sku(ads_raw)

    all_skus = set(sku_fin.keys()) | set(funnel_by_sku.keys()) | set(stock_by_sku.keys()) | set(ads_by_sku.keys())

    rows: List[Dict[str, Any]] = []

    for sku in sorted(all_skus):
        fin = sku_fin.get(sku) or {}
        fun = funnel_by_sku.get(sku) or {}
        stock_qty = int(stock_by_sku.get(sku) or 0)
        ad = ads_by_sku.get(sku) or {}

        revenue = float(fin.get("net_revenue", fin.get("sales_revenue", 0.0)) or 0.0)
        profit = float(fin.get("profit", 0.0) or 0.0)
        margin = float(fin.get("margin", 0.0) or 0.0)

        orders = int(fun.get("orders", 0) or 0)
        buys = int(fun.get("buys", 0) or 0)

        ad_spend = float(ad.get("spend", 0.0) or 0.0)
        ad_rev_attr = float(ad.get("revenue_attr", 0.0) or 0.0)
        ad_profit_est = (ad_rev_attr * margin) - ad_spend if ad_spend else 0.0
        ad_roi = _safe_div(ad_profit_est, ad_spend) if ad_spend else 0.0

        buys_per_day = _safe_div(buys, float(period_days or 1))
        turnover_days = _safe_div(stock_qty, buys_per_day) if buys_per_day else 0.0

        rows.append({
            "sku": int(sku),
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 4),
            "orders": orders,
            "buyouts": buys,
            "conversion": float(fun.get("conversion", 0.0) or 0.0),
            "cr_cart": float(fun.get("cr_cart", 0.0) or 0.0),
            "cr_order": float(fun.get("cr_order", 0.0) or 0.0),
            "buyout_rate": float(fun.get("buyout_rate", 0.0) or 0.0),
            "ad_spend": round(ad_spend, 2),
            "ad_revenue_attr": round(ad_rev_attr, 2),
            "ad_roi": round(float(ad_roi or 0.0), 4),
            "stock_qty": int(stock_qty),
            "turnover_days": round(float(turnover_days or 0.0), 2),
        })

    rows_sorted, abc_meta = _abc_by_profit(rows)

    # summary by abc
    abc_agg = {"A": {"sku_count": 0, "profit": 0.0, "revenue": 0.0},
               "B": {"sku_count": 0, "profit": 0.0, "revenue": 0.0},
               "C": {"sku_count": 0, "profit": 0.0, "revenue": 0.0}}
    for r in rows_sorted:
        c = r.get("abc") or "C"
        if c not in abc_agg:
            c = "C"
        abc_agg[c]["sku_count"] += 1
        abc_agg[c]["profit"] += float(r.get("profit", 0.0) or 0.0)
        abc_agg[c]["revenue"] += float(r.get("revenue", 0.0) or 0.0)

    for c in abc_agg:
        abc_agg[c]["profit"] = round(abc_agg[c]["profit"], 2)
        abc_agg[c]["revenue"] = round(abc_agg[c]["revenue"], 2)

    top_profit = rows_sorted[:15]
    worst_profit = sorted(rows_sorted, key=lambda r: float(r.get("profit", 0.0) or 0.0))[:10]

    return {
        "period_days": int(period_days or 1),
        "abc_meta": abc_meta,
        "abc_summary": abc_agg,
        "top_profit": top_profit,
        "worst_profit": worst_profit,
        "rows": rows_sorted,
    }
