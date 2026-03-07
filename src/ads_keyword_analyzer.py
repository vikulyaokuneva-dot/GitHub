from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from src.metrics import safe_div


def _normalize_items(raw: Any) -> List[dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        # Sometimes WB wraps
        if "data" in raw and isinstance(raw["data"], list):
            return [x for x in raw["data"] if isinstance(x, dict)]
        return [raw]
    return []


def analyze_ads_keywords(ads_raw: Any, top_n: int = 20) -> Dict[str, Any]:
    """Lightweight keyword analysis for WB ads.

    Works best with manual report that has 'keyword' column.
    With API fullstats, keyword granularity may be missing — returns empty list.
    """
    items = _normalize_items(ads_raw)
    acc = defaultdict(lambda: {"views": 0, "clicks": 0, "spend": 0.0, "orders": 0, "revenue": 0.0})

    for it in items:
        kw = (it.get("keyword") or it.get("query") or it.get("phrase") or "").strip()
        if not kw:
            continue
        views = int(it.get("views", 0) or it.get("impressions", 0) or it.get("shows", 0) or 0)
        clicks = int(it.get("clicks", 0) or it.get("click", 0) or 0)
        spend = float(it.get("spend", 0) or it.get("cost", 0) or it.get("sum", 0) or 0)
        orders = int(it.get("orders", 0) or it.get("ordersCount", 0) or 0)
        revenue = float(it.get("orderSum", 0) or it.get("revenue", 0) or it.get("revenueAttr", 0) or 0)

        a = acc[kw]
        a["views"] += views
        a["clicks"] += clicks
        a["spend"] += spend
        a["orders"] += orders
        a["revenue"] += revenue

    rows: List[Dict[str, Any]] = []
    for kw, v in acc.items():
        ctr = safe_div(v["clicks"], v["views"])
        cpc = safe_div(v["spend"], v["clicks"])
        cpa = safe_div(v["spend"], v["orders"])
        drr = safe_div(v["spend"], v["revenue"])  # spend / revenue
        rows.append({
            "keyword": kw,
            "views": v["views"],
            "clicks": v["clicks"],
            "ctr": ctr,
            "cpc": cpc,
            "orders": v["orders"],
            "cpa": cpa,
            "revenue": v["revenue"],
            "drr": drr,
        })

    rows.sort(key=lambda r: (r["spend"] if "spend" in r else 0, r["clicks"]), reverse=True)
    rows = rows[:top_n]

    # Simple labels
    for r in rows:
        r["label"] = "ok"
        if r["views"] >= 200 and r["ctr"] < 0.01:
            r["label"] = "low_ctr"
        if r["orders"] == 0 and r["spend"] > 0:
            r["label"] = "no_orders"
        if r["drr"] > 0.35 and r["revenue"] > 0:
            r["label"] = "high_drr"

    return {"top_keywords": rows, "keywords_found": len(acc)}
