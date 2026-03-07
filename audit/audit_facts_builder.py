# audit/audit_facts_builder.py
import os
import datetime as dt
from zoneinfo import ZoneInfo
from typing import Any, Dict

from audit.audit_loader import (
    load_ads_xlsx,
    load_finance_xlsx,
    load_funnel_xlsx,
    load_stocks_xlsx,
    pick_first_file,
)

from src.metrics import (
    calc_ads_metrics,
    calc_funnel_metrics,
    calc_financial_metrics,
)
from src.decisions import build_decision_signals
from src.sku_performance_analyzer import analyze_sku_performance
from src.portfolio_strategy_engine import analyze_portfolio_strategy
from src.growth_engine import analyze_growth_engine
from src.action_orchestrator import build_actions


WB_TIMEZONE = ZoneInfo(os.getenv("WB_TIMEZONE", "Europe/Moscow"))


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _audit_stock_summary(
    stocks_raw: list,
    avg_daily_sales: float,
    lead_days: int = 14,
    safety_days: int = 7,
) -> dict:
    """
    Audit-mode stock summary that DOES NOT require nmId.

    Why:
      - Some WB stock exports have only supplierArticle (Артикул продавца) and total stock fields,
        without nmId (Артикул WB). In that case src.metrics.calc_stock_forecast() returns 0,
        because it aggregates by nmId only.
      - For audit, we still want account-level stock_units + rough days_of_cover.

    We assume audit.audit_loader.load_stocks_xlsx() returns rows where:
      - quantityFull contains total stock for that row (best-effort)
      - supplierArticle may exist
      - nmId may be missing/0
    """
    total_units = 0
    keys = set()

    for r in (stocks_raw or []):
        if not isinstance(r, dict):
            continue

        q = r.get("quantityFull") or r.get("quantity") or r.get("qty") or r.get("stock") or 0
        try:
            q = int(float(q or 0))
        except Exception:
            q = 0

        if q > 0:
            total_units += q

        key = r.get("nmId") or r.get("nm_id") or r.get("supplierArticle") or r.get("vendorCode")
        if key:
            keys.add(str(key))

    sku_count = len(keys)

    days_of_cover = (float(total_units) / float(avg_daily_sales)) if avg_daily_sales else 0.0
    threshold = int(lead_days + safety_days)

    return {
        "stock_units": int(total_units),
        "sku_count": int(sku_count),
        "days_of_cover": round(float(days_of_cover or 0.0), 2),
        "risk_of_oos": bool(days_of_cover != 0 and days_of_cover < threshold),
        "threshold_days": threshold,
        "items_count": int(len(stocks_raw or [])),
        "note": (
            "Остатки посчитаны по полям выгрузки (например 'Всего находится на складах'). "
            "Привязка к nmId может быть ограничена, если в файле нет 'Артикул WB'."
        ),
    }


def build_audit_facts(input_dir: str = "audit/input", period_label: str = "") -> Dict[str, Any]:
    """
    Build facts_json in the same spirit as src/facts_builder.build_facts_json,
    but from offline files and for a period (week/month/quarter).
    """
    tax_rate = float(os.getenv("WB_TAX_RATE", "0.06"))

    # --- locate input files ---
    ads_path = pick_first_file(os.path.join(input_dir, "ads"))
    stocks_path = pick_first_file(os.path.join(input_dir, "stocks"))
    finance_path = pick_first_file(os.path.join(input_dir, "finance"))
    funnel_path = pick_first_file(os.path.join(input_dir, "funnel"))

    # --- load raw blocks (lists of dicts) ---
    ads_raw = load_ads_xlsx(ads_path) if ads_path else []
    finance_raw = load_finance_xlsx(finance_path) if finance_path else []
    funnel_raw = load_funnel_xlsx(funnel_path) if funnel_path else []
    stocks_raw = load_stocks_xlsx(stocks_path) if stocks_path else []

    # --- metrics ---
    funnel = calc_funnel_metrics(funnel_raw)
    ads = calc_ads_metrics(ads_raw)
    finance = calc_financial_metrics(finance_raw, tax_rate=tax_rate)

    # period_days: best-effort from label like "2026-02-23_2026-03-01"
    period_days = 7
    if period_label and "_" in period_label:
        try:
            a, b = period_label.split("_", 1)
            d1 = dt.date.fromisoformat(a)
            d2 = dt.date.fromisoformat(b)
            period_days = max((d2 - d1).days + 1, 1)
        except Exception:
            pass

    # avg_daily_sales for stock forecast from buyouts in funnel (period totals -> convert to avg)
    avg_daily_sales = float(funnel.get("buys", 0) or 0) / float(period_days or 1)

    # IMPORTANT: audit stock summary must work even when nmId is missing in stocks export
    stock = _audit_stock_summary(stocks_raw, avg_daily_sales=avg_daily_sales, lead_days=14, safety_days=7)

    # --- SKU performance / portfolio / growth ---
    try:
        sku_performance = analyze_sku_performance(
            finance_summary=finance,
            funnel_raw=funnel_raw,
            stocks_raw=stocks_raw,
            ads_raw=ads_raw,
            period_days=period_days,
        )
    except Exception:
        sku_performance = {"error": "sku_performance_failed"}

    try:
        portfolio_strategy = analyze_portfolio_strategy(sku_performance=sku_performance)
    except Exception:
        portfolio_strategy = {"error": "portfolio_strategy_failed"}

    try:
        growth_engine_full = analyze_growth_engine(
            sku_performance=sku_performance,
            portfolio_strategy=portfolio_strategy,
        )
        growth_engine = {
            "summary": growth_engine_full.get("summary", {}),
            "top_scale": (growth_engine_full.get("top_scale", []) or [])[:10],
            "top_optimize": (growth_engine_full.get("top_optimize", []) or [])[:10],
            "top_liquidate": (growth_engine_full.get("top_liquidate", []) or [])[:10],
            "top_contribution": (growth_engine_full.get("top_contribution", []) or [])[:10],
        }
    except Exception:
        growth_engine_full = {"error": "growth_engine_failed"}
        growth_engine = {"error": "growth_engine_failed"}

    # --- decision engine ---
    decision_signals = build_decision_signals(
        funnel=funnel,
        finance=finance,
        ads=ads,
        stock=stock,
        sku_summary={
            "top_by_profit": finance.get("top_sku_by_profit") or [],
            "negative_margin": finance.get("negative_margin_sku") or [],
            "high_return": finance.get("high_return_sku") or [],
            # audit mode: we may not have nmId in stocks export; keep empty for now
            "no_sales_with_stock": [],
        },
        scope="audit",
    )

    # --- actions (rule-based orchestrator; no keywords in offline audit) ---
    try:
        actions = build_actions(
            {
                "ads_keywords": [],
                "stock_forecast": stock,
                "portfolio_strategy": portfolio_strategy,
                "growth_engine": growth_engine,
                "growth_engine_full": growth_engine_full,
            }
        )
    except Exception:
        actions = []

    # report date is "today" (generation date), but period is embedded in label
    report_date = dt.datetime.now(WB_TIMEZONE).date()

    return {
        "date": str(report_date),
        "report_type": "audit",
        "timezone": str(WB_TIMEZONE),
        "tax_rate": tax_rate,
        "period": {
            "label": (period_label or ""),
            "days": int(period_days),
        },
        "inputs": {
            "ads_file": os.path.basename(ads_path) if ads_path else "",
            "stocks_file": os.path.basename(stocks_path) if stocks_path else "",
            "finance_file": os.path.basename(finance_path) if finance_path else "",
            "funnel_file": os.path.basename(funnel_path) if funnel_path else "",
        },
        "financial_summary": finance,
        "funnel_summary": funnel,
        "ads_summary": ads,
        "stock_summary": stock,
        "sku_summary": {
            "top_by_profit": finance.get("top_sku_by_profit") or [],
            "negative_margin": finance.get("negative_margin_sku") or [],
            "high_return": finance.get("high_return_sku") or [],
        },
        "sku_performance": sku_performance,
        "portfolio_strategy": portfolio_strategy,
        "growth_engine": growth_engine,
        "growth_engine_full": growth_engine_full,
        "decision_signals": decision_signals,
        "actions": actions,
        "notes": [
            "Audit mode работает офлайн: данные берутся из выгрузок (xlsx/csv), WB API и LLM не требуются.",
            "Для больших периодов данные агрегируются до метрик и витрин, чтобы отчёт оставался компактным.",
            "Если в выгрузке остатков нет nmId (артикула WB), то SKU-level анализ остатков будет ограничен.",
        ],
    }
