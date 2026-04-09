"""Build unified offline WB audit facts from audit/input files."""

from __future__ import annotations

import datetime as dt
import os
import re
from math import ceil
from collections import defaultdict
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd

from audit.audit_loader import (
    FILE_TYPES,
    group_detected_files,
    parse_ads_file_with_diagnostics,
    parse_cogs_file_with_diagnostics,
    parse_finance_file_with_diagnostics,
    parse_funnel_file,
    parse_orders_file_with_diagnostics,
    parse_search_file_with_diagnostics,
    parse_stocks_file_with_diagnostics,
    scan_input_files,
)
from audit.audit_stock_parser import parse_audit_stock_history_with_diagnostics
from audit.localization_loss import estimate_total_localization_loss
from audit.logistics_model import SUPPLY_TYPE_BOX, compute_wb_logistics_estimate
from shared.logistics_reference import (
    HIGH_COEFFICIENT_ALERT,
    build_region_logistics_summary,
    flatten_warehouse_logistics_reference,
    load_warehouse_logistics_reference,
)
from shared.wb_logistics_regions import (
    high_risk_regions_by_avg,
    normalize_region_coefficients,
)
from src.metrics import calc_ads_metrics, calc_financial_metrics, calc_funnel_metrics
from src.sku_performance_analyzer import analyze_sku_performance


WB_TIMEZONE = ZoneInfo(os.getenv("WB_TIMEZONE", "Europe/Moscow"))
REQUIRED_TYPES = ("finance", "funnel", "stocks")
OPTIONAL_TYPES = ("ads", "search", "orders", "cogs")
LOCAL_MOVE_MIN_BATCH = int(os.getenv("WB_LOCAL_MOVE_MIN_BATCH", "5"))
LOGISTICS_CONFIG_FILE_NAME = "logistics_config.xlsx"
LOGISTICS_CONFIG_REL_PATH = LOGISTICS_CONFIG_FILE_NAME
LOGISTICS_CONFIG_LEGACY_REL_PATH = os.path.join("logist", LOGISTICS_CONFIG_FILE_NAME)
PREFERRED_LOGISTICS_CONFIG_SHEET = "Остатки по дням"
LOGISTICS_CONFIG_UPDATE_FREQUENCY_DAYS = 14
LOCAL_COST_PER_ORDER = 50.0
NON_LOCAL_COST_PER_ORDER = 120.0
TARGET_LOCALIZATION_PCT = 70.0


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _date_ru(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def _parse_date_ymd(text: str) -> list[dt.date]:
    out: list[dt.date] = []
    if not text:
        return out
    for m in re.finditer(r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", text):
        try:
            out.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except Exception:
            continue
    return out


def _parse_date_dmy(text: str) -> list[dt.date]:
    out: list[dt.date] = []
    if not text:
        return out
    for m in re.finditer(r"(?<!\d)(\d{1,2})[.](\d{1,2})[.](20\d{2})(?!\d)", text):
        try:
            out.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except Exception:
            continue
    return out


def _extract_dates_from_text(text: str) -> list[dt.date]:
    if not text:
        return []
    return _parse_date_ymd(text) + _parse_date_dmy(text)


def _extract_dates_from_value(value: Any) -> list[dt.date]:
    if value is None:
        return []
    if isinstance(value, dt.datetime):
        return [value.date()]
    if isinstance(value, dt.date):
        return [value]
    if isinstance(value, (int, float)):
        # Excel serial date fallback.
        num = float(value)
        if 20000 <= num <= 80000:
            try:
                return [(dt.date(1899, 12, 30) + dt.timedelta(days=int(num)))]
            except Exception:
                return []
        return []
    text = str(value).strip()
    if not text:
        return []
    dates = _extract_dates_from_text(text)
    if dates:
        return dates
    iso_candidate = text[:10]
    try:
        return [dt.date.fromisoformat(iso_candidate)]
    except Exception:
        return []


def _date_range_from_rows(
    rows: list[dict[str, Any]] | None,
    *,
    key_hints: tuple[str, ...],
) -> tuple[dt.date, dt.date] | None:
    if not rows:
        return None
    hints = tuple(_norm_text(x) for x in key_hints if _norm_text(x))
    dates: list[dt.date] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, raw_value in row.items():
            key_norm = _norm_text(key)
            if hints and not any(h in key_norm for h in hints):
                continue
            dates.extend(_extract_dates_from_value(raw_value))
    if not dates:
        return None
    return min(dates), max(dates)


def _range_days(date_from: dt.date, date_to: dt.date) -> int:
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return int((date_to - date_from).days) + 1


def _audit_kind_label(days: int) -> str:
    return "Недельный аудит" if int(days) <= 7 else "Периодический аудит"


def _derive_audit_period(
    *,
    period_label: str,
    report_date: dt.date,
    funnel_rows: list[dict[str, Any]] | None,
    orders_rows: list[dict[str, Any]] | None,
    finance_rows: list[dict[str, Any]] | None,
    selected_files: dict[str, list[str]],
    parse_diagnostics: dict[str, Any],
    period_days: int,
) -> dict[str, Any]:
    source_ranges: list[tuple[str, dt.date, dt.date]] = []
    priority = {"funnel": 0, "orders": 1, "finance": 2}

    funnel_range = _date_range_from_rows(
        funnel_rows,
        key_hints=("date", "дата", "period", "период", "dt"),
    )
    if funnel_range:
        source_ranges.append(("funnel", funnel_range[0], funnel_range[1]))

    orders_range = _date_range_from_rows(
        orders_rows,
        key_hints=("date", "дата", "order", "заказ", "period", "период", "dt"),
    )
    if orders_range:
        source_ranges.append(("orders", orders_range[0], orders_range[1]))

    finance_range = _date_range_from_rows(
        finance_rows,
        key_hints=("date", "дата", "операц", "sale", "order", "rr", "dt"),
    )
    if finance_range:
        source_ranges.append(("finance", finance_range[0], finance_range[1]))

    date_from: dt.date
    date_to: dt.date
    source_used = "fallback"

    if source_ranges:
        chosen = min(
            source_ranges,
            key=lambda x: (priority.get(x[0], 99), x[1], x[2]),
        )
        same_ranges = all((r[1], r[2]) == (chosen[1], chosen[2]) for r in source_ranges)
        if not same_ranges:
            chosen = min(
                source_ranges,
                key=lambda x: (_range_days(x[1], x[2]), priority.get(x[0], 99)),
            )
        source_used = str(chosen[0])
        date_from, date_to = chosen[1], chosen[2]
    else:
        candidates: list[dt.date] = []

        if period_label:
            candidates.extend(_extract_dates_from_text(period_label))

        for files in selected_files.values():
            if not isinstance(files, list):
                continue
            for path in files:
                txt = str(path or "")
                candidates.extend(_extract_dates_from_text(txt))

        for value in parse_diagnostics.values():
            if isinstance(value, dict):
                for inner in value.values():
                    if isinstance(inner, str):
                        candidates.extend(_extract_dates_from_text(inner))

        if candidates:
            date_from = min(candidates)
            date_to = max(candidates)
        else:
            days = max(int(period_days or 1), 1)
            date_to = report_date
            date_from = report_date - dt.timedelta(days=days - 1)

    if date_from > date_to:
        date_from, date_to = date_to, date_from
    days = _range_days(date_from, date_to)
    audit_kind = _audit_kind_label(days)

    return {
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "label_ru": f"\u0441 {_date_ru(date_from)} \u043f\u043e {_date_ru(date_to)}",
        "days": int(days),
        "audit_kind": audit_kind,
        "source": source_used,
    }


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _norm_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip().lower()
    return " ".join(text.split())


def _to_float_relaxed(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(" ", "").replace(",", ".")
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _parse_localization_pct(value: Any) -> float | None:
    if value is None:
        return None
    has_percent_sign = False
    parsed: float | None = None
    if isinstance(value, str):
        text = value.strip().replace("\xa0", " ")
        if not text:
            return None
        has_percent_sign = "%" in text
        cleaned = text.replace("%", "").replace(" ", "").replace(",", ".")
        if cleaned == "":
            return None
        try:
            parsed = float(cleaned)
        except Exception:
            return None
    else:
        parsed = _to_float_or_none(value)

    if parsed is None:
        return None

    pct = float(parsed)
    if not has_percent_sign and 0.0 <= pct <= 1.0:
        pct *= 100.0
    pct = min(max(pct, 0.0), 100.0)
    return round(pct, 2)


def _norm_key_like(value: Any) -> str:
    text = _norm_text(value)
    text = text.replace("ё", "е")
    return text


def _is_localization_key(value: Any) -> bool:
    key = _norm_key_like(value)
    if not key:
        return False
    return any(
        token in key
        for token in (
            "процент локальных заказов",
            "доля локальных заказов",
            "локализац",
            "localization",
            "local_share",
            "local share",
            "localization_pct",
        )
    )


def _extract_localization_pct_from_df(df: pd.DataFrame) -> float | None:
    if df is None or df.empty:
        return None

    work = df.fillna("")
    row_count = min(int(work.shape[0]), 60)
    col_count = min(int(work.shape[1]), 12)

    # Priority: rows with explicit localization key + neighbor value.
    for row_idx in range(row_count):
        row_values = [work.iat[row_idx, col_idx] for col_idx in range(col_count)]
        key_positions = [idx for idx, cell in enumerate(row_values) if _is_localization_key(cell)]
        if not key_positions:
            continue

        for key_pos in key_positions:
            ordered_cells = row_values[key_pos + 1 :] + row_values[:key_pos]
            for candidate in ordered_cells:
                pct = _parse_localization_pct(candidate)
                if pct is not None:
                    return pct

    # Fallback: first parseable numeric value in the sheet.
    for row_idx in range(row_count):
        for col_idx in range(col_count):
            pct = _parse_localization_pct(work.iat[row_idx, col_idx])
            if pct is not None:
                return pct
    return None


def _parse_numeric_from_config_value(value: Any) -> tuple[float | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), False
    text = str(value or "").replace("\xa0", " ").strip()
    if not text:
        return None, False
    has_percent_sign = "%" in text
    cleaned = text.replace(",", ".")
    cleaned = re.sub(r"[^0-9.+\-]", "", cleaned)
    if cleaned in {"", ".", "+", "-", "+.", "-."}:
        return None, has_percent_sign
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = parts[0] + "." + "".join(parts[1:])
    try:
        return float(cleaned), has_percent_sign
    except Exception:
        return None, has_percent_sign


def _normalize_local_order_share(value: Any) -> float | None:
    parsed, has_percent_sign = _parse_numeric_from_config_value(value)
    if parsed is None:
        return None
    share = float(parsed)
    if has_percent_sign or share > 1.0:
        share = share / 100.0
    share = min(max(share, 0.0), 1.0)
    return round(share, 4)


def _normalize_locality_index(value: Any) -> float | None:
    parsed, _ = _parse_numeric_from_config_value(value)
    if parsed is None:
        return None
    return round(float(parsed), 4)


def _normalize_irp_share(value: Any) -> float | None:
    parsed, has_percent_sign = _parse_numeric_from_config_value(value)
    if parsed is None:
        return None
    irp_share = float(parsed)
    # Config may provide IRP as percent points (0.99 / 2.15 / 0.99%) or as already normalized share (0.0099).
    if has_percent_sign or irp_share > 1.0 or irp_share >= 0.1:
        irp_share = irp_share / 100.0
    irp_share = max(irp_share, 0.0)
    return round(irp_share, 6)


def _is_local_order_share_key(key: str) -> bool:
    if not key:
        return False
    aliases = (
        "процент локальных заказов",
        "локализация",
        "процент локализации",
        "доля локализации",
        "localization",
        "local share",
        "local_order_share",
    )
    return any(alias in key for alias in aliases)


def _is_locality_index_key(key: str) -> bool:
    if not key:
        return False
    compact = re.sub(r"[^a-zа-я0-9]+", " ", key, flags=re.IGNORECASE).strip()
    return compact in {
        "ил",
        "индекс локализации",
        "locality index",
        "locality_index",
    }


def _is_irp_key(key: str) -> bool:
    if not key:
        return False
    compact = re.sub(r"[^a-zа-я0-9]+", " ", key, flags=re.IGNORECASE).strip()
    return compact in {"ирп", "irp", "sales distribution index"}


def _extract_logistics_config_from_df(df: pd.DataFrame) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "local_order_share": None,
        "locality_index": None,
        "irp": None,
    }
    if df is None or df.empty:
        return result

    work = df.fillna("")
    row_count = min(int(work.shape[0]), 400)
    col_count = int(work.shape[1])
    if col_count <= 0:
        return result

    for row_idx in range(row_count):
        raw_key = work.iat[row_idx, 0]
        raw_value = work.iat[row_idx, 1] if col_count > 1 else None
        key = _norm_key_like(raw_key)
        if not key:
            continue

        if result["local_order_share"] is None and _is_local_order_share_key(key):
            value = _normalize_local_order_share(raw_value)
            if value is not None:
                result["local_order_share"] = value

        if result["locality_index"] is None and _is_locality_index_key(key):
            value = _normalize_locality_index(raw_value)
            if value is not None:
                result["locality_index"] = value

        if result["irp"] is None and _is_irp_key(key):
            value = _normalize_irp_share(raw_value)
            if value is not None:
                result["irp"] = value

        if all(result.get(field) is not None for field in ("local_order_share", "locality_index", "irp")):
            break

    return result


def _pick_logistics_config_file_path(input_dir: str) -> str | None:
    candidates = [
        os.path.join(input_dir, LOGISTICS_CONFIG_REL_PATH),
        os.path.join(input_dir, LOGISTICS_CONFIG_LEGACY_REL_PATH),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _pick_logistics_sheet(workbook: dict[str, pd.DataFrame]) -> tuple[str | None, pd.DataFrame | None]:
    if not isinstance(workbook, dict) or not workbook:
        return None, None

    target_key = _norm_key_like(PREFERRED_LOGISTICS_CONFIG_SHEET)
    for sheet_name, sheet_df in workbook.items():
        if _norm_key_like(sheet_name) == target_key:
            return str(sheet_name), sheet_df

    first_sheet_name = next(iter(workbook.keys()))
    return str(first_sheet_name), workbook.get(first_sheet_name)


def _load_logistics_config(input_dir: str) -> dict[str, Any]:
    payload = {
        "local_order_share": None,
        "locality_index": None,
        "irp": None,
        "localization_pct": None,
        "source": LOGISTICS_CONFIG_FILE_NAME,
        "scope": "cabinet",
        "update_frequency_days": LOGISTICS_CONFIG_UPDATE_FREQUENCY_DAYS,
    }

    source_path = _pick_logistics_config_file_path(input_dir)
    if not source_path:
        return payload

    try:
        workbook = pd.read_excel(source_path, sheet_name=None, header=None)
    except Exception:
        return payload

    selected_sheet, sheet_df = _pick_logistics_sheet(workbook or {})
    if sheet_df is None:
        return payload

    extracted = _extract_logistics_config_from_df(sheet_df)
    local_order_share = _to_float_or_none(extracted.get("local_order_share"))
    locality_index = _to_float_or_none(extracted.get("locality_index"))
    irp = _to_float_or_none(extracted.get("irp"))

    payload["source"] = os.path.basename(source_path).strip() or LOGISTICS_CONFIG_FILE_NAME
    payload["source_path"] = source_path.replace("\\", "/")
    payload["sheet"] = selected_sheet
    payload["local_order_share"] = round(float(local_order_share), 4) if local_order_share is not None else None
    payload["locality_index"] = round(float(locality_index), 4) if locality_index is not None else None
    payload["irp"] = round(float(irp), 6) if irp is not None else None
    if local_order_share is not None:
        payload["localization_pct"] = round(float(local_order_share) * 100.0, 2)
    return payload


def _cabinet_orders_count(funnel_summary: dict[str, Any], financial_summary: dict[str, Any]) -> int:
    orders = _to_int(funnel_summary.get("orders"))
    if orders > 0:
        return orders
    buys = _to_int(funnel_summary.get("buys"))
    if buys > 0:
        return buys
    finance_sales = _to_int(financial_summary.get("sales_qty"))
    if finance_sales > 0:
        return finance_sales
    return 0


def _cabinet_revenue_for_irp(funnel_summary: dict[str, Any], financial_summary: dict[str, Any]) -> float | None:
    revenue = _to_float_or_none(financial_summary.get("gross_revenue"))
    if revenue is not None and revenue > 0:
        return float(revenue)
    fallback = _to_float_or_none(funnel_summary.get("revenue_buyouts"))
    if fallback is not None and fallback > 0:
        return float(fallback)
    fallback_orders = _to_float_or_none(funnel_summary.get("revenue_orders"))
    if fallback_orders is not None and fallback_orders > 0:
        return float(fallback_orders)
    return None


def _build_cabinet_logistics_summary(
    *,
    funnel_summary: dict[str, Any],
    financial_summary: dict[str, Any],
    logistics_config: dict[str, Any],
) -> dict[str, Any]:
    local_order_share = _to_float_or_none(logistics_config.get("local_order_share"))
    if local_order_share is None:
        localization_pct = _to_float_or_none(logistics_config.get("localization_pct"))
        if localization_pct is not None:
            local_order_share = max(0.0, min(1.0, float(localization_pct) / 100.0))
    else:
        local_order_share = max(0.0, min(1.0, float(local_order_share)))
    localization_pct = round(float(local_order_share) * 100.0, 2) if local_order_share is not None else None
    orders_count = _cabinet_orders_count(funnel_summary, financial_summary)

    avg_logistics_cost_est: float | None = None
    estimated_logistics_total: float | None = None
    target_avg_logistics_cost: float | None = None
    delta_vs_target_per_order: float | None = None
    potential_overpay_due_localization: float | None = None

    if local_order_share is not None:
        local_share = float(local_order_share)
        avg_logistics_cost_est = (
            local_share * LOCAL_COST_PER_ORDER + (1.0 - local_share) * NON_LOCAL_COST_PER_ORDER
        )
        estimated_logistics_total = float(avg_logistics_cost_est) * float(orders_count)

        target_share = TARGET_LOCALIZATION_PCT / 100.0
        target_avg_logistics_cost = (
            target_share * LOCAL_COST_PER_ORDER + (1.0 - target_share) * NON_LOCAL_COST_PER_ORDER
        )
        delta_vs_target_per_order = float(avg_logistics_cost_est) - float(target_avg_logistics_cost)
        potential_overpay = float(delta_vs_target_per_order) * float(orders_count)
        potential_overpay_due_localization = max(0.0, potential_overpay)

    revenue = _cabinet_revenue_for_irp(funnel_summary, financial_summary)
    logistics_fact = _to_float_or_none(financial_summary.get("logistics"))
    logistics_used = logistics_fact if (logistics_fact is not None and logistics_fact > 0) else estimated_logistics_total
    cogs = _to_float_or_none(financial_summary.get("cogs_total")) or 0.0
    commission = _to_float_or_none(financial_summary.get("commission")) or 0.0
    irp = None
    if revenue is not None and revenue > 0 and logistics_used is not None:
        irp = (float(revenue) - float(logistics_used) - float(cogs) - float(commission)) / float(revenue)

    return {
        "local_order_share": round(float(local_order_share), 4) if local_order_share is not None else None,
        "localization_pct": round(float(localization_pct), 2) if localization_pct is not None else None,
        "orders_count": int(orders_count),
        "avg_logistics_cost_est": round(float(avg_logistics_cost_est), 2) if avg_logistics_cost_est is not None else None,
        "estimated_logistics_total": round(float(estimated_logistics_total), 2)
        if estimated_logistics_total is not None
        else None,
        "local_cost_per_order": float(LOCAL_COST_PER_ORDER),
        "non_local_cost_per_order": float(NON_LOCAL_COST_PER_ORDER),
        "target_localization_pct": float(TARGET_LOCALIZATION_PCT),
        "target_avg_logistics_cost": round(float(target_avg_logistics_cost), 2)
        if target_avg_logistics_cost is not None
        else None,
        "delta_vs_target_per_order": round(float(delta_vs_target_per_order), 2)
        if delta_vs_target_per_order is not None
        else None,
        "potential_overpay_due_localization": round(float(potential_overpay_due_localization), 2)
        if potential_overpay_due_localization is not None
        else None,
        "irp": round(float(irp), 4) if irp is not None else None,
    }


def _extract_first_numeric_from_rows(
    rows: list[dict[str, Any]] | None,
    *,
    key_hints: tuple[str, ...],
    positive_only: bool = True,
) -> float | None:
    if not rows:
        return None
    normalized_hints = tuple(_norm_text(x) for x in key_hints if _norm_text(x))
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, raw_value in row.items():
            key_norm = _norm_text(key)
            if not key_norm:
                continue
            if not any(hint in key_norm for hint in normalized_hints):
                continue
            value = _to_float_relaxed(raw_value)
            if value is None:
                continue
            if positive_only and value <= 0:
                continue
            return float(value)
    return None


def _derive_funnel_impressions_and_ctr(
    *,
    funnel_summary: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    ads_summary: dict[str, Any],
) -> dict[str, Any]:
    clicks = _to_int((funnel_summary or {}).get("views"))
    if clicks <= 0:
        clicks = sum(
            max(
                _to_int(row.get("clicks"))
                or _to_int(row.get("openCardCount"))
                or 0,
                0,
            )
            for row in (funnel_rows or [])
            if isinstance(row, dict)
        )

    impressions_from_summary = _to_int((funnel_summary or {}).get("impressions"))
    impressions_from_funnel = sum(
        max(
            _to_int(row.get("impressions"))
            or _to_int(row.get("shows"))
            or _to_int(row.get("showCount"))
            or 0,
            0,
        )
        for row in (funnel_rows or [])
        if isinstance(row, dict)
    )

    impressions: int | None = None
    source = "missing"
    if impressions_from_funnel > 0:
        impressions = int(impressions_from_funnel)
        source = "funnel"
    elif impressions_from_summary > 0:
        impressions = int(impressions_from_summary)
        source = "funnel"
    else:
        ads_impressions = _to_int((ads_summary or {}).get("impressions"))
        if ads_impressions > 0:
            impressions = int(ads_impressions)
            source = "ads"

    ctr = (float(clicks) / float(impressions)) if impressions is not None and impressions > 0 else None
    return {
        "impressions": impressions,
        "ctr": round(float(ctr), 4) if ctr is not None else None,
        "impressions_source": source,
    }


def _estimate_item_price(
    *,
    funnel_summary: dict[str, Any],
    financial_summary: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    orders = _to_int((funnel_summary or {}).get("orders"))
    revenue_orders = _to_float_or_none((funnel_summary or {}).get("revenue_orders"))
    if orders > 0 and revenue_orders is not None and revenue_orders > 0:
        return round(float(revenue_orders) / float(orders), 2)

    buys = _to_int((funnel_summary or {}).get("buys"))
    revenue_buyouts = _to_float_or_none((funnel_summary or {}).get("revenue_buyouts"))
    if buys > 0 and revenue_buyouts is not None and revenue_buyouts > 0:
        return round(float(revenue_buyouts) / float(buys), 2)

    sales_qty = _to_int((financial_summary or {}).get("sales_qty"))
    gross_revenue = _to_float_or_none((financial_summary or {}).get("gross_revenue"))
    if sales_qty > 0 and gross_revenue is not None and gross_revenue > 0:
        return round(float(gross_revenue) / float(sales_qty), 2)

    row_value = _extract_first_numeric_from_rows(
        funnel_rows,
        key_hints=(
            "price",
            "item_price",
            "retail_price",
            "цена",
            "средняя цена",
        ),
        positive_only=True,
    )
    if row_value is not None:
        return round(float(row_value), 2)

    row_value = _extract_first_numeric_from_rows(
        finance_rows,
        key_hints=(
            "retail_price_withdisc_rub",
            "retail_price",
            "цена",
            "price",
        ),
        positive_only=True,
    )
    if row_value is not None:
        return round(float(row_value), 2)
    return None


def _build_sku_dimensions(stocks_rows: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    buckets: dict[int, dict[str, list[float] | bool]] = {}
    for row in stocks_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
        if sku <= 0:
            continue
        sku_key = int(sku)
        bucket = buckets.setdefault(
            sku_key,
            {
                "stocks": [],
                "calculated": [],
                "seen": True,
            },
        )
        volume = _to_float_or_none(row.get("volume_liters"))
        source = _norm_text(row.get("volume_source") or "")
        if volume is None or volume <= 0:
            continue
        if source == "calculated":
            casted = bucket.get("calculated")
            if isinstance(casted, list):
                casted.append(float(volume))
        else:
            casted = bucket.get("stocks")
            if isinstance(casted, list):
                casted.append(float(volume))

    sku_dimensions: dict[int, dict[str, Any]] = {}
    with_volume = 0
    calculated = 0
    missing = 0
    for sku_key, bucket in buckets.items():
        stocks_values = [float(x) for x in (bucket.get("stocks") or []) if float(x) > 0]
        calc_values = [float(x) for x in (bucket.get("calculated") or []) if float(x) > 0]
        if stocks_values:
            volume_liters = round(sum(stocks_values) / float(len(stocks_values)), 6)
            source = "stocks"
            with_volume += 1
        elif calc_values:
            volume_liters = round(sum(calc_values) / float(len(calc_values)), 6)
            source = "calculated"
            with_volume += 1
            calculated += 1
        else:
            volume_liters = None
            source = "missing"
            missing += 1
        sku_dimensions[sku_key] = {
            "volume_liters": volume_liters,
            "source": source,
        }

    volume_coverage = {
        "total_sku": int(len(sku_dimensions)),
        "with_volume": int(with_volume),
        "calculated": int(calculated),
        "missing": int(missing),
    }
    return sku_dimensions, volume_coverage


def _estimate_volume_liters_from_sku_dimensions(
    sku_dimensions: dict[Any, dict[str, Any]] | None,
) -> tuple[float | None, str]:
    if not isinstance(sku_dimensions, dict) or not sku_dimensions:
        return None, "missing"
    values: list[float] = []
    for item in sku_dimensions.values():
        if not isinstance(item, dict):
            continue
        parsed = _to_float_or_none(item.get("volume_liters"))
        if parsed is None or parsed <= 0:
            continue
        values.append(float(parsed))
    if not values:
        return None, "missing"
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2 == 0:
        median = (values[middle - 1] + values[middle]) / 2.0
    else:
        median = values[middle]
    return round(float(median), 4), "stocks"


def _sku_dimension_entry(sku_dimensions: dict[Any, dict[str, Any]] | None, sku: int) -> dict[str, Any]:
    if not isinstance(sku_dimensions, dict):
        return {}
    direct = sku_dimensions.get(sku)
    if isinstance(direct, dict):
        return direct
    as_str = sku_dimensions.get(str(sku))
    if isinstance(as_str, dict):
        return as_str
    return {}


def _estimate_volume_liters(
    *,
    sku_dimensions: dict[Any, dict[str, Any]] | None,
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    volume_from_stocks, _ = _estimate_volume_liters_from_sku_dimensions(sku_dimensions)
    if volume_from_stocks is not None and volume_from_stocks > 0:
        return volume_from_stocks

    key_hints = (
        "volume_liters",
        "volume_liter",
        "volume_l",
        "volume",
        "литраж",
        "литр",
        "объем",
        "объём",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=True)
        if value is not None:
            return round(float(value), 4)
    return None


def _estimate_localization_share_pct(
    *,
    local_orders_insights: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    by_region = local_orders_insights.get("by_region")
    if isinstance(by_region, list):
        local_total = 0
        non_local_total = 0
        for row in by_region:
            if not isinstance(row, dict):
                continue
            local_total += _to_int(row.get("local_orders") or row.get("orders_local"))
            non_local_total += _to_int(row.get("non_local_orders") or row.get("orders_non_local"))
        denom = local_total + non_local_total
        if denom > 0:
            return round((float(local_total) / float(denom)) * 100.0, 2)

    key_hints = (
        "localization_share_pct",
        "localization_share",
        "local_share_pct",
        "доля локализации",
        "локализация",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=False)
        if value is None:
            continue
        bounded = min(max(float(value), 0.0), 100.0)
        return round(bounded, 2)
    return None


def _estimate_warehouse_coef(
    *,
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float:
    weighted_sum = 0.0
    weighted_orders = 0
    signals = logistics_payload.get("locality_signals")
    if isinstance(signals, list):
        for item in signals:
            if not isinstance(item, dict):
                continue
            avg_coef = _to_float_or_none(item.get("avg_coefficient"))
            orders = _to_int(item.get("orders"))
            if avg_coef is None or orders <= 0:
                continue
            weighted_sum += float(avg_coef) * float(orders)
            weighted_orders += orders
    if weighted_orders > 0:
        return round(weighted_sum / float(weighted_orders), 2)

    by_region = local_orders_insights.get("by_region")
    if isinstance(by_region, list):
        values: list[float] = []
        for row in by_region:
            if not isinstance(row, dict):
                continue
            coef = _to_float_or_none(row.get("logistics_avg_coefficient"))
            if coef is not None and coef > 0:
                values.append(float(coef))
        if values:
            return round(sum(values) / float(len(values)), 2)

    key_hints = (
        "warehouse_coef",
        "warehouse_coefficient",
        "коэффициент склада",
        "коэф склада",
        "коэффициент логистики",
        "logistics_coefficient",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=True)
        if value is not None:
            return float(value)
    return 1.0


def _build_logistics_formula_model_payload(
    *,
    funnel_summary: dict[str, Any],
    financial_summary: dict[str, Any],
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
    sku_dimensions: dict[Any, dict[str, Any]],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    representative_volume, representative_volume_source = _estimate_volume_liters_from_sku_dimensions(sku_dimensions)
    volume_liters = _estimate_volume_liters(
        sku_dimensions=sku_dimensions,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    item_price = _estimate_item_price(
        funnel_summary=funnel_summary,
        financial_summary=financial_summary,
        funnel_rows=funnel_rows,
        finance_rows=finance_rows,
    )
    localization_share_pct = _estimate_localization_share_pct(
        local_orders_insights=local_orders_insights,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    warehouse_coef = _estimate_warehouse_coef(
        local_orders_insights=local_orders_insights,
        logistics_payload=logistics_payload,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    estimate = compute_wb_logistics_estimate(
        volume_liters=volume_liters,
        item_price=item_price,
        warehouse_coef=warehouse_coef,
        localization_share_pct=localization_share_pct,
        supply_type=SUPPLY_TYPE_BOX,
        is_sgt=False,
        is_courier_wb=False,
    )
    localization_share = _to_float_or_none(estimate.get("localization_share_pct"))
    if localization_share is None:
        risk_level = "unknown"
    elif localization_share >= 70.0:
        risk_level = "low"
    elif localization_share >= 40.0:
        risk_level = "medium"
    else:
        risk_level = "high"

    mode = "C"
    has_volume = bool(estimate.get("inputs_available", {}).get("volume_liters"))
    has_price = bool(estimate.get("inputs_available", {}).get("item_price"))
    has_localization = bool(estimate.get("inputs_available", {}).get("localization_share_pct"))
    if has_volume and has_price and has_localization and estimate.get("estimated_delivery_cost") is not None:
        mode = "A"
    elif has_localization and estimate.get("localization_index") is not None:
        mode = "B"

    sku_risk_rows: list[dict[str, Any]] = []
    raw_sku_localization = local_orders_insights.get("sku_localization")
    if isinstance(raw_sku_localization, list):
        for row in raw_sku_localization:
            if not isinstance(row, dict):
                continue
            sku = _to_int(row.get("sku"))
            share_pct = _to_float_or_none(row.get("localization_share_pct"))
            if sku <= 0 or share_pct is None:
                continue
            if share_pct >= 70.0:
                impact_label = "низкое"
                conclusion = "локализация высокая, влияние на удорожание ограничено"
            elif share_pct >= 40.0:
                impact_label = "умеренное"
                conclusion = "локализация средняя, стоит контролировать ИЛ/ИРП"
            elif share_pct >= 20.0:
                impact_label = "высокое"
                conclusion = "локализация слабая, логистика может заметно дорожать"
            else:
                impact_label = "критичное"
                conclusion = "локализация очень низкая, риск существенного давления на маржу"

            sku_estimate = compute_wb_logistics_estimate(
                volume_liters=None,
                item_price=None,
                warehouse_coef=1.0,
                localization_share_pct=share_pct,
            )
            sku_risk_rows.append(
                {
                    "sku": sku,
                    "localization_share_pct": round(float(share_pct), 2),
                    "localization_index": _to_float_or_none(sku_estimate.get("localization_index")),
                    "sales_distribution_index_pct": _to_float_or_none(sku_estimate.get("sales_distribution_index_pct")),
                    "impact": impact_label,
                    "conclusion": conclusion,
                }
            )

    sku_risk_rows = sorted(
        sku_risk_rows,
        key=lambda x: float(x.get("localization_share_pct") or 100.0),
    )[:5]

    estimate["source"] = "wb_formula_model_v1"
    estimate["model_version"] = "2026-04-05"
    estimate["mode"] = mode
    estimate["risk_level"] = risk_level
    estimate["sku_risk_rows"] = sku_risk_rows
    estimate["input_candidates"] = {
        "volume_liters": volume_liters,
        "volume_source": representative_volume_source if volume_liters == representative_volume else "derived",
        "item_price": item_price,
        "warehouse_coef": warehouse_coef,
        "localization_share_pct": localization_share_pct,
    }
    return estimate


def _norm_geo_compare(value: Any) -> str:
    text = _norm_text(value)
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _estimate_non_local_orders_share(
    *,
    funnel_rows: list[dict[str, Any]],
    local_orders_insights: dict[str, Any],
    localization_share_pct: float | None,
) -> float | None:
    by_region = local_orders_insights.get("by_region")
    if isinstance(by_region, list):
        local_orders = 0
        non_local_orders = 0
        for row in by_region:
            if not isinstance(row, dict):
                continue
            local_orders += _to_int(row.get("local_orders") or row.get("orders_local"))
            non_local_orders += _to_int(row.get("non_local_orders") or row.get("orders_non_local"))
        total_orders = local_orders + non_local_orders
        if total_orders > 0:
            return round(float(non_local_orders) / float(total_orders), 4)

    local_flag_aliases = ("is_local", "local_order", "isLocal", "local")
    non_local_flag_aliases = ("is_non_local", "non_local", "isNonLocal", "nonLocal")
    origin_aliases = (
        "from_region",
        "origin_region",
        "source_region",
        "shipment_region",
        "warehouse_region",
        "warehouse",
    )
    destination_aliases = (
        "to_region",
        "destination_region",
        "delivery_region",
        "region",
        "city",
    )
    total_weight = 0
    non_local_weight = 0
    for row in funnel_rows or []:
        if not isinstance(row, dict):
            continue
        orders = max(
            _to_int(row.get("orderCount") or row.get("orders")),
            _to_int(row.get("buyoutCount") or row.get("buyouts")),
            1,
        )
        local_flag: bool | None = None
        for key in local_flag_aliases:
            if key in row:
                raw = row.get(key)
                if isinstance(raw, bool):
                    local_flag = raw
                elif _to_int(raw) in {0, 1}:
                    local_flag = bool(_to_int(raw))
                break
        if local_flag is None:
            for key in non_local_flag_aliases:
                if key in row:
                    raw = row.get(key)
                    if isinstance(raw, bool):
                        local_flag = not raw
                    elif _to_int(raw) in {0, 1}:
                        local_flag = not bool(_to_int(raw))
                    break
        if local_flag is None:
            origin = ""
            destination = ""
            for key in origin_aliases:
                value = _norm_geo_compare(row.get(key))
                if value:
                    origin = value
                    break
            for key in destination_aliases:
                value = _norm_geo_compare(row.get(key))
                if value:
                    destination = value
                    break
            if origin and destination:
                local_flag = origin == destination
        if local_flag is None:
            continue
        total_weight += orders
        if not local_flag:
            non_local_weight += orders
    if total_weight > 0:
        return round(float(non_local_weight) / float(total_weight), 4)

    share = _to_float_or_none(localization_share_pct)
    if share is not None:
        return round(max(0.0, min(1.0, 1.0 - (share / 100.0))), 4)
    return None


def _build_localization_loss_payload(
    *,
    sku_rows: list[dict[str, Any]],
    financial_summary: dict[str, Any],
    funnel_summary: dict[str, Any],
    local_orders_insights: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    logistics_formula_model: dict[str, Any],
) -> dict[str, Any]:
    localization_share_pct = _to_float_or_none(logistics_formula_model.get("localization_share_pct"))
    assumptions = []
    diagnostics = logistics_formula_model.get("diagnostics")
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("assumptions"), list):
        assumptions = [str(x) for x in (diagnostics.get("assumptions") or [])]

    force_locality_index = "localization_index_from_config" in assumptions
    force_irp = "sales_distribution_index_pct_from_config" in assumptions
    forced_localization_index = _to_float_or_none(logistics_formula_model.get("localization_index")) if force_locality_index else None
    forced_sales_distribution_index_pct = (
        _to_float_or_none(logistics_formula_model.get("sales_distribution_index_pct")) if force_irp else None
    )

    non_local_orders_share = _estimate_non_local_orders_share(
        funnel_rows=funnel_rows,
        local_orders_insights=local_orders_insights,
        localization_share_pct=localization_share_pct,
    )
    if localization_share_pct is None and non_local_orders_share is not None:
        localization_share_pct = round(max(0.0, 1.0 - non_local_orders_share) * 100.0, 2)

    revenue_total = _to_float_or_none(financial_summary.get("gross_revenue"))
    if revenue_total is None or revenue_total <= 0:
        revenue_total = _to_float_or_none(funnel_summary.get("revenue_orders"))

    payload = estimate_total_localization_loss(
        sku_rows=sku_rows,
        localization_share_pct=localization_share_pct,
        non_local_orders_share=non_local_orders_share,
        default_volume_liters=_to_float_or_none(logistics_formula_model.get("volume_liters")),
        default_item_price=_to_float_or_none(logistics_formula_model.get("item_price")),
        warehouse_coef=_to_float_or_none(logistics_formula_model.get("warehouse_coef")) or 1.0,
        revenue_total=revenue_total,
        forced_localization_index=forced_localization_index,
        forced_sales_distribution_index_pct=forced_sales_distribution_index_pct,
    )
    payload["localization_share_pct"] = localization_share_pct
    return payload


def _as_sku_int_map(raw_map: dict[Any, Any] | None) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not isinstance(raw_map, dict):
        return out
    for key, value in raw_map.items():
        if not isinstance(value, dict):
            continue
        sku = _to_int(key)
        if sku <= 0:
            continue
        out[sku] = value
    return out


def _top5_risk_level(
    *,
    overpay_per_order: float | None,
    logistics_new_per_order: float | None,
    price_avg: float | None,
) -> str:
    if overpay_per_order is not None and overpay_per_order > 30.0:
        return "high"
    if (
        logistics_new_per_order is not None
        and price_avg is not None
        and price_avg > 0
        and (float(logistics_new_per_order) / float(price_avg)) > 0.20
    ):
        return "high"
    if overpay_per_order is not None and overpay_per_order >= 10.0:
        return "medium"
    return "low"


def _ads_load_by_drr(drr_sku_pct: float | None) -> str | None:
    if drr_sku_pct is None:
        return None
    value = float(drr_sku_pct)
    if value < 10.0:
        return "низкая"
    if value < 20.0:
        return "умеренная"
    if value < 30.0:
        return "высокая"
    return "критичная"


def _top5_comment_and_recommendation(
    *,
    risk_level: str,
    overpay_per_order: float | None,
    logistics_new_per_order: float | None,
    price_avg: float | None,
    localization_share_pct: float | None,
    ads_per_order: float | None,
    drr_sku_pct: float | None,
    ads_load: str | None,
    profit_per_order: float | None,
) -> tuple[str, str]:
    drr_is_high = bool(drr_sku_pct is not None and float(drr_sku_pct) >= 20.0)
    drr_is_critical = bool(drr_sku_pct is not None and float(drr_sku_pct) >= 30.0)

    if risk_level == "high":
        if overpay_per_order is not None:
            comment = (
                "Высокая логистика из-за слабой локализации. "
                f"Переплата составляет +{round(float(overpay_per_order), 2)} ₽ на заказ."
            )
        else:
            comment = "Логистика превышает 20% цены товара и давит на маржу."
        recommendation = "Перераспределить товар по складам для снижения ИЛ/ИРП."
        if drr_is_high:
            comment += " Реклама также оказывает заметное давление на маржу."
            recommendation = "Перераспределить товар по складам и проверить эффективность рекламы, сократить невыгодные запросы."
        return comment, recommendation

    if risk_level == "medium":
        if overpay_per_order is not None:
            comment = f"Есть заметное удорожание логистики: +{round(float(overpay_per_order), 2)} ₽ на заказ."
        else:
            comment = "Логистика на границе риска, нужен контроль локализации и стоимости доставки."
        recommendation = "Проверить распределение остатков и снизить долю нелокальных заказов."
        if drr_is_high:
            comment += " Дополнительно реклама заметно давит на маржу."
            recommendation = "Проверить эффективность рекламы и сократить невыгодные запросы."
        return comment, recommendation

    if drr_is_critical:
        return (
            "Товар прибыльный, но ДРР уже критичный — реклама существенно давит на маржу.",
            "Срочно проверить эффективность рекламы и сократить невыгодные запросы.",
        )

    if drr_is_high:
        return (
            "Товар прибыльный, но ДРР уже высокий — масштабировать рекламу нужно осторожно.",
            "Проверить эффективность рекламы и сократить невыгодные запросы.",
        )

    if (
        ads_per_order is not None
        and price_avg is not None
        and price_avg > 0
        and (float(ads_per_order) / float(price_avg)) > 0.20
    ):
        comment = "Рекламная нагрузка заметна относительно цены товара."
        recommendation = "Снизить рекламные расходы и оставить только эффективные кампании."
        return comment, recommendation

    if localization_share_pct is not None and localization_share_pct < 70.0:
        comment = "Товар прибыльный, но есть потенциал снижения логистики через улучшение локализации."
        recommendation = "Тестировать локальное размещение в регионах основного спроса."
        return comment, recommendation

    if profit_per_order is not None and profit_per_order > 0:
        if ads_load in {"низкая", "умеренная"}:
            return (
                f"Товар прибыльный, ДРР в норме ({ads_load}), рекламу можно усиливать по конверсионным запросам.",
                "Увеличить оборот и усилить рекламу по эффективным запросам.",
            )
        return "Товар прибыльный, логистика в норме.", "Увеличить оборот и усилить рекламу по эффективным запросам."
    return "Недостаточно данных для полной оценки логистических потерь.", "Собрать недостающие данные по объему, цене и локализации."


def _build_top5_sku_unit_economics_payload(
    *,
    sku_rows: list[dict[str, Any]],
    financial_summary: dict[str, Any],
    sku_dimensions: dict[Any, dict[str, Any]],
    wb_logistics_estimate: dict[str, Any],
    local_orders_insights: dict[str, Any],
    localization_loss: dict[str, Any],
) -> dict[str, Any]:
    sku_financials = _as_sku_int_map(financial_summary.get("sku_financials"))
    sku_by_id: dict[int, dict[str, Any]] = {}
    for row in sku_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku"))
        if sku <= 0:
            continue
        sku_by_id[sku] = row

    localization_share_by_sku: dict[int, float] = {}
    raw_localization = local_orders_insights.get("sku_localization")
    if isinstance(raw_localization, list):
        for item in raw_localization:
            if not isinstance(item, dict):
                continue
            sku = _to_int(item.get("sku"))
            share = _to_float_or_none(item.get("localization_share_pct"))
            if sku > 0 and share is not None:
                localization_share_by_sku[sku] = float(share)

    top_loss_rows = localization_loss.get("top_loss_sku") if isinstance(localization_loss.get("top_loss_sku"), list) else []
    for item in top_loss_rows:
        if not isinstance(item, dict):
            continue
        sku = _to_int(item.get("sku"))
        share = _to_float_or_none(item.get("localization_share_pct"))
        if sku > 0 and share is not None and sku not in localization_share_by_sku:
            localization_share_by_sku[sku] = float(share)

    default_localization_share = _to_float_or_none(wb_logistics_estimate.get("localization_share_pct"))
    warehouse_coef = _to_float_or_none(wb_logistics_estimate.get("warehouse_coef")) or 1.0
    cogs_total = _to_float_or_none(financial_summary.get("cogs_total"))
    profit_without_cogs = bool(financial_summary.get("profit_without_cogs"))
    cogs_status = _norm_text(financial_summary.get("cogs_status") or "")
    if "profit_without_cogs" not in financial_summary:
        profit_without_cogs = bool(cogs_total is None or cogs_total <= 0)
    if cogs_status == "partial_match":
        margin_label_default = "Маржа (частично с COGS)"
    else:
        margin_label_default = "Маржа без COGS" if profit_without_cogs else "Маржа"

    candidates: list[dict[str, Any]] = []
    all_skus = sorted(set(sku_by_id.keys()) | set(sku_financials.keys()))
    for sku in all_skus:
        row = sku_by_id.get(sku) or {}
        fin = sku_financials.get(sku) or {}
        profit = _to_float_or_none(fin.get("profit"))
        if profit is None:
            profit = _to_float_or_none(row.get("profit"))
        revenue = _to_float_or_none(fin.get("net_revenue"))
        if revenue is None or revenue <= 0:
            revenue = _to_float_or_none(fin.get("sales_revenue"))
        if revenue is None or revenue <= 0:
            revenue = _to_float_or_none(row.get("revenue"))
        if (profit is None or profit <= 0) or (revenue is None or revenue <= 0):
            continue

        orders_count = _to_int(row.get("orders"))
        if orders_count <= 0:
            orders_count = _to_int(fin.get("sales_qty"))
        buyouts_count = _to_int(row.get("buyouts"))
        if buyouts_count <= 0:
            buyouts_count = _to_int(fin.get("sales_qty"))

        candidates.append(
            {
                "sku": int(sku),
                "category": str(row.get("abc") or "N/A"),
                "revenue_total": float(revenue),
                "profit": float(profit),
                "orders_count": int(orders_count),
                "buyouts_count": int(buyouts_count),
                "logistics_total": _to_float_or_none(fin.get("logistics")),
                "ads_spend": _to_float_or_none(row.get("ad_spend")),
                "cogs": _to_float_or_none(fin.get("cogs")),
                "commission": _to_float_or_none(fin.get("commission")),
                "tax": _to_float_or_none(fin.get("tax_alloc")),
            }
        )

    top_candidates = sorted(candidates, key=lambda x: float(x.get("profit") or 0.0), reverse=True)[:5]
    if not top_candidates:
        return {
            "available": False,
            "items": [],
            "message": "Нет SKU с положительной прибылью и выручкой для блока ТОП-5.",
        }

    items: list[dict[str, Any]] = []
    for item in top_candidates:
        sku = _to_int(item.get("sku"))
        revenue_total = float(item.get("revenue_total") or 0.0)
        profit = float(item.get("profit") or 0.0)
        orders_count = _to_int(item.get("orders_count"))
        buyouts_count = _to_int(item.get("buyouts_count"))
        orders = max(orders_count, 1)
        buyouts_for_price = max(buyouts_count, 1)
        price_avg = (revenue_total / float(buyouts_for_price)) if revenue_total > 0 else None
        profit_per_order = (profit / float(orders)) if orders > 0 else None

        logistics_total = _to_float_or_none(item.get("logistics_total"))
        logistics_per_order = None
        if logistics_total is not None:
            logistics_per_order = float(logistics_total) / float(orders)

        ads_spend = _to_float_or_none(item.get("ads_spend"))
        ads_per_order = None
        if ads_spend is not None:
            ads_per_order = float(ads_spend) / float(orders)
        drr_sku_pct = None
        if ads_spend is not None and revenue_total > 0:
            drr_sku_pct = (float(ads_spend) / float(revenue_total)) * 100.0
        ads_load = _ads_load_by_drr(drr_sku_pct)
        margin_sku_pct = (float(profit) / float(revenue_total) * 100.0) if revenue_total > 0 else None

        cogs_sku = _to_float_or_none(item.get("cogs"))
        commission_sku = _to_float_or_none(item.get("commission"))
        tax_sku = _to_float_or_none(item.get("tax"))
        has_cogs_for_roi = bool(not profit_without_cogs and cogs_sku is not None)
        total_costs_sku = None
        roi_sku_pct = None
        roi_available = False
        if has_cogs_for_roi:
            total_costs_sku = (
                float(cogs_sku or 0.0)
                + float(commission_sku or 0.0)
                + float(logistics_total or 0.0)
                + float(ads_spend or 0.0)
                + float(tax_sku or 0.0)
            )
            if total_costs_sku > 0:
                roi_sku_pct = (float(profit) / float(total_costs_sku)) * 100.0
                roi_available = True

        dim_entry = _sku_dimension_entry(sku_dimensions, sku)
        volume_liters = _to_float_or_none(dim_entry.get("volume_liters"))
        localization_share = localization_share_by_sku.get(sku)
        if localization_share is None:
            localization_share = default_localization_share

        wb_estimate = compute_wb_logistics_estimate(
            volume_liters=volume_liters,
            item_price=price_avg,
            warehouse_coef=warehouse_coef,
            localization_share_pct=localization_share,
            supply_type=SUPPLY_TYPE_BOX,
            is_sgt=False,
            is_courier_wb=False,
        )

        logistics_new = _to_float_or_none(wb_estimate.get("estimated_delivery_cost"))
        logistics_base = _to_float_or_none(wb_estimate.get("neutral_estimated_delivery_cost"))
        overpay_per_order = None
        total_overpay = None
        if logistics_new is not None and logistics_base is not None:
            overpay_per_order = float(logistics_new) - float(logistics_base)
            total_overpay = overpay_per_order * float(orders)

        risk_level = _top5_risk_level(
            overpay_per_order=overpay_per_order,
            logistics_new_per_order=logistics_new,
            price_avg=price_avg,
        )
        comment, recommendation = _top5_comment_and_recommendation(
            risk_level=risk_level,
            overpay_per_order=overpay_per_order,
            logistics_new_per_order=logistics_new,
            price_avg=price_avg,
            localization_share_pct=localization_share,
            ads_per_order=ads_per_order,
            drr_sku_pct=drr_sku_pct,
            ads_load=ads_load,
            profit_per_order=profit_per_order,
        )
        if margin_sku_pct is not None:
            if margin_sku_pct >= 25.0:
                margin_comment = "Товар прибыльный, маржа комфортная."
            elif margin_sku_pct < 10.0:
                margin_comment = "Маржа ограничена, рост рекламы и логистики нужно контролировать."
            else:
                margin_comment = "Маржа рабочая, динамику логистики и рекламы нужно держать под контролем."
            if margin_comment.lower() not in str(comment).lower():
                comment = f"{comment} {margin_comment}".strip()

        if roi_available and roi_sku_pct is not None:
            if roi_sku_pct >= 30.0:
                roi_comment = "SKU хорошо окупает вложения."
            elif roi_sku_pct < 10.0:
                roi_comment = "Окупаемость слабая, масштабировать товар нужно осторожно."
                roi_recommendation = "Перед масштабированием проверить ROI по каналам рекламы и логистике SKU."
                if roi_recommendation.lower() not in str(recommendation).lower():
                    recommendation = f"{recommendation} {roi_recommendation}".strip()
            else:
                roi_comment = "Окупаемость умеренная, масштабирование требует контроля затрат."
            if roi_comment.lower() not in str(comment).lower():
                comment = f"{comment} {roi_comment}".strip()

        items.append(
            {
                "sku": sku,
                "category": str(item.get("category") or "N/A"),
                "revenue": round(revenue_total, 2),
                "profit": round(profit, 2),
                "orders": int(orders_count),
                "buyouts": int(buyouts_count),
                "price_avg": round(float(price_avg), 2) if price_avg is not None else None,
                "profit_per_order": round(float(profit_per_order), 2) if profit_per_order is not None else None,
                "logistics_per_order": round(float(logistics_per_order), 2) if logistics_per_order is not None else None,
                "logistics_new": round(float(logistics_new), 2) if logistics_new is not None else None,
                "logistics_base": round(float(logistics_base), 2) if logistics_base is not None else None,
                "overpay_per_order": round(float(overpay_per_order), 2) if overpay_per_order is not None else None,
                "total_overpay": round(float(total_overpay), 2) if total_overpay is not None else None,
                "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
                "ads_per_order": round(float(ads_per_order), 2) if ads_per_order is not None else None,
                "drr_sku_pct": round(float(drr_sku_pct), 2) if drr_sku_pct is not None else None,
                "ads_load": ads_load,
                "margin_sku_pct": round(float(margin_sku_pct), 2) if margin_sku_pct is not None else None,
                "margin_label": margin_label_default,
                "roi_sku_pct": round(float(roi_sku_pct), 2) if roi_sku_pct is not None else None,
                "roi_available": bool(roi_available),
                "risk_level": risk_level,
                "comment": comment,
                "recommendation": recommendation,
                "localization_share_pct": round(float(localization_share), 2) if localization_share is not None else None,
                "localization_index": _to_float_or_none(wb_estimate.get("localization_index")),
                "sales_distribution_index_pct": _to_float_or_none(wb_estimate.get("sales_distribution_index_pct")),
                "volume_liters": round(float(volume_liters), 4) if volume_liters is not None else None,
            }
        )

    return {
        "available": bool(items),
        "items": items,
        "warehouse_coef": round(float(warehouse_coef), 4),
        "default_localization_share_pct": round(float(default_localization_share), 2)
        if default_localization_share is not None
        else None,
        "message": "Топ-5 SKU по прибыли рассчитан с учетом юнит-экономики и логистики WB.",
    }


def _coef_pct_to_multiplier(value: Any) -> float | None:
    parsed = _to_float_or_none(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed > 10.0:
        return float(parsed / 100.0)
    return float(parsed)


def _region_risk_label(avg_pct: float | None) -> str:
    if avg_pct is None:
        return "не определен"
    if avg_pct > 150.0:
        return "высокий"
    if avg_pct > 130.0:
        return "средний"
    return "низкий"


def _regional_sensitivity_label(score: int) -> str:
    if score >= 6:
        return "критичная"
    if score >= 4:
        return "высокая"
    if score >= 2:
        return "умеренная"
    return "низкая"


def _estimate_representative_price_from_sku_rows(sku_rows: list[dict[str, Any]]) -> float | None:
    prices: list[float] = []
    for row in sku_rows or []:
        if not isinstance(row, dict):
            continue
        revenue = _to_float_or_none(row.get("revenue"))
        orders = _to_int(row.get("buyouts") or row.get("orders"))
        if revenue is None or revenue <= 0 or orders <= 0:
            continue
        prices.append(float(revenue) / float(orders))
    if not prices:
        return None
    prices = sorted(prices)
    mid = len(prices) // 2
    if len(prices) % 2 == 0:
        return round((prices[mid - 1] + prices[mid]) / 2.0, 2)
    return round(prices[mid], 2)


def _build_regional_logistics_impact_payload(
    *,
    logistics_payload: dict[str, Any],
    logistics_formula_model: dict[str, Any],
    sku_rows: list[dict[str, Any]],
    sku_dimensions: dict[Any, dict[str, Any]],
    local_orders_insights: dict[str, Any],
    localization_loss: dict[str, Any],
    top5_sku_unit_economics: dict[str, Any],
) -> dict[str, Any]:
    region_coefficients = (
        logistics_payload.get("region_coefficients")
        if isinstance(logistics_payload.get("region_coefficients"), dict)
        else {}
    )
    if not region_coefficients:
        region_coefficients = normalize_region_coefficients(
            logistics_payload.get("region_summary") if isinstance(logistics_payload.get("region_summary"), dict) else {}
        )

    high_risk_regions = (
        logistics_payload.get("regions_over_150")
        if isinstance(logistics_payload.get("regions_over_150"), list)
        else []
    )
    if not high_risk_regions:
        high_risk_regions = high_risk_regions_by_avg(region_coefficients)

    locality_signals = (
        logistics_payload.get("locality_signals")
        if isinstance(logistics_payload.get("locality_signals"), list)
        else []
    )
    known_signals: list[dict[str, Any]] = []
    for row in locality_signals:
        if not isinstance(row, dict):
            continue
        orders = _to_int(row.get("orders"))
        avg_coef = _to_float_or_none(row.get("avg_coefficient"))
        if orders <= 0 or avg_coef is None:
            continue
        known_signals.append(row)

    representative_volume = _to_float_or_none(logistics_formula_model.get("volume_liters"))
    if representative_volume is None:
        representative_volume, _ = _estimate_volume_liters_from_sku_dimensions(sku_dimensions)
    representative_price = _to_float_or_none(logistics_formula_model.get("item_price"))
    if representative_price is None:
        representative_price = _estimate_representative_price_from_sku_rows(sku_rows)
    default_localization_share = _to_float_or_none(logistics_formula_model.get("localization_share_pct"))

    total_estimated_overpay_rub = None
    region_cost_rows: list[dict[str, Any]] = []
    routes_available = bool(local_orders_insights.get("available")) and bool(local_orders_insights.get("by_region"))

    if representative_volume is not None and representative_price is not None and known_signals:
        total_overpay = 0.0
        for signal in known_signals:
            orders = _to_int(signal.get("orders"))
            avg_pct = _to_float_or_none(signal.get("avg_coefficient"))
            region_name = str(signal.get("logistics_region") or signal.get("geo_region") or "").strip()
            coef_multiplier = _coef_pct_to_multiplier(avg_pct)
            if orders <= 0 or coef_multiplier is None:
                continue

            estimated = compute_wb_logistics_estimate(
                volume_liters=representative_volume,
                item_price=representative_price,
                warehouse_coef=coef_multiplier,
                localization_share_pct=default_localization_share,
                supply_type=SUPPLY_TYPE_BOX,
            )
            baseline = compute_wb_logistics_estimate(
                volume_liters=representative_volume,
                item_price=representative_price,
                warehouse_coef=1.0,
                localization_share_pct=default_localization_share,
                supply_type=SUPPLY_TYPE_BOX,
            )
            estimated_cost = _to_float_or_none(estimated.get("estimated_delivery_cost"))
            baseline_cost = _to_float_or_none(baseline.get("estimated_delivery_cost"))
            if estimated_cost is None or baseline_cost is None:
                continue
            overpay_per_order = max(0.0, float(estimated_cost) - float(baseline_cost))
            total_overpay_region = overpay_per_order * float(orders)
            total_overpay += total_overpay_region
            region_cost_rows.append(
                {
                    "region": region_name,
                    "orders": orders,
                    "avg_pct": avg_pct,
                    "overpay_per_order": round(overpay_per_order, 2),
                    "total_overpay_rub": round(total_overpay_region, 2),
                }
            )
        if region_cost_rows:
            total_estimated_overpay_rub = round(total_overpay, 2)

    top5_rows = top5_sku_unit_economics.get("items") if isinstance(top5_sku_unit_economics.get("items"), list) else []
    top5_high_risk_skus = {
        _to_int(item.get("sku"))
        for item in top5_rows
        if isinstance(item, dict) and str(item.get("risk_level") or "").lower() in {"high", "medium"}
    }

    weighted_coef_pct = None
    if known_signals:
        weighted_sum = 0.0
        weighted_orders = 0
        for row in known_signals:
            orders = _to_int(row.get("orders"))
            avg = _to_float_or_none(row.get("avg_coefficient"))
            if orders > 0 and avg is not None:
                weighted_sum += float(avg) * float(orders)
                weighted_orders += orders
        if weighted_orders > 0:
            weighted_coef_pct = round(weighted_sum / float(weighted_orders), 2)

    sku_localization_map: dict[int, float] = {}
    raw_sku_localization = local_orders_insights.get("sku_localization")
    if isinstance(raw_sku_localization, list):
        for row in raw_sku_localization:
            if not isinstance(row, dict):
                continue
            sku = _to_int(row.get("sku"))
            share = _to_float_or_none(row.get("localization_share_pct"))
            if sku > 0 and share is not None:
                sku_localization_map[sku] = float(share)

    sku_risk_rows: list[dict[str, Any]] = []
    for row in sku_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku"))
        orders = _to_int(row.get("orders"))
        buyouts = _to_int(row.get("buyouts"))
        revenue = _to_float_or_none(row.get("revenue"))
        margin_ratio = _to_float_or_none(row.get("margin"))
        abc = str(row.get("abc") or "N/A")
        if sku <= 0 or orders <= 0 or revenue is None or revenue <= 0:
            continue

        dim_entry = _sku_dimension_entry(sku_dimensions, sku)
        volume = _to_float_or_none(dim_entry.get("volume_liters"))
        if volume is None:
            volume = _to_float_or_none(row.get("volume_liters"))
        price_avg = float(revenue) / float(max(buyouts, 1))
        localization_share = sku_localization_map.get(sku, default_localization_share)

        score = 0
        if volume is not None and volume >= 1.0:
            score += 2
        elif volume is not None and volume >= 0.5:
            score += 1
        if orders >= 30:
            score += 2
        elif orders >= 10:
            score += 1
        if margin_ratio is not None:
            if margin_ratio < 0.15:
                score += 2
            elif margin_ratio < 0.30:
                score += 1
        if abc in {"A", "B"}:
            score += 1
        if sku in top5_high_risk_skus:
            score += 1
        sensitivity = _regional_sensitivity_label(score)

        overpay_per_order = None
        total_overpay = None
        logistics_per_order = None
        if weighted_coef_pct is not None and volume is not None and price_avg > 0:
            regional = compute_wb_logistics_estimate(
                volume_liters=volume,
                item_price=price_avg,
                warehouse_coef=_coef_pct_to_multiplier(weighted_coef_pct) or 1.0,
                localization_share_pct=localization_share,
                supply_type=SUPPLY_TYPE_BOX,
            )
            baseline = compute_wb_logistics_estimate(
                volume_liters=volume,
                item_price=price_avg,
                warehouse_coef=1.0,
                localization_share_pct=localization_share,
                supply_type=SUPPLY_TYPE_BOX,
            )
            logistics_per_order = _to_float_or_none(regional.get("estimated_delivery_cost"))
            regional_base = _to_float_or_none(baseline.get("estimated_delivery_cost"))
            if logistics_per_order is not None and regional_base is not None:
                overpay_per_order = max(0.0, float(logistics_per_order) - float(regional_base))
                total_overpay = overpay_per_order * float(orders)

        region_risk = _region_risk_label(weighted_coef_pct)
        if region_risk == "не определен":
            region_risk = "высокий" if high_risk_regions else "средний"
        if overpay_per_order is not None and overpay_per_order > 30.0:
            conclusion = "Высокая переплата на логистике при текущей региональной нагрузке."
        elif sensitivity in {"критичная", "высокая"}:
            conclusion = "SKU чувствителен к дорогим направлениям; важно контролировать размещение."
        else:
            conclusion = "Существенных признаков критичной региональной переплаты не выявлено."

        sku_risk_rows.append(
            {
                "sku": sku,
                "abc": abc,
                "orders": orders,
                "logistics_per_order": round(float(logistics_per_order), 2) if logistics_per_order is not None else None,
                "region_risk": region_risk,
                "sensitivity": sensitivity,
                "overpay_rub": round(float(total_overpay), 2) if total_overpay is not None else None,
                "conclusion": conclusion,
            }
        )

    if total_estimated_overpay_rub is not None:
        sku_risk_rows = sorted(
            sku_risk_rows,
            key=lambda x: float(x.get("overpay_rub") or 0.0),
            reverse=True,
        )
    else:
        sensitivity_order = {"критичная": 3, "высокая": 2, "умеренная": 1, "низкая": 0}
        sku_risk_rows = sorted(
            sku_risk_rows,
            key=lambda x: (sensitivity_order.get(str(x.get("sensitivity")), 0), _to_int(x.get("orders"))),
            reverse=True,
        )
    top_sku_by_regional_risk = sku_risk_rows[:5]

    recommendations: list[dict[str, Any]] = []
    top_sku_preview = [str(_to_int(item.get("sku"))) for item in top_sku_by_regional_risk[:3] if _to_int(item.get("sku")) > 0]
    if total_estimated_overpay_rub is not None and total_estimated_overpay_rub > 0:
        sku_text = ", ".join(top_sku_preview) if top_sku_preview else "A/B SKU"
        recommendations.append(
            {
                "priority": "P0",
                "action": f"Тестово перераспределить SKU {sku_text} ближе к регионам спроса.",
                "why": f"По оценке региональных коэффициентов переплата за период составляет ~{round(float(total_estimated_overpay_rub), 2)} RUB.",
                "expected_effect": "Снижение удельной логистики и защита маржи на оборотных позициях.",
            }
        )

    non_local_share = _to_float_or_none(localization_loss.get("non_local_orders_share"))
    if non_local_share is not None and non_local_share > 0.4:
        recommendations.append(
            {
                "priority": "P1",
                "action": "Пересмотреть карту распределения остатков по регионам с высоким нелокальным спросом.",
                "why": f"Доля нелокальных заказов: {round(float(non_local_share) * 100.0, 1)}%.",
                "expected_effect": "Снижение доли дорогих маршрутов и стабильнее экономика доставки.",
            }
        )

    if high_risk_regions:
        recommendations.append(
            {
                "priority": "P1",
                "action": "При ограниченном бюджете в первую очередь перераспределять A-SKU и сильные B-SKU.",
                "why": f"Высокий риск удорожания по направлениям: {', '.join(str(x) for x in high_risk_regions[:3])}.",
                "expected_effect": "Быстрый эффект на маржу при минимальном объеме перемещений.",
            }
        )

    if not routes_available:
        recommendations.append(
            {
                "priority": "P2",
                "action": "Загрузить маршруты/географию заказов для точного SKU→регион расчета потерь.",
                "why": "Без маршрутных данных региональная оценка выполняется в эвристическом режиме.",
                "expected_effect": "Переход от risk-map к точной рублевой оценке по направлениям.",
            }
        )

    missing_inputs: list[str] = []
    if not region_coefficients:
        missing_inputs.append("region_coefficients")
    if not known_signals:
        missing_inputs.append("order_geography")
    if representative_volume is None:
        missing_inputs.append("volume_liters")
    if representative_price is None:
        missing_inputs.append("item_price")
    if default_localization_share is None:
        missing_inputs.append("localization_share_pct")

    if total_estimated_overpay_rub is not None:
        mode = "full_rub"
        status = "ok" if not missing_inputs else "partial"
    elif region_coefficients or high_risk_regions:
        mode = "risk_only"
        status = "partial"
    else:
        mode = "insufficient_data"
        status = "insufficient_data"

    return {
        "status": status,
        "mode": mode,
        "high_risk_regions": high_risk_regions,
        "top_sku_by_regional_risk": top_sku_by_regional_risk,
        "total_estimated_overpay_rub": total_estimated_overpay_rub,
        "missing_inputs": missing_inputs,
        "routes_available": routes_available,
        "weighted_region_coef_pct": weighted_coef_pct,
        "representative_volume_liters": representative_volume,
        "representative_price": representative_price,
        "recommendations": recommendations[:4],
        "region_cost_rows": sorted(
            region_cost_rows,
            key=lambda x: float(x.get("total_overpay_rub") or 0.0),
            reverse=True,
        )[:10],
    }


def _geo_label(row: dict[str, Any]) -> str:
    for key in ("region", "city", "warehouse", "cluster", "federal_district"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_local_orders_insights(
    *,
    orders_rows: list[dict[str, Any]],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    orders_by_sku_region: dict[tuple[int, str], int] = defaultdict(int)
    total_orders_by_sku: dict[int, int] = defaultdict(int)
    total_orders_by_region: dict[str, int] = defaultdict(int)
    total_buyouts_by_region: dict[str, int] = defaultdict(int)
    local_orders_by_region: dict[str, int] = defaultdict(int)
    non_local_orders_by_region: dict[str, int] = defaultdict(int)
    stock_by_sku_region: dict[tuple[int, str], int] = defaultdict(int)
    stock_by_region: dict[str, int] = defaultdict(int)
    non_local_orders_by_sku: dict[int, int] = defaultdict(int)
    customer_region_by_sku: dict[tuple[int, str], int] = defaultdict(int)
    sku_orders_with_routes: dict[int, int] = defaultdict(int)

    preferred_orders_source = "orders_feed"
    raw_orders_rows = orders_rows or []
    if not raw_orders_rows:
        preferred_orders_source = "funnel"
        raw_orders_rows = funnel_rows or []

    origin_aliases = (
        "warehouse_region",
        "origin_region",
        "from_region",
        "source_region",
        "shipment_region",
        "warehouse",
    )
    destination_aliases = (
        "customer_region",
        "destination_region",
        "to_region",
        "delivery_region",
        "region",
        "city",
    )
    route_rows_with_origin_destination = 0
    route_rows_non_local = 0
    orders_rows_scanned = 0
    orders_rows_with_geo = 0
    for row in raw_orders_rows:
        if not isinstance(row, dict):
            continue
        orders_rows_scanned += 1
        sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
        orders = _to_int(row.get("orderCount") or row.get("orders") or row.get("quantity"))
        buyouts = _to_int(row.get("buyoutCount") or row.get("buyouts") or row.get("buys"))
        if orders <= 0 and preferred_orders_source == "orders_feed":
            orders = 1
        geo = _geo_label(row)
        if sku <= 0 or (orders <= 0 and buyouts <= 0):
            continue
        if not geo:
            continue
        orders_rows_with_geo += 1
        if orders > 0:
            orders_by_sku_region[(sku, geo)] += orders
            total_orders_by_sku[sku] += orders
            total_orders_by_region[geo] += orders
        if buyouts > 0:
            total_buyouts_by_region[geo] += buyouts

        origin_region = ""
        destination_region = ""
        for key in origin_aliases:
            value = str(row.get(key) or "").strip()
            if value:
                origin_region = value
                break
        for key in destination_aliases:
            value = str(row.get(key) or "").strip()
            if value:
                destination_region = value
                break

        origin_norm = _norm_geo_compare(origin_region)
        destination_norm = _norm_geo_compare(destination_region)
        if origin_norm and destination_norm:
            route_rows_with_origin_destination += 1
            sku_orders_with_routes[sku] += orders
            customer_region_by_sku[(sku, destination_region)] += orders
            if origin_norm == destination_norm:
                local_orders_by_region[destination_region] += orders
            else:
                route_rows_non_local += 1
                non_local_orders_by_region[destination_region] += orders
                non_local_orders_by_sku[sku] += orders

    stock_rows_scanned = 0
    stock_rows_with_geo = 0
    for row in stocks_rows or []:
        if not isinstance(row, dict):
            continue
        stock_rows_scanned += 1
        sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
        geo = _geo_label(row)
        qty = _to_int(row.get("quantityFull") or row.get("quantity") or row.get("qty") or row.get("stock"))
        if sku <= 0 or not geo:
            continue
        stock_rows_with_geo += 1
        qty = max(qty, 0)
        stock_by_sku_region[(sku, geo)] += qty
        stock_by_region[geo] += qty

    total_orders = sum(total_orders_by_region.values())
    total_buyouts = sum(total_buyouts_by_region.values())
    if total_orders <= 0 and total_buyouts <= 0:
        return {
            "available": False,
            "message": "нет данных по географии заказов",
            "by_region": [],
            "by_sku": [],
            "orders_with_geo": [],
            "sku_non_local_available": False,
            "sku_non_local_actions": [],
            "recommendations": [],
            "diagnostics": {
                "orders_rows_scanned": int(orders_rows_scanned),
                "orders_rows_with_geo": int(orders_rows_with_geo),
                "orders_geo_source": preferred_orders_source,
                "route_rows_with_origin_destination": int(route_rows_with_origin_destination),
                "route_rows_non_local": int(route_rows_non_local),
                "stock_rows_scanned": int(stock_rows_scanned),
                "stock_rows_with_geo": int(stock_rows_with_geo),
                "required_fields": [
                    "SKU (nmId)",
                    "region/city/warehouse for orders",
                    "buyouts quantity",
                ],
                "required_source_hint": "WB выгрузка заказов с географией доставки (регион/город) по SKU за период.",
            },
        }

    by_region = []
    region_keys = set(total_orders_by_region.keys()) | set(total_buyouts_by_region.keys())
    sorted_regions = sorted(
        region_keys,
        key=lambda region: (
            int(total_buyouts_by_region.get(region) or 0),
            int(total_orders_by_region.get(region) or 0),
        ),
        reverse=True,
    )
    for region in sorted_regions:
        region_orders = int(total_orders_by_region.get(region) or 0)
        region_buyouts = int(total_buyouts_by_region.get(region) or 0)
        share = (
            (float(region_buyouts) / float(total_buyouts)) * 100.0
            if total_buyouts > 0 and region_buyouts > 0
            else None
        )
        by_region.append(
            {
                "region": region,
                "orders": int(region_orders),
                "buyouts": int(region_buyouts),
                "share_pct": round(share, 1) if share is not None else None,
                "stock_qty": int(stock_by_region.get(region) or 0) if stock_rows_with_geo > 0 else None,
                "local_orders": int(local_orders_by_region.get(region) or 0) if route_rows_with_origin_destination > 0 else None,
                "non_local_orders": int(non_local_orders_by_region.get(region) or 0)
                if route_rows_with_origin_destination > 0
                else None,
            }
        )

    by_sku = []
    orders_with_geo: list[dict[str, Any]] = []
    for sku, sku_orders in sorted(total_orders_by_sku.items(), key=lambda x: x[1], reverse=True):
        regions = []
        for (s, region), region_orders in orders_by_sku_region.items():
            if s != sku:
                continue
            orders_with_geo.append(
                {
                    "sku": int(sku),
                    "region": str(region),
                    "orders": int(region_orders),
                }
            )
            share = (float(region_orders) / float(sku_orders)) * 100.0 if sku_orders > 0 else 0.0
            regions.append(
                {
                    "region": region,
                    "orders": int(region_orders),
                    "share_pct": round(share, 1),
                    "stock_qty": int(stock_by_sku_region.get((sku, region)) or 0) if stock_rows_with_geo > 0 else None,
                }
            )
        regions = sorted(regions, key=lambda x: x["orders"], reverse=True)
        by_sku.append(
            {
                "sku": int(sku),
                "total_orders": int(sku_orders),
                "regions": regions[:10],
            }
        )

    sku_non_local_actions: list[dict[str, Any]] = []
    for sku, non_local_orders in sorted(non_local_orders_by_sku.items(), key=lambda x: x[1], reverse=True):
        if non_local_orders <= 0:
            continue
        total_orders = int(total_orders_by_sku.get(sku) or 0)
        top_region = ""
        top_region_orders = 0
        for (sku_key, region), region_orders in customer_region_by_sku.items():
            if int(sku_key) != int(sku):
                continue
            if int(region_orders) > top_region_orders:
                top_region = str(region)
                top_region_orders = int(region_orders)

        # "Активно продается" — рабочий порог для приоритета открытия/подключения склада.
        active_sales = total_orders >= 20
        if active_sales and top_region:
            recommendation = f"Добавить склад в {top_region}"
        elif top_region:
            recommendation = f"Переместить часть остатков в {top_region}"
        else:
            recommendation = "Проверить географию спроса и маршруты доставки"

        sku_non_local_actions.append(
            {
                "sku": int(sku),
                "non_local_orders_count": int(non_local_orders),
                "top_region": top_region,
                "total_orders": int(total_orders),
                "recommendation": recommendation,
            }
        )

    low_stock_threshold = max(1, LOCAL_MOVE_MIN_BATCH // 2)
    recommendations: list[dict[str, Any]] = []
    for item in by_sku:
        sku = int(item["sku"])
        sku_orders = int(item["total_orders"])
        actionable = False
        for region_item in item.get("regions", []):
            share_pct = float(region_item.get("share_pct") or 0.0)
            if share_pct < 10.0:
                continue
            region = str(region_item.get("region") or "")
            region_orders = int(region_item.get("orders") or 0)
            stock_qty_raw = region_item.get("stock_qty")
            stock_qty = int(stock_qty_raw) if stock_qty_raw is not None else None
            share = share_pct / 100.0
            recommended_qty = max(int(ceil(float(sku_orders) * share)), int(LOCAL_MOVE_MIN_BATCH))
            if stock_qty is None:
                message = (
                    f"SKU {sku}: за выбранный период {share_pct:.1f}% заказов ({region_orders} шт.) пришлись на {region}. "
                    f"Рекомендуется проверить наличие товара в этом регионе и рассмотреть локальное размещение "
                    f"на уровне {recommended_qty} шт."
                )
                recommendations.append(
                    {
                        "sku": sku,
                        "region": region,
                        "share_pct": round(share_pct, 1),
                        "orders": region_orders,
                        "stock_qty": None,
                        "recommended_qty": int(recommended_qty),
                        "message": message,
                        "priority": "check_stock",
                    }
                )
                actionable = True
                continue

            if stock_qty <= low_stock_threshold:
                stock_text = "остаток 0" if stock_qty == 0 else f"остаток низкий ({stock_qty} шт.)"
                message = (
                    f"SKU {sku}: за выбранный период {share_pct:.1f}% заказов ({region_orders} шт.) пришлись на {region}. "
                    f"В этом регионе {stock_text}. Рекомендуется поставить {recommended_qty} шт."
                )
                recommendations.append(
                    {
                        "sku": sku,
                        "region": region,
                        "share_pct": round(share_pct, 1),
                        "orders": region_orders,
                        "stock_qty": int(stock_qty),
                        "recommended_qty": int(recommended_qty),
                        "message": message,
                        "priority": "move_stock",
                    }
                )
                actionable = True
        if not actionable and item.get("regions"):
            top_region = item["regions"][0]
            recommendations.append(
                {
                    "sku": sku,
                    "region": top_region.get("region"),
                    "share_pct": float(top_region.get("share_pct") or 0.0),
                    "orders": int(top_region.get("orders") or 0),
                    "stock_qty": top_region.get("stock_qty"),
                    "recommended_qty": None,
                    "message": f"SKU {sku}: спрос распределен без выраженного локального дефицита, срочное перемещение не требуется.",
                    "priority": "observe",
                }
            )

    return {
        "available": True,
        "message": "Локальный спрос рассчитан по данным с географией заказов.",
        "total_buyouts": int(total_buyouts),
        "by_region": by_region[:20],
        "by_sku": by_sku[:50],
        "orders_with_geo": sorted(
            orders_with_geo,
            key=lambda item: (int(item.get("orders") or 0), int(item.get("sku") or 0)),
            reverse=True,
        )[:500],
        "sku_non_local_available": bool(route_rows_with_origin_destination > 0),
        "sku_non_local_actions": sorted(
            sku_non_local_actions,
            key=lambda item: int(item.get("non_local_orders_count") or 0),
            reverse=True,
        ),
        "recommendations": recommendations[:80],
        "diagnostics": {
            "orders_rows_scanned": int(orders_rows_scanned),
            "orders_rows_with_geo": int(orders_rows_with_geo),
            "orders_geo_source": preferred_orders_source,
            "route_rows_with_origin_destination": int(route_rows_with_origin_destination),
            "route_rows_non_local": int(route_rows_non_local),
            "stock_rows_scanned": int(stock_rows_scanned),
            "stock_rows_with_geo": int(stock_rows_with_geo),
            "minimal_batch": int(LOCAL_MOVE_MIN_BATCH),
            "low_stock_threshold": int(low_stock_threshold),
            "has_stock_by_region": bool(stock_rows_with_geo > 0),
        },
    }


def _norm_geo_key(value: Any) -> str:
    text = str(value or "").lower().replace("\xa0", " ").strip()
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _build_geo_to_logistics_index(
    flat_reference: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str]]]:
    region_exact: dict[str, str] = {}
    warehouse_exact: dict[str, str] = {}
    alias_pairs: list[tuple[str, str]] = []

    for row in flat_reference:
        region = str(row.get("region") or "").strip()
        warehouse = str(row.get("warehouse") or "").strip()
        if not region:
            continue
        region_key = _norm_geo_key(region)
        if region_key and region_key not in region_exact:
            region_exact[region_key] = region
            alias_pairs.append((region_key, region))
        warehouse_key = _norm_geo_key(warehouse)
        if warehouse_key:
            warehouse_exact[warehouse_key] = region
            alias_pairs.append((warehouse_key, region))

    alias_pairs = sorted(alias_pairs, key=lambda x: len(x[0]), reverse=True)
    return region_exact, warehouse_exact, alias_pairs


def _match_logistics_region(
    geo_label: str,
    *,
    region_exact: dict[str, str],
    warehouse_exact: dict[str, str],
    alias_pairs: list[tuple[str, str]],
) -> tuple[str | None, str]:
    geo_key = _norm_geo_key(geo_label)
    if not geo_key:
        return None, "none"
    if geo_key in region_exact:
        return region_exact[geo_key], "region_exact"
    if geo_key in warehouse_exact:
        return warehouse_exact[geo_key], "warehouse_exact"
    for alias, region in alias_pairs:
        if len(alias) < 5:
            continue
        if alias in geo_key or geo_key in alias:
            return region, "alias_match"
    return None, "unmatched"


def _build_logistics_reference_payload(
    *,
    local_orders_insights: dict[str, Any],
) -> dict[str, Any]:
    reference = load_warehouse_logistics_reference()
    flat_reference = flatten_warehouse_logistics_reference(reference)
    region_summary = build_region_logistics_summary(reference)
    region_coefficients = normalize_region_coefficients(region_summary)

    sortable = []
    regions_over_150: list[str] = []
    low_coverage_regions: list[str] = []
    unknown_regions: list[str] = []

    for region, item in region_summary.items():
        avg = _to_float_or_none(item.get("avg_coefficient"))
        known = _to_int(item.get("known_count"))
        unknown = _to_int(item.get("unknown_count"))
        if avg is not None:
            sortable.append((region, float(avg)))
            if float(avg) > float(HIGH_COEFFICIENT_ALERT):
                regions_over_150.append(region)
        else:
            unknown_regions.append(region)
        if known == 0 or (known > 0 and unknown > known):
            low_coverage_regions.append(region)

    top_expensive_regions = [
        {
            "region": region,
            "avg_coefficient": avg,
            "class": str((region_summary.get(region) or {}).get("class") or "unknown"),
        }
        for region, avg in sorted(sortable, key=lambda x: x[1], reverse=True)[:5]
    ]
    if region_coefficients:
        regions_over_150 = high_risk_regions_by_avg(region_coefficients)

    region_exact, warehouse_exact, alias_pairs = _build_geo_to_logistics_index(flat_reference)
    locality_signals: list[dict[str, Any]] = []
    by_region = (
        local_orders_insights.get("by_region")
        if isinstance(local_orders_insights.get("by_region"), list)
        else []
    )
    for item in by_region:
        if not isinstance(item, dict):
            continue
        geo_region = str(item.get("region") or "").strip()
        if not geo_region:
            continue
        mapped_region, match_type = _match_logistics_region(
            geo_region,
            region_exact=region_exact,
            warehouse_exact=warehouse_exact,
            alias_pairs=alias_pairs,
        )
        summary = (region_summary.get(mapped_region) or {}) if mapped_region else {}
        avg = _to_float_or_none(summary.get("avg_coefficient"))
        cls = str(summary.get("class") or "unknown")
        non_local_orders = _to_int(
            item.get("non_local_orders")
            or item.get("orders_non_local")
            or item.get("not_local_orders")
        )
        local_orders = _to_int(item.get("local_orders") or item.get("orders_local"))
        comment = ""
        risk_level = "low"
        if cls == "expensive" and non_local_orders > 0:
            comment = (
                "В регионе есть не локальные заказы; при повышенной логистике по сети складов "
                "стоит приоритизировать тест локального размещения малыми партиями."
            )
            risk_level = "high"
        elif cls == "expensive":
            comment = (
                "Регион относится к дорогим по логистике; рекомендации по размещению стоит применять осторожно."
            )
            risk_level = "medium"
        elif cls == "unknown":
            comment = (
                "Для региона коэффициенты логистики по части складов отсутствуют, выводы ограничены."
            )
        else:
            comment = (
                "Логистика региона не выглядит завышенной; можно использовать мягкий сценарий расширения размещения."
            )
        locality_signals.append(
            {
                "geo_region": geo_region,
                "logistics_region": mapped_region,
                "match_type": match_type,
                "orders": _to_int(item.get("orders")),
                "local_orders": local_orders,
                "non_local_orders": non_local_orders,
                "avg_coefficient": avg,
                "logistics_class": cls,
                "risk_level": risk_level,
                "comment": comment,
            }
        )

    potential_risk_regions = [
        row
        for row in locality_signals
        if str(row.get("risk_level")) == "high"
    ][:10]

    return {
        "reference": reference,
        "flat_reference": flat_reference,
        "region_summary": region_summary,
        "region_coefficients": region_coefficients,
        "top_expensive_regions": top_expensive_regions,
        "regions_over_150": regions_over_150,
        "low_coverage_regions": low_coverage_regions,
        "unknown_regions": unknown_regions,
        "locality_signals": locality_signals,
        "potential_risk_regions": potential_risk_regions,
    }


def _enhance_local_orders_with_logistics(
    *,
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(local_orders_insights, dict):
        return {"available": False, "message": "local orders payload is invalid"}

    enhanced = dict(local_orders_insights)
    signals = logistics_payload.get("locality_signals") or []
    if not isinstance(signals, list):
        return enhanced

    signal_by_geo = {
        _norm_geo_key(item.get("geo_region")): item
        for item in signals
        if isinstance(item, dict) and _norm_geo_key(item.get("geo_region"))
    }

    by_region = enhanced.get("by_region")
    if isinstance(by_region, list):
        enriched_regions: list[dict[str, Any]] = []
        for row in by_region:
            if not isinstance(row, dict):
                continue
            key = _norm_geo_key(row.get("region"))
            signal = signal_by_geo.get(key)
            merged = dict(row)
            if isinstance(signal, dict):
                merged["logistics_region"] = signal.get("logistics_region")
                merged["logistics_class"] = signal.get("logistics_class")
                merged["logistics_avg_coefficient"] = signal.get("avg_coefficient")
                merged["logistics_comment"] = signal.get("comment")
            enriched_regions.append(merged)
        enhanced["by_region"] = enriched_regions

    recommendations = enhanced.get("recommendations")
    if isinstance(recommendations, list):
        enriched_recommendations: list[dict[str, Any]] = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            out = dict(rec)
            key = _norm_geo_key(rec.get("region"))
            signal = signal_by_geo.get(key)
            if isinstance(signal, dict):
                cls = str(signal.get("logistics_class") or "unknown")
                non_local = _to_int(signal.get("non_local_orders"))
                logistic_note = str(signal.get("comment") or "").strip()
                base_message = str(out.get("message") or "").strip()
                if cls == "expensive" and non_local > 0:
                    out["priority"] = "move_stock_high"
                if logistic_note:
                    if base_message:
                        out["message"] = f"{base_message} {logistic_note}"
                    else:
                        out["message"] = logistic_note
                out["logistics_class"] = cls
                out["logistics_avg_coefficient"] = signal.get("avg_coefficient")
            enriched_recommendations.append(out)
        enhanced["recommendations"] = enriched_recommendations

    return enhanced


def _dedupe_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    seen = set()
    dup = 0
    for row in rows:
        key = tuple(str(row.get(f, "")) for f in key_fields)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dup


def _audit_stock_summary(
    *,
    stocks_raw: list[dict[str, Any]],
    stocks_parse_diag: dict[str, Any],
    stock_history_payload: dict[str, Any] | None,
    avg_daily_sales: float,
    lead_days: int = 14,
    safety_days: int = 7,
) -> dict[str, Any]:
    history = stock_history_payload if isinstance(stock_history_payload, dict) else {}
    history_totals_raw = history.get("sku_total_stocks")
    history_warehouses_raw = history.get("sku_stocks_by_warehouse")
    has_history_totals = isinstance(history_totals_raw, dict) and bool(history_totals_raw)

    by_key: dict[str, int] = defaultdict(int)
    total_units = 0
    parsed_rows = int(stocks_parse_diag.get("parsed_rows") or 0)
    mapped_rows = int(stocks_parse_diag.get("mapped_rows") or 0)

    if has_history_totals:
        for key_raw, qty_raw in (history_totals_raw or {}).items():
            key = str(key_raw or "").strip()
            if not key:
                continue
            qty = max(_to_int(qty_raw), 0)
            by_key[key] += qty
            total_units += qty
    else:
        for r in (stocks_raw or []):
            if not isinstance(r, dict):
                continue
            q = _to_int(r.get("quantityFull") or r.get("quantity") or r.get("qty") or r.get("stock"))
            key = r.get("nmId") or r.get("nm_id") or r.get("supplierArticle") or r.get("vendorCode")
            if key:
                by_key[str(key)] += max(q, 0)
            if q > 0:
                total_units += q

    sku_count = len(by_key)
    days_of_cover = (float(total_units) / float(avg_daily_sales)) if avg_daily_sales else 0.0
    threshold = int(lead_days + safety_days)

    aggregation_status = str(stocks_parse_diag.get("status") or "unknown")
    if aggregation_status == "ok" and parsed_rows > 0 and total_units == 0:
        aggregation_status = "aggregation_zero_with_nonempty_input"
    if aggregation_status == "ok" and parsed_rows > 0 and mapped_rows == 0:
        aggregation_status = "aggregation_unmapped"

    history_source = str(history.get("source") or "").strip()
    source = "xlsx_history" if has_history_totals or history_source == "xlsx_history" else "stocks_file"
    source_sheet = history.get("source_sheet") if has_history_totals else stocks_parse_diag.get("sheet")
    source_date = history.get("source_date") if has_history_totals else None

    sku_stocks_by_warehouse: dict[str, list[dict[str, Any]]] = {}
    if isinstance(history_warehouses_raw, dict):
        for key_raw, rows in history_warehouses_raw.items():
            key = str(key_raw or "").strip()
            if not key or not isinstance(rows, list):
                continue
            normalized_rows: list[dict[str, Any]] = []
            for item in rows:
                if not isinstance(item, dict):
                    continue
                warehouse = str(item.get("warehouse") or "").strip()
                qty = max(_to_int(item.get("qty")), 0)
                if not warehouse:
                    continue
                normalized_rows.append({"warehouse": warehouse, "qty": qty})
            sku_stocks_by_warehouse[key] = sorted(
                normalized_rows,
                key=lambda item: int(item.get("qty") or 0),
                reverse=True,
            )

    control_total_history = _to_int(history.get("control_total_history"))
    control_total_detail = history.get("control_total_detail")
    control_total_diff = history.get("control_total_diff")
    control_totals_match = history.get("control_totals_match")
    warnings = history.get("warnings") if isinstance(history.get("warnings"), list) else []

    return {
        "stock_units": int(total_units),
        "sku_count": int(sku_count),
        "days_of_cover": round(float(days_of_cover or 0.0), 2),
        "risk_of_oos": bool(days_of_cover != 0 and days_of_cover < threshold),
        "threshold_days": threshold,
        "items_count": int(len(stocks_raw or [])),
        "by_sku_or_article": dict(by_key),
        "source": source,
        "source_sheet": source_sheet,
        "source_date": source_date,
        "sku_total_stocks": dict(by_key),
        "sku_stocks_by_warehouse": sku_stocks_by_warehouse,
        "control_total_history": int(control_total_history) if control_total_history > 0 else None,
        "control_total_detail": _to_int(control_total_detail) if control_total_detail is not None else None,
        "control_total_diff": _to_int(control_total_diff) if control_total_diff is not None else None,
        "control_totals_match": bool(control_totals_match) if control_totals_match is not None else None,
        "warnings": warnings,
        "parsed_rows": parsed_rows,
        "mapped_rows": mapped_rows,
        "aggregation_status": aggregation_status,
        "parse_diagnostics": stocks_parse_diag,
        "note": (
            "Остатки audit-режима приоритетно собраны из листа 'Остатки по дням' "
            "как сумма по всем складам на выбранную дату."
        ),
    }


def _build_search_insights(
    *,
    selected_search_files: list[str],
    search_rows: list[dict[str, Any]],
    search_parse_diag: dict[str, Any],
    ads_rows: list[dict[str, Any]],
    orders_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    def _alloc_float(total: float, weights: list[float]) -> list[float]:
        size = len(weights)
        if size <= 0:
            return []
        total_norm = float(total or 0.0)
        if total_norm <= 0:
            return [0.0] * size
        safe_weights = [max(float(w or 0.0), 0.0) for w in weights]
        denom = sum(safe_weights)
        if denom <= 0:
            even = total_norm / float(size)
            out = [even] * size
        else:
            out = [(total_norm * w / denom) for w in safe_weights]
        diff = total_norm - sum(out)
        if size > 0 and abs(diff) > 1e-9:
            out[-1] += diff
        return out

    def _alloc_int(total: int, weights: list[float]) -> list[int]:
        size = len(weights)
        total_int = int(max(total, 0))
        if size <= 0:
            return []
        if total_int <= 0:
            return [0] * size
        base = _alloc_float(float(total_int), weights)
        ints = [int(x) for x in base]
        remain = int(total_int - sum(ints))
        if remain > 0:
            fractions = [(idx, base[idx] - float(ints[idx])) for idx in range(size)]
            fractions.sort(key=lambda x: x[1], reverse=True)
            for idx, _ in fractions[:remain]:
                ints[idx] += 1
        return ints

    if not selected_search_files:
        return {
            "status": "missing",
            "message": "search file not provided",
            "profitable": [],
            "unprofitable": [],
            "weak": [],
            "effective": [],
            "potential": [],
            "base_rows": [],
            "total_leak_spend": 0.0,
            "growth_hypotheses": [],
            "orders_data": {
                "available": False,
                "source": "missing",
                "message": "нет данных о заказах по запросам",
            },
            "parse_diagnostics": search_parse_diag,
        }

    status = str(search_parse_diag.get("status") or "unknown")
    if status != "ok" and not search_rows:
        return {
            "status": status,
            "message": f"search file selected but parse status is {status}",
            "profitable": [],
            "unprofitable": [],
            "weak": [],
            "effective": [],
            "potential": [],
            "base_rows": [],
            "total_leak_spend": 0.0,
            "growth_hypotheses": [],
            "orders_data": {
                "available": False,
                "source": "missing",
                "message": "нет данных о заказах по запросам",
            },
            "parse_diagnostics": search_parse_diag,
        }

    # 1) Агрегация search по query+SKU (полный список для JSON).
    aggregated: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in search_rows:
        if not isinstance(row, dict):
            continue
        query_raw = str(row.get("query") or "").strip()
        if not query_raw:
            continue
        nm_id = _to_int(row.get("nmId"))
        seller_article = str(row.get("seller_article") or "").strip()
        key = (_norm_text(query_raw), int(nm_id), _norm_text(seller_article))
        bucket = aggregated.setdefault(
            key,
            {
                "query": query_raw,
                "nmId": int(nm_id),
                "seller_article": seller_article,
                "impressions": 0,
                "clicks": 0,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
                "spend": 0.0,
                "revenue": 0.0,
                "spend_source": "search",
                "revenue_source": "search",
                "orders_source": "search",
            },
        )
        bucket["impressions"] += max(_to_int(row.get("impressions")), 0)
        bucket["clicks"] += max(_to_int(row.get("clicks")), 0)
        bucket["add_to_cart"] += max(_to_int(row.get("add_to_cart")), 0)
        bucket["orders"] += max(_to_int(row.get("orders")), 0)
        bucket["buyouts"] += max(_to_int(row.get("buyouts")), 0)
        bucket["spend"] += max(_to_float(row.get("spend")), 0.0)
        bucket["revenue"] += max(_to_float(row.get("revenue")), 0.0)

    base_rows = list(aggregated.values())

    # 2) Подготовка ads-агрегатов (для merge search + ads).
    ads_by_sku: dict[int, dict[str, float]] = {}
    ads_by_query_sku: dict[tuple[str, int], dict[str, float]] = {}
    for row in ads_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("nmId"))
        if sku <= 0:
            continue
        spend = max(_to_float(row.get("spend")), 0.0)
        impressions = max(_to_int(row.get("impressions")), 0)
        clicks = max(_to_int(row.get("clicks")), 0)
        revenue = max(_to_float(row.get("revenueAttr") if row.get("revenueAttr") is not None else row.get("revenue")), 0.0)
        sku_bucket = ads_by_sku.setdefault(
            int(sku),
            {
                "spend": 0.0,
                "impressions": 0.0,
                "clicks": 0.0,
                "revenue": 0.0,
            },
        )
        sku_bucket["spend"] += spend
        sku_bucket["impressions"] += float(impressions)
        sku_bucket["clicks"] += float(clicks)
        sku_bucket["revenue"] += revenue

        query_raw = str(row.get("query") or "").strip()
        query_norm = _norm_text(query_raw)
        if query_norm:
            query_bucket = ads_by_query_sku.setdefault(
                (query_norm, int(sku)),
                {
                    "spend": 0.0,
                    "impressions": 0.0,
                    "clicks": 0.0,
                    "revenue": 0.0,
                },
            )
            query_bucket["spend"] += spend
            query_bucket["impressions"] += float(impressions)
            query_bucket["clicks"] += float(clicks)
            query_bucket["revenue"] += revenue

    # 3) Прямой merge по query+SKU, если в ads есть query-level строки.
    for item in base_rows:
        sku = _to_int(item.get("nmId"))
        query_norm = _norm_text(item.get("query"))
        if sku <= 0 or not query_norm:
            continue
        direct = ads_by_query_sku.get((query_norm, int(sku)))
        if not isinstance(direct, dict):
            continue
        if _to_float(item.get("spend")) <= 0 and _to_float(direct.get("spend")) > 0:
            item["spend"] = round(_to_float(direct.get("spend")), 2)
            item["spend_source"] = "ads_query_direct"
        if _to_float(item.get("revenue")) <= 0 and _to_float(direct.get("revenue")) > 0:
            item["revenue"] = round(_to_float(direct.get("revenue")), 2)
            item["revenue_source"] = "ads_query_direct"
        if _to_int(item.get("impressions")) <= 0 and _to_int(direct.get("impressions")) > 0:
            item["impressions"] = _to_int(direct.get("impressions"))

    indices_by_sku: dict[int, list[int]] = {}
    for idx, item in enumerate(base_rows):
        sku = _to_int(item.get("nmId"))
        if sku <= 0:
            continue
        indices_by_sku.setdefault(int(sku), []).append(idx)

    # 4) Fallback spend/revenue из ads по SKU с аллокацией по query.
    for sku, idxs in indices_by_sku.items():
        ads_node = ads_by_sku.get(int(sku))
        if not isinstance(ads_node, dict):
            continue
        spend_total_sku = _to_float(ads_node.get("spend"))
        revenue_total_sku = _to_float(ads_node.get("revenue"))
        search_spend_sku = sum(max(_to_float(base_rows[i].get("spend")), 0.0) for i in idxs)
        search_revenue_sku = sum(max(_to_float(base_rows[i].get("revenue")), 0.0) for i in idxs)

        clicks_weights = [max(_to_int(base_rows[i].get("clicks")), 0) for i in idxs]
        impressions_weights = [max(_to_int(base_rows[i].get("impressions")), 0) for i in idxs]
        if sum(clicks_weights) > 0:
            weights = [float(x) for x in clicks_weights]
        elif sum(impressions_weights) > 0:
            weights = [float(x) for x in impressions_weights]
        else:
            weights = [1.0 for _ in idxs]

        if search_spend_sku <= 0 and spend_total_sku > 0:
            allocated_spend = _alloc_float(spend_total_sku, weights)
            for i, part in zip(idxs, allocated_spend):
                base_rows[i]["spend"] = round(max(part, 0.0), 2)
                base_rows[i]["spend_source"] = "ads_sku_allocated"

        if search_revenue_sku <= 0 and revenue_total_sku > 0:
            order_weights = [max(_to_int(base_rows[i].get("orders")), 0) for i in idxs]
            if sum(order_weights) > 0:
                revenue_weights = [float(x) for x in order_weights]
            else:
                revenue_weights = weights
            allocated_revenue = _alloc_float(revenue_total_sku, revenue_weights)
            for i, part in zip(idxs, allocated_revenue):
                base_rows[i]["revenue"] = round(max(part, 0.0), 2)
                base_rows[i]["revenue_source"] = "ads_sku_allocated"

    # 5) Fallback orders: если в search нет заказов, пробуем связать через orders/SKU.
    recognized_columns = search_parse_diag.get("recognized_columns") if isinstance(search_parse_diag, dict) else {}
    orders_column_detected = bool((recognized_columns or {}).get("orders"))
    orders_in_search = sum(max(_to_int(item.get("orders")), 0) for item in base_rows)
    orders_source = "search"
    orders_available = bool(orders_in_search > 0)
    orders_message = "orders from search file"

    if orders_in_search <= 0:
        buyouts_total = sum(max(_to_int(item.get("buyouts")), 0) for item in base_rows)
        if buyouts_total > 0:
            for item in base_rows:
                if _to_int(item.get("orders")) <= 0 and _to_int(item.get("buyouts")) > 0:
                    item["orders"] = _to_int(item.get("buyouts"))
                    item["orders_source"] = "search_buyouts_proxy"
            orders_source = "search_buyouts_proxy"
            orders_available = True
            orders_message = "orders restored from buyouts in search file"
        else:
            orders_by_sku: dict[int, int] = {}
            for row in orders_rows or []:
                if not isinstance(row, dict):
                    continue
                sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
                qty = _to_int(row.get("orders") or row.get("orderCount") or row.get("quantity"))
                if sku <= 0 or qty <= 0:
                    continue
                orders_by_sku[int(sku)] = orders_by_sku.get(int(sku), 0) + int(qty)

            linked_any = False
            for sku, idxs in indices_by_sku.items():
                sku_orders = orders_by_sku.get(int(sku), 0)
                if sku_orders <= 0:
                    continue
                clicks_weights = [max(_to_int(base_rows[i].get("clicks")), 0) for i in idxs]
                impressions_weights = [max(_to_int(base_rows[i].get("impressions")), 0) for i in idxs]
                if sum(clicks_weights) > 0:
                    weights = [float(x) for x in clicks_weights]
                elif sum(impressions_weights) > 0:
                    weights = [float(x) for x in impressions_weights]
                else:
                    weights = [1.0 for _ in idxs]
                allocated_orders = _alloc_int(sku_orders, weights)
                for i, part in zip(idxs, allocated_orders):
                    base_rows[i]["orders"] = max(_to_int(base_rows[i].get("orders")), int(part))
                    if int(part) > 0:
                        base_rows[i]["orders_source"] = "orders_sku_allocated"
                        linked_any = True
            if linked_any:
                orders_source = "orders_sku_allocated"
                orders_available = True
                orders_message = "orders linked via SKU from orders feed"
            else:
                if orders_column_detected:
                    orders_source = "search"
                    orders_available = True
                    orders_message = "orders column is present: 0 orders in period"
                else:
                    orders_source = "missing"
                    orders_available = False
                    orders_message = "нет данных о заказах по запросам"

    # 6) Финальные метрики query-level + A/B/C классификация.
    unprofitable: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []

    for item in base_rows:
        impressions = max(_to_int(item.get("impressions")), 0)
        clicks = max(_to_int(item.get("clicks")), 0)
        spend = max(_to_float(item.get("spend")), 0.0)
        orders = max(_to_int(item.get("orders")), 0)
        revenue = max(_to_float(item.get("revenue")), 0.0)
        ctr_ratio = (float(clicks) / float(impressions)) if impressions > 0 else None
        ctr_pct = (float(ctr_ratio) * 100.0) if ctr_ratio is not None else None
        cpc = (float(spend) / float(clicks)) if clicks > 0 else None
        cr = (float(orders) / float(clicks)) if clicks > 0 else None
        drr = (float(spend) / float(revenue)) if revenue > 0 else None
        roas = (float(revenue) / float(spend)) if spend > 0 else None

        # CTR is stored in percent (0..100), per audit requirements.
        item["ctr"] = round(float(ctr_pct), 2) if ctr_pct is not None else None
        item["cpc"] = round(float(cpc), 4) if cpc is not None else None
        item["cr"] = round(float(cr), 4) if cr is not None else None
        item["drr"] = round(float(drr), 4) if drr is not None else None
        item["roas"] = round(float(roas), 4) if roas is not None else None
        item["spend"] = round(float(spend), 2)
        item["revenue"] = round(float(revenue), 2)
        item["orders"] = int(orders)

        bucket = "unclassified"
        action = "Проверить вручную"
        if orders_available:
            if spend > 0 and orders == 0:
                bucket = "unprofitable"
                action = "Отключить"
                unprofitable.append(item)
            elif spend > 0 and orders > 0 and drr is not None and drr > 0.25:
                bucket = "weak"
                action = "Снизить ставку"
                weak.append(item)
            elif orders > 0 and drr is not None and drr < 0.20:
                bucket = "effective"
                action = "Масштабировать"
                effective.append(item)
        else:
            action = "нет данных о заказах по запросам"
        item["bucket"] = bucket
        item["action"] = action

    unprofitable = sorted(unprofitable, key=lambda r: (_to_float(r.get("spend")), _to_int(r.get("clicks"))), reverse=True)
    weak = sorted(weak, key=lambda r: (_to_float(r.get("spend")), _to_int(r.get("orders"))), reverse=True)
    effective = sorted(
        effective,
        key=lambda r: ((_to_float(r.get("revenue")) - _to_float(r.get("spend"))), _to_int(r.get("orders"))),
        reverse=True,
    )
    total_leak_spend = round(sum(max(_to_float(r.get("spend")), 0.0) for r in unprofitable), 2)

    # 7) Growth hypotheses D: high CTR, no ad spend.
    growth_query_map: dict[str, dict[str, Any]] = {}
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        q_norm = _norm_text(query)
        node = growth_query_map.setdefault(
            q_norm,
            {
                "query": query,
                "impressions": 0,
                "clicks": 0,
                "spend": 0.0,
            },
        )
        node["impressions"] += max(_to_int(row.get("impressions")), 0)
        node["clicks"] += max(_to_int(row.get("clicks")), 0)
        node["spend"] += max(_to_float(row.get("spend")), 0.0)

    growth_hypotheses: list[dict[str, Any]] = []
    for node in growth_query_map.values():
        impressions = max(_to_int(node.get("impressions")), 0)
        clicks = max(_to_int(node.get("clicks")), 0)
        spend = max(_to_float(node.get("spend")), 0.0)
        ctr_ratio = (float(clicks) / float(impressions)) if impressions > 0 else None
        ctr_pct = (float(ctr_ratio) * 100.0) if ctr_ratio is not None else None
        strict_ok = impressions >= 100 and ctr_pct is not None and ctr_pct >= 15.0
        relaxed_ok = impressions >= 50 and ctr_pct is not None and ctr_pct >= 20.0
        if spend <= 0 and (strict_ok or relaxed_ok):
            growth_hypotheses.append(
                {
                    "query": str(node.get("query") or ""),
                    "impressions": int(impressions),
                    "clicks": int(clicks),
                    "ctr": round(float(ctr_pct), 2) if ctr_pct is not None else None,
                    "spend": 0.0,
                    "action": "Протестировать",
                    "ads": "нет",
                }
            )
    growth_hypotheses = sorted(
        growth_hypotheses,
        key=lambda row: (_to_float_or_none(row.get("ctr")) or -1.0, _to_int(row.get("impressions"))),
        reverse=True,
    )

    final_status = "ok" if base_rows else ("empty_after_parse" if status == "ok" else status)
    message = "search parsed and enriched with ads"
    if not orders_available:
        message = "search parsed, but нет данных о заказах по запросам"
    elif orders_source == "orders_sku_allocated":
        message = "search parsed, orders linked via SKU/orders feed"
    return {
        "status": final_status,
        "message": message if final_status == "ok" else f"search file selected but no usable rows (status={final_status})",
        # Backward-compatible keys:
        "profitable": effective,
        "unprofitable": unprofitable,
        "potential": weak,
        # New explicit buckets:
        "effective": effective,
        "weak": weak,
        "base_rows": base_rows,
        "total_leak_spend": total_leak_spend,
        "growth_hypotheses": growth_hypotheses,
        "orders_data": {
            "available": bool(orders_available),
            "source": orders_source,
            "message": orders_message,
        },
        "summary": {
            "rows_count": len(base_rows),
            "profitable_count": len(effective),
            "unprofitable_count": len(unprofitable),
            "weak_count": len(weak),
            "effective_count": len(effective),
            "potential_count": len(weak),
            "total_leak_spend": total_leak_spend,
            "growth_hypotheses_count": len(growth_hypotheses),
            "orders_data_available": bool(orders_available),
            "orders_data_source": orders_source,
            "orders_data_message": orders_message,
        },
        "parse_diagnostics": search_parse_diag,
    }


def _build_source_consistency_warnings(finance: dict[str, Any], funnel: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    finance_qty = _to_int(finance.get("sales_qty"))
    funnel_buyouts = _to_int(funnel.get("buys"))
    finance_rev = _to_float(finance.get("gross_revenue"))
    funnel_rev = _to_float(funnel.get("revenue_buyouts"))

    def _rel_diff(a: float, b: float) -> float:
        denom = max(abs(a), abs(b), 1.0)
        return abs(a - b) / denom

    if finance_qty > 0 and funnel_buyouts > 0:
        diff = _rel_diff(float(finance_qty), float(funnel_buyouts))
        if diff > 0.5:
            warnings.append(
                {
                    "type": "quantity_mismatch",
                    "severity": "high",
                    "message": "Выкупы по funnel и finance сильно расходятся",
                    "numbers": {
                        "finance_sales_qty": finance_qty,
                        "funnel_buyouts": funnel_buyouts,
                        "relative_diff": round(diff, 4),
                    },
                }
            )
        elif diff > 0.3:
            warnings.append(
                {
                    "type": "quantity_mismatch",
                    "severity": "medium",
                    "message": "Выкупы по funnel и finance заметно расходятся",
                    "numbers": {
                        "finance_sales_qty": finance_qty,
                        "funnel_buyouts": funnel_buyouts,
                        "relative_diff": round(diff, 4),
                    },
                }
            )

    if finance_rev > 0 and funnel_rev > 0:
        diff = _rel_diff(finance_rev, funnel_rev)
        if diff > 0.5:
            warnings.append(
                {
                    "type": "revenue_mismatch",
                    "severity": "high",
                    "message": "Выручка по funnel и finance сильно расходится",
                    "numbers": {
                        "finance_gross_revenue": round(finance_rev, 2),
                        "funnel_revenue_buyouts": round(funnel_rev, 2),
                        "relative_diff": round(diff, 4),
                    },
                }
            )
        elif diff > 0.3:
            warnings.append(
                {
                    "type": "revenue_mismatch",
                    "severity": "medium",
                    "message": "Выручка по funnel и finance заметно расходится",
                    "numbers": {
                        "finance_gross_revenue": round(finance_rev, 2),
                        "funnel_revenue_buyouts": round(funnel_rev, 2),
                        "relative_diff": round(diff, 4),
                    },
                }
            )
    return warnings


def _build_decision_layer(
    *,
    finance: dict[str, Any],
    funnel: dict[str, Any],
    ads: dict[str, Any],
    stock: dict[str, Any],
    sku_rows: list[dict[str, Any]],
    search_insights: dict[str, Any],
    missing_required: list[str],
    missing_optional: list[str],
    source_consistency_warnings: list[dict[str, Any]],
    profit_without_cogs: bool,
) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    growth_points: list[dict[str, Any]] = []

    profit = _to_float(finance.get("profit"))
    revenue = _to_float(finance.get("gross_revenue"))
    margin = _to_float(finance.get("margin"))
    ads_spend = _to_float(ads.get("spend"))
    ads_revenue = _to_float(ads.get("revenue_attr"))
    roas = _to_float(ads.get("roas"))
    buyout_rate = _to_float(funnel.get("buyout_rate"))

    expense_components = [
        ("commission", _to_float(finance.get("commission"))),
        ("logistics", _to_float(finance.get("logistics"))),
        ("storage", _to_float(finance.get("storage"))),
        ("penalties", _to_float(finance.get("penalties"))),
        ("tax", _to_float(finance.get("tax"))),
        ("cogs_total", _to_float(finance.get("cogs_total"))),
    ]
    for name, value in sorted(expense_components, key=lambda x: x[1], reverse=True)[:3]:
        if value > 0:
            reasons.append(
                {
                    "category": "finance",
                    "reason": f"Высокий расход: {name}",
                    "numbers": {"amount": round(value, 2)},
                }
            )

    if ads_spend > 0 and ads_revenue <= 0:
        reasons.append(
            {
                "category": "ads",
                "reason": "Реклама убыточная: расход есть, атрибутированной выручки нет",
                "numbers": {"spend": round(ads_spend, 2), "revenue_attr": round(ads_revenue, 2)},
            }
        )
    elif ads_spend > 0 and roas < 1:
        reasons.append(
            {
                "category": "ads",
                "reason": "Реклама убыточная: ROAS ниже 1",
                "numbers": {"spend": round(ads_spend, 2), "roas": round(roas, 3)},
            }
        )

    if buyout_rate and buyout_rate < 0.6:
        reasons.append(
            {
                "category": "funnel",
                "reason": "Низкий % выкупа после заказа",
                "numbers": {"buyout_rate": round(buyout_rate, 4)},
            }
        )

    if profit_without_cogs:
        reasons.append(
            {
                "category": "finance",
                "reason": "Прибыль рассчитана без COGS (себестоимость не загружена)",
                "numbers": {"profit_without_cogs": True},
            }
        )

    for warning in source_consistency_warnings:
        reasons.append(
            {
                "category": "consistency",
                "reason": warning.get("message"),
                "numbers": warning.get("numbers"),
            }
        )

    stock_aggregation_status = str(stock.get("aggregation_status") or "")
    if stock_aggregation_status not in {"ok", ""}:
        reasons.append(
            {
                "category": "stock",
                "reason": "Проблема агрегации остатков: итоговые метрики могут быть неполными",
                "numbers": {
                    "aggregation_status": stock_aggregation_status,
                    "parsed_rows": stock.get("parsed_rows"),
                    "mapped_rows": stock.get("mapped_rows"),
                },
            }
        )

    negative_margin_sku = finance.get("negative_margin_sku") or []
    unprofitable_sku = [
        {
            "sku": int(x.get("sku") or 0),
            "profit": round(_to_float(x.get("profit")), 2),
            "margin": round(_to_float(x.get("margin")), 4),
        }
        for x in negative_margin_sku[:100]
        if int(x.get("sku") or 0) > 0
    ]

    sku_without_sales = []
    dead_stock = []
    for row in sku_rows:
        sku = int(row.get("sku") or 0)
        stock_qty = _to_int(row.get("stock_qty"))
        buyouts = _to_int(row.get("buyouts"))
        if stock_qty > 0 and buyouts == 0:
            payload = {
                "sku": sku,
                "stock_qty": stock_qty,
                "orders": _to_int(row.get("orders")),
                "buyouts": buyouts,
                "revenue": round(_to_float(row.get("revenue")), 2),
            }
            sku_without_sales.append(payload)
            dead_stock.append(payload)

    ads_leaks = []
    if ads_spend > 0 and ads_revenue <= 0:
        ads_leaks.append(
            {
                "level": "cabinet",
                "spend": round(ads_spend, 2),
                "revenue_attr": round(ads_revenue, 2),
                "roas": round(roas, 3),
            }
        )
    for row in (search_insights.get("unprofitable") or [])[:200]:
        ads_leaks.append(
            {
                "level": "query",
                "query": row.get("query"),
                "spend": round(_to_float(row.get("spend")), 2),
                "orders": _to_int(row.get("orders")),
                "revenue": round(_to_float(row.get("revenue")), 2),
            }
        )

    top_profit = finance.get("top_sku_by_profit") or []
    for item in top_profit[:20]:
        growth_points.append(
            {
                "type": "sku_profit_leader",
                "sku": int(item.get("sku") or 0),
                "profit": round(_to_float(item.get("profit")), 2),
                "margin": round(_to_float(item.get("margin")), 4),
            }
        )
    for row in (search_insights.get("profitable") or [])[:50]:
        growth_points.append(
            {
                "type": "search_query",
                "query": row.get("query"),
                "orders": _to_int(row.get("orders")),
                "roas": row.get("roas"),
            }
        )

    status = "ok"
    if missing_required:
        status = "partial_required_missing"
    elif missing_optional:
        status = "partial_optional_missing"

    return {
        "status": status,
        "profit_state": "loss" if profit < 0 else "profit" if profit > 0 else "breakeven",
        "kpi": {
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 4),
            "roas": round(roas, 3) if ads_spend > 0 else None,
            "profit_without_cogs": bool(profit_without_cogs),
        },
        "reasons_of_loss": reasons[:40],
        "unprofitable_sku": unprofitable_sku,
        "sku_without_sales": sku_without_sales[:200],
        "ads_leaks": ads_leaks[:200],
        "dead_stock": dead_stock[:200],
        "growth_points": growth_points[:200],
        "source_consistency_warnings": source_consistency_warnings,
        "missing_data": {
            "required": missing_required,
            "optional": missing_optional,
        },
    }


def _build_money_losses(
    *,
    ads_summary: dict[str, Any],
    decision_layer: dict[str, Any],
    financial_summary: dict[str, Any],
    sku_rows: list[dict[str, Any]],
    stock_summary: dict[str, Any],
) -> dict[str, Any]:
    ads_waste_rub = 0.0
    ads_waste_count = 0
    ads_waste_source = "none"

    ads_leaks = decision_layer.get("ads_leaks") if isinstance(decision_layer.get("ads_leaks"), list) else []
    query_leaks = [
        item
        for item in ads_leaks
        if isinstance(item, dict)
        and str(item.get("level") or "").strip().lower() == "query"
        and _to_float(item.get("spend")) > 0
        and _to_int(item.get("orders")) == 0
    ]
    if query_leaks:
        ads_waste_rub = round(sum(_to_float(item.get("spend")) for item in query_leaks), 2)
        ads_waste_count = len(query_leaks)
        ads_waste_source = "query"
    else:
        cabinet_leaks = [
            item
            for item in ads_leaks
            if isinstance(item, dict)
            and str(item.get("level") or "").strip().lower() == "cabinet"
            and _to_float(item.get("spend")) > 0
            and _to_int(item.get("orders")) == 0
        ]
        if cabinet_leaks:
            ads_waste_rub = round(sum(_to_float(item.get("spend")) for item in cabinet_leaks), 2)
            ads_waste_count = len(cabinet_leaks)
            ads_waste_source = "cabinet"
        else:
            spend_total = _to_float_or_none(ads_summary.get("spend"))
            revenue_attr = _to_float_or_none(ads_summary.get("revenue_attr"))
            if (spend_total or 0.0) > 0 and (revenue_attr or 0.0) <= 0:
                ads_waste_rub = round(float(spend_total or 0.0), 2)
                ads_waste_count = 1
                ads_waste_source = "ads_summary_fallback"

    negative_profit_rows: list[dict[str, Any]] = []
    for row in sku_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku"))
        profit = _to_float_or_none(row.get("profit"))
        if sku <= 0 or profit is None or profit >= 0:
            continue
        negative_profit_rows.append(
            {
                "sku": int(sku),
                "profit": round(float(profit), 2),
                "stock_qty": _to_int(row.get("stock_qty")),
            }
        )
    negative_profit_rub = round(sum(abs(_to_float(item.get("profit"))) for item in negative_profit_rows), 2)
    negative_profit_sku_count = len(negative_profit_rows)

    sku_financials = _as_sku_int_map(financial_summary.get("sku_financials"))
    frozen_rows: list[dict[str, Any]] = []
    storage_risk_rows: list[dict[str, Any]] = []
    frozen_stock_value_total = 0.0
    frozen_stock_value_valuated_sku = 0
    frozen_stock_qty_total = 0

    for row in sku_rows or []:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku"))
        if sku <= 0:
            continue
        stock_qty = max(_to_int(row.get("stock_qty")), 0)
        orders = _to_int(row.get("orders"))
        buyouts = _to_int(row.get("buyouts"))
        turnover_days = _to_float_or_none(row.get("turnover_days"))
        if stock_qty <= 0:
            continue

        no_sales = orders <= 0 and buyouts <= 0
        slow_turnover = turnover_days is not None and float(turnover_days) >= 45.0
        if no_sales or slow_turnover:
            frozen_stock_qty_total += int(stock_qty)
            cogs_unit = None
            fin = sku_financials.get(sku) or {}
            cogs_total_sku = _to_float_or_none(fin.get("cogs"))
            sales_qty_sku = _to_int(fin.get("sales_qty"))
            if cogs_total_sku is not None and cogs_total_sku > 0 and sales_qty_sku > 0:
                cogs_unit = float(cogs_total_sku) / float(sales_qty_sku)
                frozen_stock_value_total += float(cogs_unit) * float(stock_qty)
                frozen_stock_value_valuated_sku += 1
            frozen_rows.append(
                {
                    "sku": int(sku),
                    "stock_qty": int(stock_qty),
                    "orders": int(orders),
                    "buyouts": int(buyouts),
                    "turnover_days": round(float(turnover_days), 2) if turnover_days is not None else None,
                    "cogs_unit": round(float(cogs_unit), 2) if cogs_unit is not None else None,
                }
            )

        storage_risk = stock_qty >= 50 and (buyouts <= 1 or (turnover_days is not None and float(turnover_days) >= 60.0))
        if storage_risk:
            storage_risk_rows.append(
                {
                    "sku": int(sku),
                    "stock_qty": int(stock_qty),
                    "buyouts": int(buyouts),
                    "turnover_days": round(float(turnover_days), 2) if turnover_days is not None else None,
                }
            )

    frozen_stock_sku_count = len(frozen_rows)
    frozen_stock_value_rub = round(float(frozen_stock_value_total), 2) if frozen_stock_value_valuated_sku > 0 else None
    storage_risk_sku_count = len(storage_risk_rows)

    total_direct_losses_rub = round(float(ads_waste_rub) + float(negative_profit_rub), 2)

    return {
        "ads_waste_rub": round(float(ads_waste_rub), 2),
        "ads_waste_count": int(ads_waste_count),
        "ads_waste_source": ads_waste_source,
        "negative_profit_rub": round(float(negative_profit_rub), 2),
        "negative_profit_sku_count": int(negative_profit_sku_count),
        "frozen_stock_value_rub": frozen_stock_value_rub,
        "frozen_stock_sku_count": int(frozen_stock_sku_count),
        "frozen_stock_qty_units": int(frozen_stock_qty_total),
        "frozen_stock_value_estimate_available": bool(frozen_stock_value_valuated_sku > 0),
        "frozen_stock_valuated_sku_count": int(frozen_stock_value_valuated_sku),
        "storage_risk_sku_count": int(storage_risk_sku_count),
        "total_direct_losses_rub": round(float(total_direct_losses_rub), 2),
        "ads_waste_items": query_leaks[:20] if query_leaks else ads_leaks[:20],
        "negative_profit_items": negative_profit_rows[:20],
        "frozen_stock_items": frozen_rows[:20],
        "storage_risk_items": storage_risk_rows[:20],
        "source": {
            "stock_source": stock_summary.get("source"),
            "stock_source_date": stock_summary.get("source_date"),
        },
    }


def _build_actions(
    decision_layer: dict[str, Any],
    stock_summary: dict[str, Any],
    logistics_formula_model: dict[str, Any] | None = None,
    localization_loss: dict[str, Any] | None = None,
    financial_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    profit_state = decision_layer.get("profit_state")
    kpi = decision_layer.get("kpi") or {}
    finance = financial_summary if isinstance(financial_summary, dict) else {}

    if profit_state == "loss":
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Снизить крупнейшие расходные статьи до выхода в положительную маржу",
                "why": "Кабинет в убытке по финрезультату",
                "expected_effect": "Сокращение операционного убытка",
                "numbers": {"profit": kpi.get("profit"), "margin": kpi.get("margin")},
            }
        )

    cogs_status = str(finance.get("cogs_status") or "")
    cogs_diag = finance.get("cogs_diagnostics") if isinstance(finance.get("cogs_diagnostics"), dict) else {}
    cogs_coverage = _to_float_or_none(cogs_diag.get("cogs_coverage_pct"))
    if cogs_status == "file_not_found":
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Загрузить COGS-файл и пересчитать прибыль с учетом себестоимости",
                "why": "Текущая прибыль рассчитана без себестоимости",
                "expected_effect": "Корректная оценка реальной прибыльности кабинета",
                "numbers": {"cogs_status": cogs_status},
            }
        )
    elif cogs_status in {"file_found_not_read", "file_read_not_matched", "partial_match"}:
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Проверить сопоставление COGS по SKU и пересчитать прибыль",
                "why": "Себестоимость загружена не полностью или не сопоставлена с продажами",
                "expected_effect": "Корректные profit, margin и ROI по кабинету и SKU",
                "numbers": {
                    "cogs_status": cogs_status,
                    "cogs_coverage_pct": cogs_coverage,
                    "cogs_rows_loaded": cogs_diag.get("cogs_rows_loaded"),
                    "cogs_matched_sku": cogs_diag.get("cogs_matched_sku"),
                },
            }
        )

    if bool(finance.get("commission_anomaly")):
        actions.append(
            {
                "priority": "P1",
                "area": "finance",
                "action": "Проверить аномальное изменение комиссии WB и структуру комиссионных компонентов",
                "why": "Комиссия WB заметно отклоняется от базовой комиссии по продажам",
                "expected_effect": "Подтвержденный и объяснимый расчет комиссии в weekly finance",
                "numbers": {
                    "commission": finance.get("commission"),
                    "base_commission": (finance.get("commission_breakdown") or {}).get("base_commission")
                    if isinstance(finance.get("commission_breakdown"), dict)
                    else None,
                    "delta_vs_base": finance.get("commission_delta_vs_base"),
                },
            }
        )

    if decision_layer.get("source_consistency_warnings"):
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Проверить период и полноту weekly finance-файлов относительно funnel",
                "why": "Между funnel и finance есть сильные расхождения",
                "expected_effect": "Согласованные показатели выручки и количества выкупов",
                "numbers": {"warnings_count": len(decision_layer.get("source_consistency_warnings") or [])},
            }
        )

    ads_leaks = decision_layer.get("ads_leaks") if isinstance(decision_layer.get("ads_leaks"), list) else []
    ads_leaks_spend = sum(
        (_to_float_or_none(item.get("spend")) or 0.0)
        for item in ads_leaks
        if isinstance(item, dict) and _to_int(item.get("orders")) == 0
    )
    if ads_leaks:
        ads_loss_is_significant = float(ads_leaks_spend) >= 100.0
        actions.append(
            {
                "priority": "P0",
                "area": "ads",
                "action": "Отключить кампании и запросы с расходом без заказов",
                "why": (
                    "Реклама убыточная и сливает бюджет"
                    if ads_loss_is_significant
                    else "Данные не подтверждают значимые потери по рекламе"
                ),
                "expected_effect": (
                    f"Снижение рекламного расхода без потери выручки (~{round(float(ads_leaks_spend), 2)} RUB за период)"
                    if ads_loss_is_significant
                    else "Существенная экономия не подтверждена (менее 100 RUB)"
                ),
                "numbers": {
                    "leaks_count": len(ads_leaks),
                    "leaks_spend_rub": round(float(ads_leaks_spend), 2),
                    "estimated_saving_rub": round(float(ads_leaks_spend), 2) if ads_loss_is_significant else None,
                },
            }
        )

    if decision_layer.get("unprofitable_sku"):
        actions.append(
            {
                "priority": "P1",
                "area": "sku",
                "action": "Убрать из продвижения SKU с отрицательной маржей и пересчитать цену/себестоимость",
                "why": "SKU тянут кабинет в минус",
                "expected_effect": "Рост валовой маржи по ассортименту",
                "numbers": {"unprofitable_sku_count": len(decision_layer.get("unprofitable_sku") or [])},
            }
        )

    if decision_layer.get("dead_stock"):
        actions.append(
            {
                "priority": "P1",
                "area": "stock",
                "action": "Сократить мертвые остатки: распродать или убрать закупку по SKU без продаж",
                "why": "Деньги заморожены в остатках без движения",
                "expected_effect": "Высвобождение оборотного капитала",
                "numbers": {"dead_stock_count": len(decision_layer.get("dead_stock") or [])},
            }
        )

    if str(stock_summary.get("aggregation_status") or "") not in {"ok", ""}:
        actions.append(
            {
                "priority": "P1",
                "area": "stock",
                "action": "Перепроверить формат отчета остатков и маппинг колонок",
                "why": "Агрегация остатков отработала с ошибкой/неполным маппингом",
                "expected_effect": "Корректные метрики stock_units, sku_count и days_of_cover",
                "numbers": {
                    "aggregation_status": stock_summary.get("aggregation_status"),
                    "parsed_rows": stock_summary.get("parsed_rows"),
                    "mapped_rows": stock_summary.get("mapped_rows"),
                },
            }
        )

    logistic_risk_level = str((logistics_formula_model or {}).get("risk_level") or "").lower()
    if logistic_risk_level in {"medium", "high"}:
        actions.append(
            {
                "priority": "P1",
                "area": "logistics",
                "action": "Пересмотреть распределение остатков по складам для снижения ИЛ/ИРП",
                "why": "Низкая локализация повышает стоимость логистики",
                "expected_effect": "Снижение логистических затрат и рост маржи",
                "numbers": {
                    "risk_level": logistic_risk_level,
                    "localization_share_pct": (logistics_formula_model or {}).get("localization_share_pct"),
                },
            }
        )

    for rec in (localization_loss or {}).get("recommendations") or []:
        if not isinstance(rec, dict):
            continue
        actions.append(
            {
                "priority": str(rec.get("priority") or "P1"),
                "area": str(rec.get("area") or "logistics"),
                "action": str(rec.get("action") or ""),
                "why": str(rec.get("why") or ""),
                "expected_effect": str(rec.get("expected_effect") or ""),
                "numbers": {
                    "estimation_mode": (localization_loss or {}).get("estimation_mode"),
                    "total_estimated_loss_rub": (localization_loss or {}).get("total_estimated_loss_rub"),
                    "non_local_orders_share": (localization_loss or {}).get("non_local_orders_share"),
                },
            }
        )

    if not actions:
        actions.append(
            {
                "priority": "P2",
                "area": "finance",
                "action": "Зафиксировать текущую модель и масштабировать точки роста без увеличения убыточных расходов",
                "why": "Критичных отклонений не обнаружено",
                "expected_effect": "Контролируемый рост прибыли",
                "numbers": {"profit": kpi.get("profit"), "margin": kpi.get("margin")},
            }
        )
    return actions


def _build_inputs_section(
    *,
    input_dir: str,
    detected_files: list[Any],
    grouped_files: dict[str, list[Any]],
    selected_files: dict[str, list[str]],
    missing_required: list[str],
    missing_optional: list[str],
    parse_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    found = []
    for item in detected_files:
        found.append(
            {
                "path": item.path,
                "type": item.file_type,
                "score": item.score,
                "detected_by": item.detected_by,
                "sheets": item.sheets,
                "sample_columns": item.sample_columns,
            }
        )

    blocks_collected = [k for k in FILE_TYPES if selected_files.get(k)]
    blocks_skipped = [k for k in FILE_TYPES if k not in blocks_collected]

    candidate_files = {}
    for file_type in FILE_TYPES:
        candidate_files[file_type] = [x.path for x in (grouped_files.get(file_type) or [])]

    return {
        "input_dir": input_dir,
        "found_files": found,
        "candidate_files": candidate_files,
        "selected_files": selected_files,
        "blocks_collected": blocks_collected,
        "blocks_skipped": blocks_skipped,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "parse_diagnostics": parse_diagnostics,
    }


def _parse_many_finance(files: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    storage_columns_detected: set[str] = set()
    storage_column_found = False
    storage_available_columns: list[str] = []
    storage_available_seen: set[str] = set()
    for path in files:
        rows, diag = parse_finance_file_with_diagnostics(path)
        rows_all.extend(rows)
        diagnostics.append(diag)
        if bool(diag.get("storage_column_found")):
            storage_column_found = True
        source_column = str(diag.get("storage_source_column") or "").strip()
        if source_column:
            storage_columns_detected.add(source_column)
        available_columns = diag.get("available_columns")
        if isinstance(available_columns, list):
            for column in available_columns:
                column_str = str(column or "").strip()
                if not column_str or column_str in storage_available_seen:
                    continue
                storage_available_seen.add(column_str)
                storage_available_columns.append(column_str)

    deduped, dup_count = _dedupe_rows(
        rows_all,
        key_fields=(
            "doc_type_name",
            "nm_id",
            "quantity",
            "retail_amount",
            "ppvz_sales_commission",
            "wb_reward_before_agent",
            "pvz_compensation",
            "payment_services_compensation",
            "payment_services_compensation_amount",
            "ppvz_for_pay",
            "delivery_rub",
            "storage_fee",
            "penalty",
            "_supplier_article",
            "_name",
        ),
    )
    return deduped, {
        "files_count": len(files),
        "rows_raw_total": len(rows_all),
        "rows_after_dedup": len(deduped),
        "duplicates_removed": int(dup_count),
        "storage_column_found": bool(storage_column_found),
        "storage_columns_detected": sorted(storage_columns_detected),
        "storage_available_columns": storage_available_columns,
        "files": diagnostics,
    }


def _parse_many_ads(files: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    for path in files:
        rows, diag = parse_ads_file_with_diagnostics(path)
        rows_all.extend(rows)
        diagnostics.append(diag)

    deduped, dup_count = _dedupe_rows(
        rows_all,
        key_fields=("nmId", "query", "name", "spend", "impressions", "clicks", "revenueAttr"),
    )
    return deduped, {
        "files_count": len(files),
        "rows_raw_total": len(rows_all),
        "rows_after_dedup": len(deduped),
        "duplicates_removed": int(dup_count),
        "files": diagnostics,
    }


def _parse_many_orders(files: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    for path in files:
        rows, diag = parse_orders_file_with_diagnostics(path)
        rows_all.extend(rows)
        diagnostics.append(diag)

    deduped, dup_count = _dedupe_rows(
        rows_all,
        key_fields=(
            "date",
            "nmId",
            "seller_article",
            "region",
            "city",
            "customer_region",
            "warehouse_region",
            "warehouse",
            "orders",
        ),
    )
    return deduped, {
        "files_count": len(files),
        "rows_raw_total": len(rows_all),
        "rows_after_dedup": len(deduped),
        "duplicates_removed": int(dup_count),
        "files": diagnostics,
    }


def build_audit_facts(input_dir: str = "audit/input", period_label: str = "") -> dict[str, Any]:
    tax_rate = float(os.getenv("WB_TAX_RATE", "0.06"))
    report_date = dt.datetime.now(WB_TIMEZONE).date()

    detected_files = scan_input_files(input_dir)
    grouped_files = group_detected_files(detected_files)

    missing_required = [file_type for file_type in REQUIRED_TYPES if not grouped_files.get(file_type)]
    missing_optional = [file_type for file_type in OPTIONAL_TYPES if not grouped_files.get(file_type)]

    selected_files: dict[str, list[str]] = {
        "finance": [x.path for x in (grouped_files.get("finance") or [])],
        "ads": [x.path for x in (grouped_files.get("ads") or [])],
        "funnel": [grouped_files["funnel"][0].path] if grouped_files.get("funnel") else [],
        "stocks": [grouped_files["stocks"][0].path] if grouped_files.get("stocks") else [],
        "search": [grouped_files["search"][0].path] if grouped_files.get("search") else [],
        "orders": [x.path for x in (grouped_files.get("orders") or [])],
        "cogs": [grouped_files["cogs"][0].path] if grouped_files.get("cogs") else [],
    }

    finance_rows, finance_parse_diag = _parse_many_finance(selected_files["finance"])
    ads_rows, ads_parse_diag = _parse_many_ads(selected_files["ads"])
    orders_rows, orders_parse_diag = _parse_many_orders(selected_files["orders"])
    funnel_rows = parse_funnel_file(selected_files["funnel"][0]) if selected_files["funnel"] else []

    preferred_stock_date = None
    if period_label and "_" in period_label:
        try:
            _, d2s = period_label.split("_", 1)
            preferred_stock_date = dt.date.fromisoformat(d2s).isoformat()
        except Exception:
            preferred_stock_date = None

    stock_history_payload: dict[str, Any] = {
        "status": "file_not_provided",
        "rows": [],
        "warnings": [],
    }
    if selected_files["stocks"]:
        stock_history_payload = parse_audit_stock_history_with_diagnostics(
            selected_files["stocks"][0],
            preferred_date=preferred_stock_date,
        )

    history_rows = stock_history_payload.get("rows") if isinstance(stock_history_payload.get("rows"), list) else []
    history_ok = str(stock_history_payload.get("status") or "") == "ok" and len(history_rows) > 0
    if history_ok:
        stocks_rows = history_rows
        stocks_parse_diag = {
            "status": "ok",
            "path": selected_files["stocks"][0],
            "sheet": stock_history_payload.get("source_sheet"),
            "source": stock_history_payload.get("source"),
            "source_date": stock_history_payload.get("source_date"),
            "source_date_column": stock_history_payload.get("source_date_column"),
            "available_dates": stock_history_payload.get("available_dates"),
            "parsed_rows": stock_history_payload.get("rows_parsed"),
            "rows_parsed": stock_history_payload.get("rows_parsed"),
            "mapped_rows": stock_history_payload.get("rows_parsed"),
            "control_totals_match": stock_history_payload.get("control_totals_match"),
            "control_total_history": stock_history_payload.get("control_total_history"),
            "control_total_detail": stock_history_payload.get("control_total_detail"),
            "warnings": stock_history_payload.get("warnings"),
        }
    else:
        stocks_rows, stocks_parse_diag = (
            parse_stocks_file_with_diagnostics(selected_files["stocks"][0])
            if selected_files["stocks"]
            else ([], {"status": "file_not_provided"})
        )
        if selected_files["stocks"] and str(stock_history_payload.get("status") or "") != "file_not_provided":
            stocks_parse_diag = dict(stocks_parse_diag)
            stocks_parse_diag["history_parser"] = {
                "status": stock_history_payload.get("status"),
                "source_sheet": stock_history_payload.get("source_sheet"),
                "source_date": stock_history_payload.get("source_date"),
                "warnings": stock_history_payload.get("warnings"),
            }

    sku_dimensions, volume_coverage = _build_sku_dimensions(stocks_rows)
    volume_coverage["expected_source"] = "stocks"
    volume_coverage["expected_file"] = selected_files["stocks"][0] if selected_files["stocks"] else None
    if _to_int(volume_coverage.get("with_volume")) <= 0:
        volume_coverage["missing_reason"] = "volume_not_found_in_stocks_file"
        volume_coverage["missing_hint"] = "Ожидались колонки объема в файле остатков (stocks)."
    search_rows, search_parse_diag = (
        parse_search_file_with_diagnostics(selected_files["search"][0]) if selected_files["search"] else ([], {"status": "file_not_provided"})
    )
    cogs_rows, cogs_parse_diag = (
        parse_cogs_file_with_diagnostics(selected_files["cogs"][0]) if selected_files["cogs"] else ([], {"status": "file_not_provided"})
    )

    funnel_summary = calc_funnel_metrics(funnel_rows) if funnel_rows else {}
    financial_summary = (
        calc_financial_metrics(
            finance_rows,
            tax_rate=tax_rate,
            cogs_rows=cogs_rows,
            cogs_file_found=bool(selected_files["cogs"]),
        )
        if finance_rows
        else {"rows_count": 0}
    )
    ads_summary = calc_ads_metrics(ads_rows) if ads_rows else {}
    funnel_traffic = _derive_funnel_impressions_and_ctr(
        funnel_summary=funnel_summary if isinstance(funnel_summary, dict) else {},
        funnel_rows=funnel_rows,
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
    )
    funnel_summary = dict(funnel_summary or {})
    funnel_summary["impressions"] = funnel_traffic.get("impressions")
    funnel_summary["ctr"] = funnel_traffic.get("ctr")
    funnel_summary["impressions_source"] = funnel_traffic.get("impressions_source")
    ads_summary["files_count"] = len(selected_files["ads"])
    ads_summary["parse_diagnostics"] = ads_parse_diag
    financial_summary["files_count"] = len(selected_files["finance"])
    financial_summary["parse_diagnostics"] = finance_parse_diag
    financial_summary["cogs_parse_diagnostics"] = cogs_parse_diag
    if not isinstance(financial_summary.get("storage_debug"), dict):
        financial_summary["storage_debug"] = {}
    financial_summary["storage_debug"].setdefault("source_column", None)
    financial_summary["storage_debug"].setdefault("rows_with_storage", 0)
    financial_summary["storage_debug"].setdefault("storage_total", _to_float(financial_summary.get("storage")))
    financial_summary["storage_debug"].setdefault(
        "source_columns_detected",
        list((finance_parse_diag.get("storage_columns_detected") or []))
        if isinstance(finance_parse_diag, dict)
        else [],
    )

    storage_debug = financial_summary.get("storage_debug") if isinstance(financial_summary.get("storage_debug"), dict) else {}
    storage_source_column = str(storage_debug.get("source_column") or "").strip()
    storage_rows_with_values = _to_int(storage_debug.get("rows_with_storage"))
    storage_total = _to_float(storage_debug.get("storage_total"))
    storage_available_columns = (
        list(finance_parse_diag.get("storage_available_columns") or []) if isinstance(finance_parse_diag, dict) else []
    )
    if storage_source_column:
        print("STORAGE DEBUG:")
        print(f'source_column="{storage_source_column}"')
        print(f"rows_with_storage={storage_rows_with_values}")
        print(f"storage_total={storage_total:.2f}")
    else:
        print("STORAGE WARNING:")
        print("No storage column found in financial report")
        print(f"available_columns={storage_available_columns}")

    if "cogs_status" not in financial_summary:
        if not selected_files["cogs"]:
            financial_summary["cogs_status"] = "file_not_found"
        elif str(cogs_parse_diag.get("status") or "") == "ok" and len(cogs_rows) > 0:
            financial_summary["cogs_status"] = "file_read_not_matched"
        else:
            financial_summary["cogs_status"] = "file_found_not_read"
    if not isinstance(financial_summary.get("cogs_diagnostics"), dict):
        financial_summary["cogs_diagnostics"] = {}
    financial_summary["cogs_diagnostics"].setdefault("cogs_file_found", bool(selected_files["cogs"]))
    financial_summary["cogs_diagnostics"].setdefault("cogs_rows_loaded", len(cogs_rows))
    financial_summary["cogs_diagnostics"].setdefault("cogs_sku_total", len(cogs_rows))
    financial_summary["cogs_diagnostics"].setdefault("cogs_matched_sku", 0)
    financial_summary["cogs_diagnostics"].setdefault("cogs_unmatched_sku", [])
    financial_summary["cogs_diagnostics"].setdefault("cogs_match_key", "nm_id|seller_article")
    financial_summary["cogs_diagnostics"].setdefault("cogs_total", financial_summary.get("cogs_total"))

    period_days = 7
    if period_label and "_" in period_label:
        try:
            d1s, d2s = period_label.split("_", 1)
            d1 = dt.date.fromisoformat(d1s)
            d2 = dt.date.fromisoformat(d2s)
            period_days = max((d2 - d1).days + 1, 1)
        except Exception:
            period_days = 7

    avg_daily_sales = _to_float((funnel_summary or {}).get("buys")) / float(period_days or 1)
    stock_summary = _audit_stock_summary(
        stocks_raw=stocks_rows,
        stocks_parse_diag=stocks_parse_diag,
        stock_history_payload=stock_history_payload,
        avg_daily_sales=avg_daily_sales,
    )
    sku_totals_debug = stock_summary.get("sku_total_stocks") if isinstance(stock_summary.get("sku_total_stocks"), dict) else {}
    sku_warehouses_debug = (
        stock_summary.get("sku_stocks_by_warehouse")
        if isinstance(stock_summary.get("sku_stocks_by_warehouse"), dict)
        else {}
    )
    if sku_totals_debug:
        sorted_sku_totals = sorted(
            ((str(k), _to_int(v)) for k, v in sku_totals_debug.items()),
            key=lambda item: int(item[1]),
            reverse=True,
        )
        max_debug_rows = 20
        for sku_text, total_qty in sorted_sku_totals[:max_debug_rows]:
            warehouses = sku_warehouses_debug.get(sku_text) if isinstance(sku_warehouses_debug.get(sku_text), list) else []
            print("STOCK DEBUG:")
            print(f"sku={sku_text}")
            print(f"source={stock_summary.get('source_sheet')}")
            print(f"date={stock_summary.get('source_date')}")
            print(f"warehouses={len(warehouses)}")
            print(f"total_stock={int(total_qty)}")
        if len(sorted_sku_totals) > max_debug_rows:
            print(f"STOCK DEBUG: skipped {len(sorted_sku_totals) - max_debug_rows} SKU debug rows")
    else:
        print("STOCK WARNING:")
        print("No SKU stock totals parsed from stock history")

    control_totals_match = stock_summary.get("control_totals_match")
    if control_totals_match is False:
        print("STOCK WARNING:")
        print(
            "Totals mismatch between sheets: "
            f"history={stock_summary.get('control_total_history')}, "
            f"detail={stock_summary.get('control_total_detail')}, "
            f"diff={stock_summary.get('control_total_diff')}"
        )

    search_insights = _build_search_insights(
        selected_search_files=selected_files["search"],
        search_rows=search_rows,
        search_parse_diag=search_parse_diag,
        ads_rows=ads_rows,
        orders_rows=orders_rows,
    )
    logistics_config = _load_logistics_config(input_dir=input_dir)
    local_orders_insights = _build_local_orders_insights(
        orders_rows=orders_rows,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
    )
    logistics_payload: dict[str, Any]
    try:
        logistics_payload = _build_logistics_reference_payload(
            local_orders_insights=local_orders_insights,
        )
    except Exception as exc:
        logistics_payload = {
            "reference": {},
            "flat_reference": [],
            "region_summary": {},
            "top_expensive_regions": [],
            "regions_over_150": [],
            "low_coverage_regions": [],
            "unknown_regions": [],
            "locality_signals": [],
            "potential_risk_regions": [],
            "error": f"logistics_payload_failed: {exc}",
        }

    local_orders_insights = _enhance_local_orders_with_logistics(
        local_orders_insights=local_orders_insights,
        logistics_payload=logistics_payload,
    )
    try:
        logistics_formula_model = _build_logistics_formula_model_payload(
            funnel_summary=funnel_summary,
            financial_summary=financial_summary,
            local_orders_insights=local_orders_insights,
            logistics_payload=logistics_payload,
            sku_dimensions=sku_dimensions,
            funnel_rows=funnel_rows,
            stocks_rows=stocks_rows,
            finance_rows=finance_rows,
        )
    except Exception as exc:
        logistics_formula_model = {
            "status": "error",
            "missing_inputs": [],
            "inputs_available": {},
            "explanation": "Расчётная модель логистики не собрана из-за ошибки.",
            "diagnostics": {
                "error": f"logistics_formula_model_failed: {exc}",
            },
        }

    config_local_order_share = _to_float_or_none(logistics_config.get("local_order_share"))
    config_localization_pct = _to_float_or_none(logistics_config.get("localization_pct"))
    if config_localization_pct is None and config_local_order_share is not None:
        config_localization_pct = round(max(0.0, min(1.0, float(config_local_order_share))) * 100.0, 2)
    config_locality_index = _to_float_or_none(logistics_config.get("locality_index"))
    config_irp_share = _to_float_or_none(logistics_config.get("irp"))
    config_sales_distribution_index_pct = (
        round(float(config_irp_share) * 100.0, 4) if config_irp_share is not None else None
    )

    has_logistics_config_override = any(
        value is not None
        for value in (
            config_localization_pct,
            config_locality_index,
            config_sales_distribution_index_pct,
        )
    )

    if isinstance(logistics_formula_model, dict) and has_logistics_config_override:
        if config_localization_pct is not None:
            logistics_formula_model["localization_share_pct"] = round(float(config_localization_pct), 2)

        input_candidates = (
            logistics_formula_model.get("input_candidates")
            if isinstance(logistics_formula_model.get("input_candidates"), dict)
            else {}
        )
        if config_localization_pct is not None:
            input_candidates["localization_share_pct"] = round(float(config_localization_pct), 2)
        if config_locality_index is not None:
            input_candidates["localization_index"] = round(float(config_locality_index), 4)
        if config_sales_distribution_index_pct is not None:
            input_candidates["sales_distribution_index_pct"] = round(float(config_sales_distribution_index_pct), 4)
        logistics_formula_model["input_candidates"] = input_candidates

        inputs_available = (
            logistics_formula_model.get("inputs_available")
            if isinstance(logistics_formula_model.get("inputs_available"), dict)
            else {}
        )
        if config_localization_pct is not None:
            inputs_available["localization_share_pct"] = True
        if config_locality_index is not None:
            inputs_available["localization_index"] = True
        if config_sales_distribution_index_pct is not None:
            inputs_available["sales_distribution_index_pct"] = True
        logistics_formula_model["inputs_available"] = inputs_available

        recalculated = compute_wb_logistics_estimate(
            volume_liters=_to_float_or_none(logistics_formula_model.get("volume_liters")),
            item_price=_to_float_or_none(logistics_formula_model.get("item_price")),
            warehouse_coef=_to_float_or_none(logistics_formula_model.get("warehouse_coef")) or 1.0,
            localization_share_pct=float(config_localization_pct) if config_localization_pct is not None else None,
            localization_index_override=config_locality_index,
            sales_distribution_index_pct_override=config_sales_distribution_index_pct,
            supply_type=SUPPLY_TYPE_BOX,
            is_sgt=False,
            is_courier_wb=False,
        )
        for key in (
            "base_logistics",
            "localization_index",
            "sales_distribution_index_pct",
            "sales_distribution_component",
            "estimated_delivery_cost",
            "neutral_estimated_delivery_cost",
            "overpayment_absolute",
            "overpayment_pct_vs_neutral",
            "estimated_reverse_logistics",
            "estimated_storage_daily",
            "missing_inputs",
            "explanation",
            "status",
            "diagnostics",
            "tariff_per_liter",
        ):
            if key in recalculated:
                logistics_formula_model[key] = recalculated.get(key)

        if config_irp_share is not None:
            logistics_formula_model["sales_distribution_index_share"] = round(float(config_irp_share), 6)

        effective_localization_pct = _to_float_or_none(logistics_formula_model.get("localization_share_pct"))
        if effective_localization_pct is not None:
            if float(effective_localization_pct) >= 70.0:
                logistics_formula_model["risk_level"] = "low"
            elif float(effective_localization_pct) >= 40.0:
                logistics_formula_model["risk_level"] = "medium"
            else:
                logistics_formula_model["risk_level"] = "high"

        has_delivery = _to_float_or_none(logistics_formula_model.get("estimated_delivery_cost")) is not None
        has_volume = bool((logistics_formula_model.get("inputs_available") or {}).get("volume_liters"))
        has_price = bool((logistics_formula_model.get("inputs_available") or {}).get("item_price"))
        if has_delivery and has_volume and has_price:
            logistics_formula_model["mode"] = "A"
        else:
            logistics_formula_model["mode"] = "B"

    logistics_summary = _build_cabinet_logistics_summary(
        funnel_summary=funnel_summary,
        financial_summary=financial_summary,
        logistics_config=logistics_config,
    )
    finance_status = "ok" if _to_int(financial_summary.get("rows_count")) > 0 else "missing"
    try:
        sku_performance = analyze_sku_performance(
            finance_summary=financial_summary,
            funnel_raw=funnel_rows,
            stocks_raw=stocks_rows,
            ads_raw=ads_rows,
            period_days=period_days,
            finance_status=finance_status,
        )
    except Exception as exc:
        sku_performance = {"error": f"sku_performance_failed: {exc}", "rows": [], "abc_summary": {}}

    sku_rows = (sku_performance.get("rows") or []) if isinstance(sku_performance, dict) else []
    sku_profit = sorted(
        [
            {
                "sku": _to_int(row.get("sku")),
                "revenue": round(_to_float(row.get("revenue")), 2),
                "profit": round(_to_float(row.get("profit")), 2),
                "margin": round(_to_float(row.get("margin")), 4),
                "orders": _to_int(row.get("orders")),
                "stock_qty": _to_int(row.get("stock_qty")),
                "buyouts": _to_int(row.get("buyouts")),
                "ad_spend": round(_to_float(row.get("ad_spend")), 2),
                "abc": str(row.get("abc") or "N/A"),
                "volume_liters": _to_float_or_none(
                    _sku_dimension_entry(sku_dimensions, _to_int(row.get("sku"))).get("volume_liters")
                ),
                "volume_source": _norm_text(
                    _sku_dimension_entry(sku_dimensions, _to_int(row.get("sku"))).get("source")
                ),
            }
            for row in sku_rows
        ],
        key=lambda x: x["profit"],
        reverse=True,
    )
    try:
        localization_loss = _build_localization_loss_payload(
            sku_rows=sku_profit,
            financial_summary=financial_summary,
            funnel_summary=funnel_summary,
            local_orders_insights=local_orders_insights,
            funnel_rows=funnel_rows,
            logistics_formula_model=logistics_formula_model if isinstance(logistics_formula_model, dict) else {},
        )
    except Exception as exc:
        localization_loss = {
            "status": "insufficient_data",
            "estimation_mode": "insufficient_data",
            "total_estimated_loss_rub": None,
            "loss_share_of_revenue": None,
            "non_local_orders_share": None,
            "affected_sku_count": 0,
            "top_loss_sku": [],
            "missing_inputs": [],
            "recommendations": [],
            "error": f"localization_loss_failed: {exc}",
        }
    try:
        top5_sku_unit_economics = _build_top5_sku_unit_economics_payload(
            sku_rows=sku_rows,
            financial_summary=financial_summary,
            sku_dimensions=sku_dimensions,
            wb_logistics_estimate=logistics_formula_model if isinstance(logistics_formula_model, dict) else {},
            local_orders_insights=local_orders_insights,
            localization_loss=localization_loss if isinstance(localization_loss, dict) else {},
        )
    except Exception as exc:
        top5_sku_unit_economics = {
            "available": False,
            "items": [],
            "message": "Не удалось построить ТОП-5 SKU по юнит-экономике.",
            "error": f"top5_unit_economics_failed: {exc}",
        }
    try:
        regional_logistics_impact = _build_regional_logistics_impact_payload(
            logistics_payload=logistics_payload if isinstance(logistics_payload, dict) else {},
            logistics_formula_model=logistics_formula_model if isinstance(logistics_formula_model, dict) else {},
            sku_rows=sku_rows,
            sku_dimensions=sku_dimensions,
            local_orders_insights=local_orders_insights,
            localization_loss=localization_loss if isinstance(localization_loss, dict) else {},
            top5_sku_unit_economics=top5_sku_unit_economics if isinstance(top5_sku_unit_economics, dict) else {},
        )
    except Exception as exc:
        regional_logistics_impact = {
            "status": "insufficient_data",
            "mode": "insufficient_data",
            "high_risk_regions": [],
            "top_sku_by_regional_risk": [],
            "total_estimated_overpay_rub": None,
            "missing_inputs": [],
            "recommendations": [],
            "error": f"regional_logistics_impact_failed: {exc}",
        }

    cogs_status = str(financial_summary.get("cogs_status") or "file_not_found")
    profit_without_cogs = cogs_status in {"file_not_found", "file_found_not_read", "file_read_not_matched"}
    financial_summary["profit_without_cogs"] = bool(profit_without_cogs)
    if cogs_status == "partial_match":
        financial_summary["profit_label"] = "Прибыль (частично с COGS)"
        financial_summary["profit_note"] = (
            "COGS сопоставлен частично: прибыль и маржа рассчитаны по доступной части себестоимости."
        )
    elif profit_without_cogs:
        financial_summary["profit_label"] = "Прибыль без учета себестоимости"
        if cogs_status == "file_not_found":
            financial_summary["profit_note"] = "COGS-файл не загружен; показатель прибыли не учитывает себестоимость."
        elif cogs_status == "file_found_not_read":
            financial_summary["profit_note"] = "COGS-файл найден, но не прочитан; прибыль рассчитана без себестоимости."
        else:
            financial_summary["profit_note"] = "COGS найден, но не сопоставлен с продажами; прибыль рассчитана без себестоимости."
    else:
        financial_summary["profit_label"] = "Прибыль"
        financial_summary["profit_note"] = "COGS применен в расчете прибыли."

    source_consistency_warnings = _build_source_consistency_warnings(financial_summary, funnel_summary)

    decision_layer = _build_decision_layer(
        finance=financial_summary,
        funnel=funnel_summary,
        ads=ads_summary,
        stock=stock_summary,
        sku_rows=sku_rows,
        search_insights=search_insights,
        missing_required=missing_required,
        missing_optional=missing_optional,
        source_consistency_warnings=source_consistency_warnings,
        profit_without_cogs=profit_without_cogs,
    )
    money_losses = _build_money_losses(
        ads_summary=ads_summary,
        decision_layer=decision_layer,
        financial_summary=financial_summary,
        sku_rows=sku_rows,
        stock_summary=stock_summary,
    )
    actions = _build_actions(
        decision_layer,
        stock_summary,
        logistics_formula_model=logistics_formula_model if isinstance(logistics_formula_model, dict) else None,
        localization_loss=localization_loss if isinstance(localization_loss, dict) else None,
        financial_summary=financial_summary,
    )

    parse_diagnostics = {
        "finance": finance_parse_diag,
        "ads": ads_parse_diag,
        "orders": orders_parse_diag,
        "stocks": stocks_parse_diag,
        "search": search_parse_diag,
        "cogs": cogs_parse_diag,
    }
    audit_period = _derive_audit_period(
        period_label=period_label,
        report_date=report_date,
        funnel_rows=funnel_rows,
        orders_rows=orders_rows,
        finance_rows=finance_rows,
        selected_files=selected_files,
        parse_diagnostics=parse_diagnostics,
        period_days=period_days,
    )

    inputs = _build_inputs_section(
        input_dir=input_dir,
        detected_files=detected_files,
        grouped_files=grouped_files,
        selected_files=selected_files,
        missing_required=missing_required,
        missing_optional=missing_optional,
        parse_diagnostics=parse_diagnostics,
    )

    return {
        "date": _iso(report_date),
        "report_type": "audit",
        "source": "wb",
        "timezone": str(WB_TIMEZONE),
        "tax_rate": tax_rate,
        "profit_without_cogs": bool(financial_summary.get("profit_without_cogs")),
        "cogs_status": financial_summary.get("cogs_status"),
        "period": {
            "label": period_label or _iso(report_date),
            "days": int(_to_int((audit_period or {}).get("days")) or period_days),
        },
        "audit_period": audit_period,
        "inputs": inputs,
        "financial_summary": financial_summary,
        "funnel_summary": funnel_summary,
        "ads_summary": ads_summary,
        "stock_summary": stock_summary,
        "sku_dimensions": sku_dimensions,
        "volume_coverage": volume_coverage,
        "search_insights": search_insights,
        "logistics_config": logistics_config,
        "logistics_summary": logistics_summary,
        "orders_with_geo": (
            local_orders_insights.get("orders_with_geo")
            if isinstance(local_orders_insights.get("orders_with_geo"), list)
            else []
        ),
        "local_orders_insights": local_orders_insights,
        "logistics_reference": {
            "regions": logistics_payload.get("reference") or {},
            "rows": logistics_payload.get("flat_reference") or [],
            "region_coefficients": logistics_payload.get("region_coefficients") or {},
            "regions_count": len(logistics_payload.get("reference") or {}),
            "warehouses_count": len(logistics_payload.get("flat_reference") or []),
            "source": "static_json",
            "source_path": "shared/data/warehouse_logistics_coefficients.json",
        },
        "wb_region_coefficients": logistics_payload.get("region_coefficients") or {},
        "region_logistics_summary": logistics_payload.get("region_summary") or {},
        "top_expensive_logistics_regions": logistics_payload.get("top_expensive_regions") or [],
        "logistics_regions_over_150": logistics_payload.get("regions_over_150") or [],
        "logistics_regions_low_coverage": logistics_payload.get("low_coverage_regions") or [],
        "logistics_regions_unknown": logistics_payload.get("unknown_regions") or [],
        "logistics_locality_signals": logistics_payload.get("locality_signals") or [],
        "logistics_potential_risk_regions": logistics_payload.get("potential_risk_regions") or [],
        "logistics_diagnostics": {
            "error": str(logistics_payload.get("error") or ""),
        },
        "logistics_formula_model": logistics_formula_model,
        "wb_logistics_estimate": logistics_formula_model,
        "localization_loss": localization_loss,
        "regional_logistics_impact": regional_logistics_impact,
        "cogs_input": {
            "rows_count": len(cogs_rows),
            "rows": cogs_rows[:200],
            "loaded": bool(cogs_rows),
            "parse_diagnostics": cogs_parse_diag,
            "cogs_status": financial_summary.get("cogs_status"),
            "cogs_file_found": bool(selected_files["cogs"]),
            "cogs_rows_loaded": (financial_summary.get("cogs_diagnostics") or {}).get("cogs_rows_loaded")
            if isinstance(financial_summary.get("cogs_diagnostics"), dict)
            else None,
            "cogs_sku_total": (financial_summary.get("cogs_diagnostics") or {}).get("cogs_sku_total")
            if isinstance(financial_summary.get("cogs_diagnostics"), dict)
            else None,
            "cogs_matched_sku": (financial_summary.get("cogs_diagnostics") or {}).get("cogs_matched_sku")
            if isinstance(financial_summary.get("cogs_diagnostics"), dict)
            else None,
            "cogs_unmatched_sku": (financial_summary.get("cogs_diagnostics") or {}).get("cogs_unmatched_sku")
            if isinstance(financial_summary.get("cogs_diagnostics"), dict)
            else [],
            "cogs_match_key": (financial_summary.get("cogs_diagnostics") or {}).get("cogs_match_key")
            if isinstance(financial_summary.get("cogs_diagnostics"), dict)
            else "nm_id|seller_article",
            "cogs_total": financial_summary.get("cogs_total"),
        },
        "sku_financials": (financial_summary.get("sku_financials") if isinstance(financial_summary.get("sku_financials"), dict) else {}),
        "sku_profit": sku_profit,
        "top5_sku_unit_economics": top5_sku_unit_economics,
        "abc_analysis": (sku_performance.get("abc_summary") if isinstance(sku_performance, dict) else {}) or {},
        "decision_layer": decision_layer,
        "money_losses": money_losses,
        "actions": actions,
        "source_consistency_warnings": source_consistency_warnings,
        "notes": [
            "Аудит собран из файлов в audit/input без WB API.",
            "При отсутствии части файлов аудит строится по доступным данным и помечается как partial.",
            "Обязательные блоки: finance, funnel, stocks. Опциональные: ads, search, orders, cogs.",
        ],
    }
