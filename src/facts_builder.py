# src/facts_builder.py
import datetime as dt
import os
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional, Tuple

from src.wb_client import WBClient
from src.ads_loader import load_ads_stats
from src.ads_keyword_analyzer import analyze_ads_keywords
from src.action_orchestrator import build_actions
from src.metrics import (
    calc_ads_metrics,
    calc_funnel_metrics,
    calc_stock_forecast,
    calc_financial_metrics,
    safe_div,
)
from src.decisions import build_decision_signals
from src.sku_performance_analyzer import analyze_sku_performance
from src.portfolio_strategy_engine import analyze_portfolio_strategy


# WB отчёты в кабинетах обычно живут в МСК
WB_TIMEZONE = ZoneInfo(os.getenv("WB_TIMEZONE", "Europe/Moscow"))

# Сколько дней назад максимум откатываем финансы, если reportDetailByPeriod пустой (204/[])
MAX_FINANCE_LAG_DAYS = int(os.getenv("WB_MAX_FINANCE_LAG_DAYS", "3"))


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _pick_realization_with_lag(
    client: WBClient,
    target_date: dt.date,
    tax_rate: float,
    max_lag_days: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    last_finance: Dict[str, Any] = {"rows_count": 0}
    last_meta: Dict[str, Any] = {"finance_date_used": None, "finance_lag_days": None}

    for lag in range(0, max_lag_days + 1):
        end_d = target_date - dt.timedelta(days=lag)
        date_from = _iso(end_d)
        date_to = _iso(end_d)

        realization_raw = client.fetch_realization_report(date_from, date_to)
        finance = calc_financial_metrics(realization_raw, tax_rate=tax_rate)

        # rows_count == 0 => WB вернул пустой отчёт (или 204)
        if int(finance.get("rows_count", 0) or 0) > 0:
            meta = {
                "finance_date_used": date_to,
                "finance_lag_days": lag,
            }
            return finance, meta

        last_finance = finance
        last_meta = {
            "finance_date_used": date_to,
            "finance_lag_days": lag,
        }

    return last_finance, last_meta


def build_facts_json() -> Dict[str, Any]:
    client = WBClient()
    tax_rate = float(os.getenv("WB_TAX_RATE", "0.06"))

    # Дневной отчёт всегда "за вчера" по МСК
    report_date = dt.datetime.now(WB_TIMEZONE).date() - dt.timedelta(days=1)
    date_from = _iso(report_date)
    date_to = _iso(report_date)

    # 1) Воронка — строго за вчера
    funnel_raw = client.fetch_sales_funnel(date_from, date_to)
    funnel = calc_funnel_metrics(funnel_raw)

    # 2) Реклама — строго за вчера (может быть пусто при 403)
    ads_raw, ads_source, manual_ads_file = load_ads_stats(client, date_from, date_to)
    ads = calc_ads_metrics(ads_raw)
    ads_keywords = analyze_ads_keywords(ads_raw)

    # 3) Остатки
    avg_daily_sales = max(float(funnel.get("buys", 0) or 0), 0.0)
    stocks_raw = client.fetch_stocks()
    stock = calc_stock_forecast(stocks_raw, avg_daily_sales=avg_daily_sales, lead_days=7, safety_days=3)

    # 4) Финансы — с лагом
    finance, finance_meta = _pick_realization_with_lag(
        client=client,
        target_date=report_date,
        tax_rate=tax_rate,
        max_lag_days=MAX_FINANCE_LAG_DAYS,
    )

    # 4.5) SKU performance + ABC (на основе finance.sku_financials + воронки/остатков/рекламы)
    # NB: привязка рекламы к SKU зависит от доступности nmId в API/ручных выгрузках.
    try:
        sku_performance = analyze_sku_performance(
            finance_summary=finance,
            funnel_raw=funnel_raw,
            stocks_raw=stocks_raw,
            ads_raw=ads_raw,
            period_days=1,
        )
        sku_performance["meta"] = {
            "finance_date_used": finance_meta.get("finance_date_used"),
            "finance_lag_days": finance_meta.get("finance_lag_days"),
        }
    except Exception:
        sku_performance = {"error": "sku_performance_failed"}

    # 4.6) Portfolio strategy engine (AI директор ассортимента)
    try:
        portfolio_strategy = analyze_portfolio_strategy(sku_performance=sku_performance)
    except Exception:
        portfolio_strategy = {"error": "portfolio_strategy_failed"}

    # --- Ads: дополнительные бизнес-метрики (оценка) ---
    # ROI/прибыль по рекламе точно посчитать нельзя без реальной атрибуции прибыли на заказ.
    # Поэтому даём ESTIMATE: attributed_revenue * account_margin - spend
    account_margin = float(finance.get("margin", 0) or 0)
    ads_spend = float(ads.get("spend", 0) or 0)
    ads_rev_attr = float(ads.get("revenue_attr", 0) or 0)

    attr_available = bool(ads_rev_attr > 0)

    # Если WB не отдал атрибуцию выручки по рекламе (revenue_attr=0),
    # то ROI/прибыль по рекламе считать нельзя (иначе будет -100% при любом spend).
    ads_profit_est = None
    ads_roi_est = None
    ads_is_profitable_est = None
    if attr_available and ads_spend > 0:
        ads_profit_est = ads_rev_attr * account_margin - ads_spend
        ads_roi_est = safe_div(ads_profit_est, ads_spend)
        ads_is_profitable_est = bool(ads_profit_est > 0)

    ads = {
        **ads,
        "attr_available": attr_available,
        "profit_est": (round(float(ads_profit_est), 2) if isinstance(ads_profit_est, (int, float)) else None),
        "roi_est": (round(float(ads_roi_est), 4) if isinstance(ads_roi_est, (int, float)) else None),
        "is_profitable_est": ads_is_profitable_est,
    }

    # --- SKU: товары без продаж, но с остатком ---
    sku_fin = (finance.get("sku_financials") or {})
    sold_skus = {int(k) for k, v in sku_fin.items() if int((v or {}).get("sales_qty", 0) or 0) > 0}

    no_sales_with_stock = []
    # WB stocks приходит построчно по складам -> агрегируем по SKU
    per_sku_qty: Dict[int, float] = {}
    if isinstance(stocks_raw, list):
        for r in stocks_raw:
            if not isinstance(r, dict):
                continue
            sku = int(r.get("nmId") or r.get("nm_id") or 0)
            if not sku:
                continue

            def f(x) -> float:
                try:
                    if x is None or x == "":
                        return 0.0
                    return float(x)
                except Exception:
                    return 0.0

            q_full = f(r.get("quantityFull"))
            q = f(r.get("quantity"))
            q_client = f(r.get("inWayToClient"))
            q_from = f(r.get("inWayFromClient"))

            # максимально “полная” оценка по строке склада
            qty_row = max(q_full, q, q + q_client + q_from)

            if qty_row > 0:
                per_sku_qty[sku] = per_sku_qty.get(sku, 0.0) + qty_row

    for sku, qty in per_sku_qty.items():
        if sku not in sold_skus and qty > 0:
            no_sales_with_stock.append({"sku": sku, "stock_qty": round(qty, 2)})

    no_sales_with_stock = sorted(
        no_sales_with_stock,
        key=lambda x: float(x.get("stock_qty", 0) or 0),
        reverse=True
    )[:50]

    # KPI по кабинету
    ctr = float(ads.get("ctr", 0) or 0)
    cpc = float(ads.get("cpc", 0) or 0)
    cr_cart = float(funnel.get("cr_cart", 0) or 0)
    cr_order = float(funnel.get("cr_order", 0) or 0)
    buyout_rate = float(funnel.get("buyout_rate", 0) or 0)

    alerts = []

    if int(finance.get("rows_count", 0) or 0) == 0:
        alerts.append({
            "type": "realization_empty",
            "severity": "high",
            "msg": (
                "WB не вернул отчёт реализации за последние дни. "
                "Финансовые цифры могут появиться с лагом 1–2 дня."
            )
        })
    elif int(finance_meta.get("finance_lag_days", 0) or 0) > 0:
        alerts.append({
            "type": "finance_lag",
            "severity": "medium",
            "msg": (
                f"Финансы WB доступны с лагом: использована дата {finance_meta.get('finance_date_used')} "
                f"(лаг {finance_meta.get('finance_lag_days')} дн.)."
            )
        })

    if finance.get("missing_sku_qty"):
        alerts.append({
            "type": "missing_cogs",
            "severity": "medium",
            "msg": (
                "Нет себестоимости для SKU: "
                f"{list(finance['missing_sku_qty'].keys())[:10]} (и др.). Прибыль может быть завышена."
            )
        })

    # Недельный отчёт (понедельник)
    weekly = None
    if report_date.weekday() == 0:  # Monday
        week_to = report_date
        week_from = week_to - dt.timedelta(days=6)
        wf = _iso(week_from)
        wt = _iso(week_to)

        funnel_w_raw = client.fetch_sales_funnel(wf, wt)
        ads_w_raw = client.fetch_ads_stats(wf, wt)

        weekly_finance = None
        weekly_meta: Optional[Dict[str, Any]] = None
        last_weekly_finance: Dict[str, Any] = {"rows_count": 0}

        for lag in range(0, MAX_FINANCE_LAG_DAYS + 1):
            end_d = week_to - dt.timedelta(days=lag)
            realization_w_raw = client.fetch_realization_report(wf, _iso(end_d))
            wf_fin = calc_financial_metrics(realization_w_raw, tax_rate=tax_rate)

            if int(wf_fin.get("rows_count", 0) or 0) > 0:
                weekly_finance = wf_fin
                weekly_meta = {
                    "finance_date_used": _iso(end_d),
                    "finance_lag_days": lag,
                }
                break

            last_weekly_finance = wf_fin
            weekly_meta = {
                "finance_date_used": _iso(end_d),
                "finance_lag_days": lag,
            }

        if weekly_finance is None:
            weekly_finance = last_weekly_finance

        weekly = {
            "period": {"from": wf, "to": wt},
            "funnel": calc_funnel_metrics(funnel_w_raw),
            "ads": calc_ads_metrics(ads_w_raw),
            "finance": weekly_finance,
            "meta": weekly_meta,
        }

    # --- Decision engine (правила) ---
    decision_signals = build_decision_signals(
        funnel=funnel,
        finance=finance,
        ads=ads,
        stock=stock,
        sku_summary={
            "top_by_profit": finance.get("top_sku_by_profit") or [],
            "negative_margin": finance.get("negative_margin_sku") or [],
            "high_return": finance.get("high_return_sku") or [],
            "no_sales_with_stock": no_sales_with_stock,
        },
    )

    weekly_decision_signals = []
    if weekly:
        weekly_decision_signals = build_decision_signals(
            funnel=weekly.get("funnel") or {},
            finance=weekly.get("finance") or {},
            ads=weekly.get("ads") or {},
            stock=stock,
            sku_summary={},
            scope="weekly",
        )

    # 8) Actions (v2): генерируем список действий. Никогда не падаем из-за оркестратора.
    try:
        actions = build_actions({
            "ads_keywords": ads_keywords,
            "stock_forecast": stock,
            "portfolio_strategy": portfolio_strategy,
        })
    except Exception:
        actions = []

    return {
        "date": str(report_date),
        "report_type": "daily",
        "timezone": str(WB_TIMEZONE),
        "tax_rate": tax_rate,

        "financial_summary": finance,

        "account_summary": {
            "revenue": float(finance.get("gross_revenue", 0) or 0),
            "orders": int(funnel.get("orders", 0) or 0),
            "buyouts": int(finance.get("sales_qty", 0) or 0),
            "buys_funnel": int(funnel.get("buys", 0) or 0),
            "returns": int(finance.get("returns_qty", 0) or 0),
            "profit": float(finance.get("profit", 0) or 0),
            "margin": float(finance.get("margin", 0) or 0),
        },

        "cabinet_metrics": {
            "ctr": ctr,
            "cpc": cpc,
            "cr_cart": cr_cart,
            "cr_order": cr_order,
            "buyout_rate": buyout_rate,
        },

        "funnel_summary": funnel,
        "ads_summary": ads,
        "ads_source": ads_source,
        "manual_ads_file": manual_ads_file,
        "ads_keywords": ads_keywords,
        "actions": actions,
        "stock_summary": stock,

        "sku_summary": {
            "top_by_profit": finance.get("top_sku_by_profit") or [],
            "negative_margin": finance.get("negative_margin_sku") or [],
            "high_return": finance.get("high_return_sku") or [],
            "no_sales_with_stock": no_sales_with_stock,
        },

        "sku_performance": sku_performance,

        "portfolio_strategy": portfolio_strategy,

        "weekly_report": weekly,
        "decision_signals": decision_signals,
        "weekly_decision_signals": weekly_decision_signals,
        "alerts_summary": alerts,

        "notes": [
            "Даты дневного отчёта считаются по МСК (WB_TIMEZONE, по умолчанию Europe/Moscow).",
            "Финансовые статьи считаются по отчету реализации (reportDetailByPeriod).",
            "Если WB не сформировал реализацию за вчера — берём последнюю доступную дату (лаг) и явно указываем это в отчёте.",
            "Прибыль = выручка - комиссия - логистика - хранение - штрафы - налог - себестоимость.",
        ],
    }
