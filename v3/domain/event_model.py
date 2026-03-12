from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .source_policy import SOURCE_UNKNOWN

STATUS_CONFIRMED = "confirmed"
STATUS_NOT_CONFIRMED = "not_confirmed"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"
STATUS_UNKNOWN = "unknown"


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _normalized_source(value: Any) -> str:
    out = str(value or "").strip().lower()
    return out or SOURCE_UNKNOWN


def _optional_rounded(value: Any) -> float | None:
    if value is None:
        return None
    return round(_safe_float(value), 2)


@dataclass
class OrderKpiContract:
    date: str
    orders_count: int | None
    orders_amount: float | None
    orders_count_confirmed: bool
    orders_amount_confirmed: bool
    source_count: str
    source_amount: str


@dataclass
class BuyoutKpiContract:
    date: str
    buyouts_count: int | None
    buyouts_amount: float | None
    buyouts_count_confirmed: bool
    buyouts_amount_confirmed: bool
    source_count: str
    source_amount: str


@dataclass
class FinancialKpiContract:
    date: str
    revenue: float | None
    cost_price: float | None
    wb_commission: float | None
    logistics: float | None
    storage: float | None
    penalties: float | None
    deductions: float | None
    ads_spend: float | None
    gross_profit: float | None
    net_profit: float | None
    margin_pct: float | None
    profitability_pct: float | None
    completeness_pct: float
    is_partial: bool
    confirmed: bool


def build_event_date_model(
    *,
    run_date: str,
    api_debug: Dict[str, Any],
    timezone: str,
) -> Dict[str, Any]:
    safe_api = api_debug if isinstance(api_debug, dict) else {}
    report_date = str(run_date or safe_api.get("run_date_requested") or "").strip()
    operational_date = str(safe_api.get("date_from") or report_date).strip()
    if not operational_date:
        operational_date = report_date
    tz_value = str(safe_api.get("timezone") or timezone or "Europe/Berlin").strip() or "Europe/Berlin"
    shifted = bool(safe_api.get("shifted_to_previous_day", False))
    return {
        "report_date": report_date,
        "operational_date": operational_date,
        "orders_date": str(safe_api.get("orders_date") or operational_date),
        "buyouts_date": str(safe_api.get("buyouts_date") or operational_date),
        "financial_date": str(safe_api.get("financial_date") or operational_date),
        "shifted_to_previous_day": shifted,
        "timezone": tz_value,
    }


def build_order_kpi(
    *,
    event_date_model: Dict[str, Any],
    daily_kpi: Dict[str, Any],
) -> Dict[str, Any]:
    safe_daily = daily_kpi if isinstance(daily_kpi, dict) else {}
    count_confirmed = bool(safe_daily.get("orders_count_confirmed", False))
    amount_confirmed = bool(safe_daily.get("orders_amount_confirmed", False))
    contract = OrderKpiContract(
        date=str(event_date_model.get("orders_date") or event_date_model.get("operational_date") or ""),
        orders_count=_safe_int(safe_daily.get("daily_orders_count")) if count_confirmed else None,
        orders_amount=round(_safe_float(safe_daily.get("daily_orders_amount")), 2) if amount_confirmed else None,
        orders_count_confirmed=count_confirmed,
        orders_amount_confirmed=amount_confirmed,
        source_count=_normalized_source(safe_daily.get("data_source_orders_count") or safe_daily.get("data_source_orders")),
        source_amount=_normalized_source(safe_daily.get("data_source_orders_amount")),
    )
    return asdict(contract)


def build_buyout_kpi(
    *,
    event_date_model: Dict[str, Any],
    daily_kpi: Dict[str, Any],
) -> Dict[str, Any]:
    safe_daily = daily_kpi if isinstance(daily_kpi, dict) else {}
    count_confirmed = bool(safe_daily.get("buyouts_count_confirmed", False))
    amount_confirmed = bool(safe_daily.get("buyouts_amount_confirmed", False))
    contract = BuyoutKpiContract(
        date=str(event_date_model.get("buyouts_date") or event_date_model.get("operational_date") or ""),
        buyouts_count=_safe_int(safe_daily.get("daily_buyouts_count")) if count_confirmed else None,
        buyouts_amount=round(_safe_float(safe_daily.get("daily_buyouts_amount")), 2) if amount_confirmed else None,
        buyouts_count_confirmed=count_confirmed,
        buyouts_amount_confirmed=amount_confirmed,
        source_count=_normalized_source(safe_daily.get("data_source_buyouts_count") or safe_daily.get("data_source_buyouts")),
        source_amount=_normalized_source(safe_daily.get("data_source_buyouts_amount")),
    )
    return asdict(contract)


def build_financial_kpi_contract(
    *,
    event_date_model: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    data_sources: Dict[str, Any],
) -> Dict[str, Any]:
    safe_financial = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_sources = data_sources if isinstance(data_sources, dict) else {}
    revenue_source = _normalized_source(safe_sources.get("revenue"))
    has_known_source = revenue_source != SOURCE_UNKNOWN
    is_partial = bool(safe_financial.get("is_partial", False))
    completeness_pct = round(_safe_float(safe_financial.get("completeness_pct", 0.0)), 2)
    confirmed = bool(has_known_source and not is_partial and completeness_pct >= 99.99)

    def _value(key: str) -> float | None:
        if not has_known_source:
            return None
        return round(_safe_float(safe_financial.get(key, 0.0)), 2)

    contract = FinancialKpiContract(
        date=str(event_date_model.get("financial_date") or event_date_model.get("operational_date") or ""),
        revenue=_value("revenue"),
        cost_price=_value("cost_price"),
        wb_commission=_value("wb_commission"),
        logistics=_value("logistics"),
        storage=_value("storage"),
        penalties=_value("penalties"),
        deductions=_value("deductions"),
        ads_spend=_value("ads_spend"),
        gross_profit=_value("gross_profit"),
        net_profit=_value("net_profit"),
        margin_pct=_value("margin_pct") if confirmed else None,
        profitability_pct=_value("profitability_pct") if confirmed else None,
        completeness_pct=completeness_pct,
        is_partial=is_partial,
        confirmed=confirmed,
    )
    return asdict(contract)


def build_daily_status_matrix(
    *,
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    data_quality: Dict[str, Any],
) -> Dict[str, str]:
    safe_order = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_financial = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_ads = ads_summary if isinstance(ads_summary, dict) else {}
    safe_quality = data_quality if isinstance(data_quality, dict) else {}

    def _commerce_status(*, count_confirmed: bool, amount_confirmed: bool, source_count: Any, source_amount: Any) -> str:
        if count_confirmed:
            return STATUS_CONFIRMED
        if amount_confirmed:
            return STATUS_PARTIAL
        if _normalized_source(source_count) == SOURCE_UNKNOWN and _normalized_source(source_amount) == SOURCE_UNKNOWN:
            return STATUS_NOT_CONFIRMED
        return STATUS_UNKNOWN

    orders_status = _commerce_status(
        count_confirmed=bool(safe_order.get("orders_count_confirmed", False)),
        amount_confirmed=bool(safe_order.get("orders_amount_confirmed", False)),
        source_count=safe_order.get("source_count"),
        source_amount=safe_order.get("source_amount"),
    )
    buyouts_status = _commerce_status(
        count_confirmed=bool(safe_buyout.get("buyouts_count_confirmed", False)),
        amount_confirmed=bool(safe_buyout.get("buyouts_amount_confirmed", False)),
        source_count=safe_buyout.get("source_count"),
        source_amount=safe_buyout.get("source_amount"),
    )

    if bool(safe_financial.get("confirmed", False)):
        financial_status = STATUS_CONFIRMED
    elif bool(safe_financial.get("is_partial", False)):
        financial_status = STATUS_PARTIAL
    elif safe_financial.get("revenue") is None:
        financial_status = STATUS_NOT_CONFIRMED
    else:
        financial_status = STATUS_UNKNOWN

    ads_rows = _safe_int(safe_ads.get("ads_rows", 0))
    ads_quality = str(safe_ads.get("ads_attribution_quality") or "").strip().lower()
    ads_file_detected = bool(safe_ads.get("ads_file_detected", False))
    if ads_rows > 0 and ads_quality and ads_quality != STATUS_UNKNOWN:
        ads_status = STATUS_CONFIRMED
    elif ads_rows > 0:
        ads_status = STATUS_PARTIAL
    elif ads_file_detected:
        ads_status = STATUS_MISSING
    else:
        ads_status = STATUS_MISSING

    ai_reliability = str(safe_quality.get("ai_decision_reliability") or "").strip().lower()
    if financial_status != STATUS_CONFIRMED:
        ai_reliability = "low"
    elif ai_reliability not in {"high", "medium", "low"}:
        ai_reliability = STATUS_UNKNOWN

    return {
        "orders": orders_status,
        "buyouts": buyouts_status,
        "financials": financial_status,
        "ads": ads_status,
        "ai_reliability": ai_reliability,
    }


def build_render_kpi_values(
    *,
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    daily_status_matrix: Dict[str, Any],
) -> Dict[str, float | int | None]:
    safe_order = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_financial = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_matrix = daily_status_matrix if isinstance(daily_status_matrix, dict) else {}

    orders_count = safe_order.get("orders_count") if bool(safe_order.get("orders_count_confirmed", False)) else None
    orders_amount = safe_order.get("orders_amount") if bool(safe_order.get("orders_amount_confirmed", False)) else None
    buyouts_count = safe_buyout.get("buyouts_count") if bool(safe_buyout.get("buyouts_count_confirmed", False)) else None
    buyouts_amount = safe_buyout.get("buyouts_amount") if bool(safe_buyout.get("buyouts_amount_confirmed", False)) else None

    avg_check: float | None = None
    if buyouts_count is not None and buyouts_amount is not None:
        buyouts_count_value = _safe_int(buyouts_count)
        buyouts_amount_value = _safe_float(buyouts_amount)
        avg_check = round((buyouts_amount_value / buyouts_count_value), 2) if buyouts_count_value > 0 else 0.0

    financial_status = str(safe_matrix.get("financials") or STATUS_UNKNOWN)
    revenue = _optional_rounded(safe_financial.get("revenue")) if financial_status in {STATUS_CONFIRMED, STATUS_PARTIAL} else None
    net_profit = _optional_rounded(safe_financial.get("net_profit")) if financial_status in {STATUS_CONFIRMED, STATUS_PARTIAL} else None
    gross_profit = _optional_rounded(safe_financial.get("gross_profit")) if financial_status in {STATUS_CONFIRMED, STATUS_PARTIAL} else None

    margin_pct: float | None = None
    profitability_pct: float | None = None
    if financial_status == STATUS_CONFIRMED and not bool(safe_financial.get("is_partial", False)):
        margin_pct = _optional_rounded(safe_financial.get("margin_pct"))
        profitability_pct = _optional_rounded(safe_financial.get("profitability_pct"))

    return {
        "orders_count": _safe_int(orders_count) if orders_count is not None else None,
        "orders_amount": _optional_rounded(orders_amount),
        "buyouts_count": _safe_int(buyouts_count) if buyouts_count is not None else None,
        "buyouts_amount": _optional_rounded(buyouts_amount),
        "avg_check": avg_check,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "margin_pct": margin_pct,
        "profitability_pct": profitability_pct,
    }


def _ledger_source(metric_source: str) -> str:
    source = _normalized_source(metric_source)
    mapping = {
        "orders_api": "api.orders",
        "sales_api": "api.sales",
        "realization_api": "api.realization",
        "supplier_goods": "local.supplier_goods",
        "local_report": "local.report",
        "api": "api",
        "fallback": "fallback",
        SOURCE_UNKNOWN: SOURCE_UNKNOWN,
    }
    return mapping.get(source, source)


def build_event_ledger(
    *,
    event_date_model: Dict[str, Any],
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    api_debug: Dict[str, Any],
    data_sources: Dict[str, Any],
) -> Dict[str, Any]:
    safe_event_date = event_date_model if isinstance(event_date_model, dict) else {}
    safe_order = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_financial = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_api = api_debug if isinstance(api_debug, dict) else {}
    safe_sources = data_sources if isinstance(data_sources, dict) else {}

    orders_source = _normalized_source(safe_order.get("source_count"))
    buyouts_source = _normalized_source(safe_buyout.get("source_count"))
    financial_source = _normalized_source(safe_sources.get("revenue"))

    orders_rows = _safe_int(safe_api.get("orders_rows", 0))
    if orders_source == "supplier_goods":
        orders_rows = _safe_int(safe_order.get("orders_count", 0))

    buyouts_rows = _safe_int(safe_api.get("sales_rows", 0))
    if buyouts_source == "realization_api":
        buyouts_rows = _safe_int(safe_api.get("realization_rows", 0))
    elif buyouts_source == "supplier_goods":
        buyouts_rows = _safe_int(safe_buyout.get("buyouts_count", 0))

    financial_rows = _safe_int(safe_api.get("realization_rows", 0) or safe_api.get("sales_rows", 0))
    if financial_source == "supplier_goods":
        financial_rows = _safe_int(safe_buyout.get("buyouts_count", 0))

    orders_source_label = "api.orders" if orders_source == "api" else _ledger_source(orders_source)
    buyouts_source_label = "api.sales" if buyouts_source == "api" else _ledger_source(buyouts_source)
    financial_source_label = "api.realization" if financial_source == "api" else _ledger_source(financial_source)

    return {
        "report_date": str(safe_event_date.get("report_date") or ""),
        "operational_date": str(safe_event_date.get("operational_date") or ""),
        "events": [
            {
                "event_type": "orders_snapshot",
                "event_date": str(safe_event_date.get("orders_date") or safe_event_date.get("operational_date") or ""),
                "source": orders_source_label,
                "confirmed": bool(safe_order.get("orders_count_confirmed", False)),
                "rows": orders_rows,
                "amount": _optional_rounded(safe_order.get("orders_amount")) if bool(safe_order.get("orders_amount_confirmed", False)) else None,
            },
            {
                "event_type": "buyouts_snapshot",
                "event_date": str(safe_event_date.get("buyouts_date") or safe_event_date.get("operational_date") or ""),
                "source": buyouts_source_label,
                "confirmed": bool(safe_buyout.get("buyouts_count_confirmed", False)),
                "rows": buyouts_rows,
                "amount": _optional_rounded(safe_buyout.get("buyouts_amount")) if bool(safe_buyout.get("buyouts_amount_confirmed", False)) else None,
            },
            {
                "event_type": "financial_snapshot",
                "event_date": str(safe_event_date.get("financial_date") or safe_event_date.get("operational_date") or ""),
                "source": financial_source_label,
                "confirmed": bool(safe_financial.get("confirmed", False)),
                "rows": financial_rows,
                "amount": _optional_rounded(safe_financial.get("revenue")) if bool(safe_financial.get("confirmed", False)) else None,
            },
        ],
    }
