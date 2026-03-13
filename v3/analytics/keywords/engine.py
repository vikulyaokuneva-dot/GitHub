from __future__ import annotations

from typing import Any, Dict, List, Mapping

from .query_classifier import DEFAULT_QUERY_THRESHOLDS, classify_query_items
from .query_extraction import extract_keyword_rows
from .query_metrics import build_query_metrics
from .query_summary import build_keyword_global_summary, build_sku_keyword_summaries
from .query_utils import append_warning_once, merge_thresholds


def _merge_warnings(*warning_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for warning_list in warning_lists:
        if not isinstance(warning_list, list):
            continue
        for item in warning_list:
            if not isinstance(item, dict):
                continue
            append_warning_once(
                merged,
                str(item.get("code") or "keyword_warning"),
                str(item.get("message") or ""),
            )
    return merged


def build_keyword_monitoring(
    source: Any,
    *,
    thresholds: Mapping[str, Any] | None = None,
    run_date: str = "",
) -> Dict[str, Any]:
    extraction = extract_keyword_rows(source)
    extracted_items = extraction.get("items", []) if isinstance(extraction, dict) else []
    if not isinstance(extracted_items, list):
        extracted_items = []

    resolved_thresholds = merge_thresholds(DEFAULT_QUERY_THRESHOLDS, thresholds)
    query_metrics = build_query_metrics([row for row in extracted_items if isinstance(row, dict)])
    query_items = classify_query_items(query_metrics, thresholds=resolved_thresholds)
    sku_items = build_sku_keyword_summaries(query_items)
    summary = build_keyword_global_summary(query_items, sku_items)

    warnings = _merge_warnings(extraction.get("warnings", []) if isinstance(extraction, dict) else [])

    if not query_items:
        append_warning_once(
            warnings,
            "keyword_monitoring_insufficient_data",
            "Keyword monitoring has no query-level rows for analysis.",
        )
        status = "insufficient_data"
    elif warnings:
        status = "partial"
    else:
        status = "ok"

    summary["status"] = status
    summary["warnings"] = list(warnings)

    return {
        "date": str(run_date or ""),
        "status": status,
        "warnings": warnings,
        "summary": summary,
        "items": query_items,
        "sku_items": sku_items,
        "query_items": query_items,
        "thresholds": resolved_thresholds,
        "source": {
            "status": str(extraction.get("status") or "insufficient_data") if isinstance(extraction, dict) else "insufficient_data",
            "stats": extraction.get("stats", {}) if isinstance(extraction, dict) else {},
        },
    }
