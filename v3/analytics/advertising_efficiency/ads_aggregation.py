from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate_ads_by_sku(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        item = bucket.setdefault(
            sku,
            {
                "sku": sku,
                "ad_spend": 0.0,
                "impressions": 0.0,
                "clicks": 0.0,
                "orders_from_ads": 0.0,
                "buyouts_from_ads_raw": 0.0,
                "buyouts_from_ads_raw_available": False,
                "revenue_from_ads_raw": 0.0,
                "revenue_from_ads_raw_available": False,
            },
        )
        item["ad_spend"] += _as_float(row.get("ad_spend"))
        item["impressions"] += _as_float(row.get("impressions"))
        item["clicks"] += _as_float(row.get("clicks"))
        item["orders_from_ads"] += _as_float(row.get("orders"))

        buyouts = row.get("buyouts")
        if buyouts is not None:
            item["buyouts_from_ads_raw"] += _as_float(buyouts)
            item["buyouts_from_ads_raw_available"] = True

        revenue = row.get("revenue")
        if revenue is not None:
            item["revenue_from_ads_raw"] += _as_float(revenue)
            item["revenue_from_ads_raw_available"] = True

    out = list(bucket.values())
    out.sort(key=lambda item: (_as_float(item.get("ad_spend")), str(item.get("sku") or "")), reverse=True)
    return out


def aggregate_ads_by_query(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[tuple[str, str], Dict[str, Any]] = {}
    sku_set_by_query: Dict[str, set[str]] = defaultdict(set)

    for row in rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        sku = str(row.get("sku") or "").strip()
        key = (query, sku)

        item = bucket.setdefault(
            key,
            {
                "query": query,
                "sku": sku,
                "impressions": 0.0,
                "clicks": 0.0,
                "orders": 0.0,
                "buyouts_raw": 0.0,
                "buyouts_raw_available": False,
                "revenue_raw": 0.0,
                "revenue_raw_available": False,
                "ad_spend": 0.0,
                "source": str(row.get("source") or "ads_rows"),
            },
        )
        item["impressions"] += _as_float(row.get("impressions"))
        item["clicks"] += _as_float(row.get("clicks"))
        item["orders"] += _as_float(row.get("orders"))
        item["ad_spend"] += _as_float(row.get("ad_spend"))

        buyouts = row.get("buyouts")
        if buyouts is not None:
            item["buyouts_raw"] += _as_float(buyouts)
            item["buyouts_raw_available"] = True

        revenue = row.get("revenue")
        if revenue is not None:
            item["revenue_raw"] += _as_float(revenue)
            item["revenue_raw_available"] = True

        if sku:
            sku_set_by_query[query].add(sku)

    out = list(bucket.values())
    for row in out:
        query = str(row.get("query") or "")
        row["sku_count"] = len(sku_set_by_query.get(query, set()))

    out.sort(key=lambda item: (_as_float(item.get("ad_spend")), _as_float(item.get("orders"))), reverse=True)
    return out
