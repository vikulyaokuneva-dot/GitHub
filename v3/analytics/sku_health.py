from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_pct(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    if 0 <= parsed <= 1:
        return parsed * 100.0
    return parsed


def _extract_sku_rows(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [row for row in metrics if isinstance(row, dict)]
    if not isinstance(metrics, dict):
        return []

    candidates = ["sku_metrics", "items", "skus"]
    for key in candidates:
        value = metrics.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    value = metrics.get("metrics_by_sku")
    if isinstance(value, dict):
        rows: List[Dict[str, Any]] = []
        for sku, payload in value.items():
            if isinstance(payload, dict):
                row = dict(payload)
                row.setdefault("sku", str(sku))
                rows.append(row)
        return rows
    return []


def _ads_score(row: Dict[str, Any], reasons: List[str], missing_flags: List[str]) -> int:
    roi = _as_pct(row.get("roi"))
    if roi is None:
        roi = _as_pct(row.get("ads_roi"))
    ddr = _as_pct(row.get("ddr"))

    if roi is not None:
        if roi >= 150:
            reasons.append("ROI >= 150%")
            return 25
        if roi >= 100:
            reasons.append("ROI 100-149%")
            return 15
        reasons.append("ROI < 100%")
        return 5

    if ddr is not None:
        if ddr <= 15:
            reasons.append("DDR <= 15%")
            return 25
        if ddr <= 25:
            reasons.append("DDR 16-25%")
            return 15
        reasons.append("DDR > 25%")
        return 5

    # cpo / ads_spend present but not enough for robust efficiency estimate
    if _as_float(row.get("cpo")) is not None or _as_float(row.get("ads_spend")) is not None:
        reasons.append("Ads data partial (cpo/ads_spend only)")
        missing_flags.append("ads_efficiency_partial")
        return 10

    reasons.append("Ads efficiency missing")
    missing_flags.append("ads_efficiency_missing")
    return 10


def _resolve_status(score: int, profit: float) -> str:
    if score >= 75 and profit > 0:
        return "SCALE"
    if profit < 0 or score < 40:
        return "LIQUIDATE"
    if profit == 0 and 40 <= score <= 60:
        return "WATCH"
    if 40 <= score <= 74 and profit >= 0:
        return "FIX"
    return "WATCH"


def _status_actions(status: str) -> List[Dict[str, str]]:
    if status == "LIQUIDATE":
        return [
            {"priority": "P1", "title": "Снижение цены/распродажа остатков", "details": "Ускорить оборачиваемость и высвободить капитал."},
            {"priority": "P2", "title": "Отключить рекламу", "details": "Остановить неэффективные кампании до пересмотра unit-экономики."},
            {"priority": "P3", "title": "Решение: вывести из ассортимента", "details": "Проверить целесообразность дальнейших закупок SKU."},
        ]
    if status == "FIX":
        return [
            {"priority": "P1", "title": "Поднять маржу/проверить цену и себестоимость", "details": "Пересчитать юнит-экономику и целевую цену."},
            {"priority": "P2", "title": "Оптимизировать карточку (конверсия)", "details": "Улучшить контент, фото, оффер и отзывы."},
            {"priority": "P3", "title": "Точечная реклама/ключи", "details": "Оставить только высокоинтентные запросы и связки."},
        ]
    if status == "SCALE":
        return [
            {"priority": "P1", "title": "Масштабировать трафик/рекламу", "details": "Увеличивать бюджет ступенчато с контролем ROMI/DDR."},
            {"priority": "P2", "title": "Проверить остатки и поставку", "details": "Не допускать OOS при росте продаж."},
            {"priority": "P3", "title": "Расширить ключи/органику", "details": "Укрепить поисковое покрытие и SEO карточки."},
        ]
    return [
        {"priority": "P1", "title": "Собрать больше данных", "details": "Недостаточно статистики для уверенного решения."},
        {"priority": "P2", "title": "Мини-тест рекламы", "details": "Запустить ограниченный тест и измерить эффективность."},
        {"priority": "P3", "title": "Проверить остатки/дефицит", "details": "Исключить влияние out-of-stock на динамику SKU."},
    ]


def _build_item(row: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
    if not sku:
        sku = "unknown_sku"

    reasons: List[str] = []
    missing_flags: List[str] = []

    profit_raw = row.get("profit")
    if profit_raw is None:
        profit_raw = row.get("net_profit")
    profit = _as_float(profit_raw)
    if profit is None:
        profit = 0.0
        reasons.append("Profit missing, fallback to 0")
        missing_flags.append("profit_missing")

    # A) Profitability
    if profit > 0:
        score_profit = 25
        reasons.append("Profit > 0")
    elif profit == 0:
        score_profit = 10
        reasons.append("Profit = 0")
    else:
        score_profit = 0
        reasons.append("Profit < 0")

    # B) Margin
    margin = _as_pct(row.get("margin_pct"))
    if margin is None:
        margin = _as_pct(row.get("margin"))
    if margin is None:
        score_margin = 10
        reasons.append("Margin missing")
        missing_flags.append("margin_missing")
    elif margin >= 40:
        score_margin = 25
        reasons.append("Margin >= 40%")
    elif margin >= 20:
        score_margin = 15
        reasons.append("Margin 20-39%")
    elif margin >= 5:
        score_margin = 8
        reasons.append("Margin 5-19%")
    else:
        score_margin = 0
        reasons.append("Margin < 5%")

    # C) Sales velocity
    velocity = _as_float(row.get("orders"))
    if velocity is None:
        velocity = _as_float(row.get("buys"))
    if velocity is None:
        velocity = _as_float(row.get("sales_count"))
    if velocity is None:
        score_velocity = 10
        reasons.append("Sales velocity missing")
        missing_flags.append("sales_velocity_missing")
    elif velocity >= 5:
        score_velocity = 25
        reasons.append("Sales velocity >= 5")
    elif velocity >= 1:
        score_velocity = 15
        reasons.append("Sales velocity 1-4")
    else:
        score_velocity = 0
        reasons.append("Sales velocity = 0")

    # D) Ads efficiency
    score_ads = _ads_score(row, reasons, missing_flags)

    health_score = int(score_profit + score_margin + score_velocity + score_ads)
    status = _resolve_status(health_score, profit)

    if len(missing_flags) >= 2 or "profit_missing" in missing_flags:
        confidence = "low"
    elif len(missing_flags) == 1:
        confidence = "medium"
    else:
        confidence = "high"

    item = {
        "sku": sku,
        "health_score": health_score,
        "status": status,
        "confidence": confidence,
        "reasons": reasons[:8],
        "actions": _status_actions(status),
    }
    return item, profit


def compute_sku_health(facts: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    rows = _extract_sku_rows(metrics)
    items: List[Dict[str, Any]] = []
    scored_items: List[Dict[str, Any]] = []
    statuses = {"SCALE": 0, "FIX": 0, "WATCH": 0, "LIQUIDATE": 0}
    confidences = {"high": 0, "medium": 0, "low": 0}

    for row in rows:
        item, profit = _build_item(row)
        items.append(item)
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
        confidences[item["confidence"]] = confidences.get(item["confidence"], 0) + 1
        scored_items.append(
            {
                "sku": item["sku"],
                "score": item["health_score"],
                "status": item["status"],
                "profit": round(profit, 2),
            }
        )

    summary_reasons: List[str] = []
    if not rows:
        summary_reasons.append("SKU-level metrics not found in metrics.json")
        confidence = "low"
    elif confidences["low"] > 0:
        confidence = "low"
    elif confidences["medium"] > 0:
        confidence = "medium"
    else:
        confidence = "high"

    top_scale = sorted(
        [x for x in scored_items if x["status"] == "SCALE"],
        key=lambda x: (x["score"], x["profit"]),
        reverse=True,
    )[:3]
    top_liquidate = sorted(
        [x for x in scored_items if x["status"] == "LIQUIDATE"],
        key=lambda x: (x["score"], x["profit"]),
    )[:3]

    return {
        "generated_at": _utc_now_iso(),
        "seller_id": str(facts.get("seller_id") or "unknown_seller"),
        "date": str(facts.get("run_date") or facts.get("date") or ""),
        "items": items,
        "summary": {
            "total_skus": len(items),
            "SCALE": statuses["SCALE"],
            "FIX": statuses["FIX"],
            "WATCH": statuses["WATCH"],
            "LIQUIDATE": statuses["LIQUIDATE"],
            "confidence": confidence,
            "reasons": summary_reasons,
            "top_scale": top_scale,
            "top_liquidate": top_liquidate,
        },
    }
