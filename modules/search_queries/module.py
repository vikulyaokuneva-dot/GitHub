"""Search queries module entrypoint."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.search_queries.engine import (
    build_search_queries_by_sku,
    build_search_queries_summary,
)
from modules.search_queries.normalizer import normalize_search_queries_rows
from modules.search_queries.reader import read_search_queries_xlsx
from shared.io.json_io import write_json


def run(seller_path: str | Path) -> dict[str, Any]:
    """Run search queries pipeline for one seller."""
    seller_root = Path(seller_path)
    input_path = seller_root / "raw" / "search_queries.xlsx"
    summary_path = seller_root / "analytics" / "search_queries_summary.json"
    by_sku_path = seller_root / "analytics" / "search_queries_by_sku.json"

    read_result = read_search_queries_xlsx(input_path)
    status = str(read_result.get("status") or "read_error")
    message = str(read_result.get("message") or "")
    sheet_name = read_result.get("sheet_name")
    header_row_index = read_result.get("header_row_index")
    recognized_columns = read_result.get("recognized_columns") or {}
    has_sku_columns = bool(read_result.get("has_sku_columns", False))

    if status != "ok":
        summary = {
            "status": status,
            "message": message,
            "sheet_name": sheet_name,
            "header_row_index": header_row_index,
            "recognized_columns": recognized_columns,
            "total_rows": 0,
            "unique_queries": 0,
            "unique_skus": 0,
            "top_queries_by_query_count": [],
            "top_queries_by_clicks": [],
            "top_queries_by_add_to_cart": [],
            "top_queries_with_no_orders": [],
            "top_queries_low_visibility": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        by_sku = {
            "status": status,
            "message": message,
            "sheet_name": sheet_name,
            "header_row_index": header_row_index,
            "recognized_columns": recognized_columns,
            "total_skus": 0,
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(summary_path, summary)
        write_json(by_sku_path, by_sku)
        print(f"[search_queries] {status}: {message}")
        return {
            "status": status,
            "message": message,
            "sheet_name": sheet_name,
            "total_rows": 0,
            "summary_path": str(summary_path),
            "by_sku_path": str(by_sku_path),
        }

    raw_rows = read_result.get("rows") or []
    normalized_rows = normalize_search_queries_rows(raw_rows, recognized_columns=recognized_columns)
    summary = build_search_queries_summary(normalized_rows, has_sku_columns=has_sku_columns)
    by_sku = build_search_queries_by_sku(normalized_rows, has_sku_columns=has_sku_columns)
    final_status = "ok" if has_sku_columns else "query_only_mode"
    final_message = message
    if not has_sku_columns:
        final_message = "SKU columns were not detected; summary built in query-only mode"

    summary["status"] = final_status
    summary["message"] = final_message
    summary["sheet_name"] = sheet_name
    summary["header_row_index"] = header_row_index
    summary["recognized_columns"] = recognized_columns
    summary["input_file"] = str(input_path)
    by_sku["status"] = final_status
    by_sku["message"] = final_message
    by_sku["sheet_name"] = sheet_name
    by_sku["header_row_index"] = header_row_index
    by_sku["recognized_columns"] = recognized_columns
    by_sku["input_file"] = str(input_path)

    write_json(summary_path, summary)
    write_json(by_sku_path, by_sku)
    print(
        f"[search_queries] {final_status}: rows={summary['total_rows']} "
        f"queries={summary['unique_queries']} skus={summary['unique_skus']} "
        f"sheet={sheet_name}"
    )
    return {
        "status": final_status,
        "message": final_message,
        "sheet_name": sheet_name,
        "header_row_index": header_row_index,
        "recognized_columns": recognized_columns,
        "total_rows": summary["total_rows"],
        "summary_path": str(summary_path),
        "by_sku_path": str(by_sku_path),
    }
