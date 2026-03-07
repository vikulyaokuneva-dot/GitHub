import json
import os
from datetime import date, timedelta
from typing import Any, Dict, Optional


def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


def save_snapshot(facts: Dict[str, Any], snapshots_dir: str) -> str:
    """Сохраняет дневной snapshot для дальнейших трендов.
    Файл: out/snapshots/YYYY-MM-DD.json
    Возвращает путь к файлу.
    """
    report_date = facts.get("date")
    if not report_date:
        raise ValueError("facts['date'] is required to save snapshot")

    path = os.path.join(snapshots_dir, f"{report_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    return path


def _safe_num(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _extract_kpis(snapshot: Dict[str, Any]) -> Dict[str, float]:
    acc = snapshot.get("account_summary") or {}
    funnel = snapshot.get("funnel_summary") or {}
    ads = snapshot.get("ads_summary") or {}
    stock = snapshot.get("stock_summary") or {}

    revenue = _safe_num(acc.get("revenue"))
    orders = _safe_num(acc.get("orders"))
    buys = _safe_num(acc.get("buys"))

    views = _safe_num(funnel.get("views"))
    add_to_cart = _safe_num(funnel.get("add_to_cart"))

    spend = _safe_num(ads.get("spend"))
    clicks = _safe_num(ads.get("clicks"))
    impressions = _safe_num(ads.get("impressions"))
    revenue_attr = _safe_num(ads.get("revenue_attr"))

    stock_units_total = _safe_num(stock.get("stock_units_total"))
    days_of_cover = _safe_num(stock.get("days_of_cover"))

    return {
        "revenue": revenue,
        "orders": orders,
        "buys": buys,
        "views": views,
        "add_to_cart": add_to_cart,
        "spend": spend,
        "clicks": clicks,
        "impressions": impressions,
        "revenue_attr": revenue_attr,
        "stock_units_total": stock_units_total,
        "days_of_cover": days_of_cover,
    }


def _aggregate(snaps: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    # snaps: {date_str: snapshot_dict}
    kpis_list = []
    for d, s in snaps.items():
        k = _extract_kpis(s)
        k["date"] = d
        kpis_list.append(k)

    if not kpis_list:
        return {"days": 0, "totals": {}, "derived": {}, "by_day": []}

    totals = {}
    for k in ["revenue", "orders", "buys", "views", "add_to_cart", "spend", "clicks", "impressions", "revenue_attr"]:
        totals[k] = sum(x.get(k, 0.0) for x in kpis_list)

    # averages for stock fields
    totals["stock_units_total_avg"] = sum(x.get("stock_units_total", 0.0) for x in kpis_list) / len(kpis_list)
    totals["days_of_cover_avg"] = sum(x.get("days_of_cover", 0.0) for x in kpis_list) / len(kpis_list)

    derived = {
        "ddr_from_total_revenue": (totals["spend"] / totals["revenue"]) if totals["revenue"] else 0.0,
        "roas_from_attr_revenue": (totals["revenue_attr"] / totals["spend"]) if totals["spend"] else 0.0,
        "cr_cart": (totals["add_to_cart"] / totals["views"]) if totals["views"] else 0.0,
        "cr_order": (totals["orders"] / totals["add_to_cart"]) if totals["add_to_cart"] else 0.0,
    }

    return {
        "days": len(kpis_list),
        "totals": {k: round(v, 4) if isinstance(v, float) else v for k, v in totals.items()},
        "derived": {k: round(v, 4) for k, v in derived.items()},
        "by_day": kpis_list,
    }


def _load_snapshots(snapshots_dir: str, from_date: date, to_date: date) -> Dict[str, Dict[str, Any]]:
    snaps: Dict[str, Dict[str, Any]] = {}
    cur = from_date
    while cur <= to_date:
        name = cur.isoformat()
        path = os.path.join(snapshots_dir, f"{name}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    snaps[name] = json.load(f)
            except Exception:
                pass
        cur += timedelta(days=1)
    return snaps


def compute_trends_7d(snapshots_dir: str, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Считает d7 vs prev7 по daily snapshot файлам.
    end_date — ISO дата, включительно (обычно facts['date']).
    """
    if end_date:
        end = _parse_date(end_date)
    else:
        end = date.today() - timedelta(days=1)

    d7_from = end - timedelta(days=6)
    prev7_to = d7_from - timedelta(days=1)
    prev7_from = prev7_to - timedelta(days=6)

    d7_snaps = _load_snapshots(snapshots_dir, d7_from, end)
    prev7_snaps = _load_snapshots(snapshots_dir, prev7_from, prev7_to)

    d7 = _aggregate(d7_snaps)
    prev7 = _aggregate(prev7_snaps)

    def delta(a: float, b: float) -> Dict[str, float]:
        # a = current, b = prev
        abs_d = a - b
        pct = (abs_d / b) if b else 0.0
        return {"abs": round(abs_d, 4), "pct": round(pct, 4)}

    delta_totals = {}
    for k in ["revenue", "orders", "buys", "views", "add_to_cart", "spend", "clicks", "impressions", "revenue_attr"]:
        a = float(d7.get("totals", {}).get(k, 0.0) or 0.0)
        b = float(prev7.get("totals", {}).get(k, 0.0) or 0.0)
        delta_totals[k] = delta(a, b)

    notes = []
    if d7["days"] < 7:
        notes.append(f"Недостаточно snapshot-данных для полного d7: найдено {d7['days']} дней из 7.")
    if prev7["days"] < 7:
        notes.append(f"Недостаточно snapshot-данных для сравнения prev7: найдено {prev7['days']} дней из 7.")

    return {
        "periods": {
            "d7": {"from": d7_from.isoformat(), "to": end.isoformat()},
            "prev7": {"from": prev7_from.isoformat(), "to": prev7_to.isoformat()},
        },
        "d7": d7,
        "prev7": prev7,
        "delta": {"totals": delta_totals},
        "notes": notes,
    }
