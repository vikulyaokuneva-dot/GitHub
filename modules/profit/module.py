"""Profit module entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.profit.cogs_loader import load_cogs_xlsx
from modules.profit.profit_engine import build_sku_profit
from shared.io.json_io import read_json, write_json


def _load_facts_for_seller(seller_root: Path) -> tuple[dict[str, Any], str]:
    candidates = [
        seller_root / "raw" / "facts.json",
        seller_root / "analytics" / "facts.json",
        seller_root / "outputs" / "facts.json",
    ]

    for path in candidates:
        payload = read_json(path)
        if isinstance(payload, dict):
            return payload, str(path)

    # Soft fallback: minimal facts from report.json if full facts are absent.
    report = read_json(seller_root / "outputs" / "report.json")
    if isinstance(report, dict):
        return {
            "date": report.get("report_date"),
            "report_date": report.get("report_date"),
            "finance_status": report.get("finance_status") or "missing",
            "financial_summary": report.get("finance_summary") or {},
            "sku_performance": {"rows": []},
        }, str(seller_root / "outputs" / "report.json")

    return {
        "finance_status": "missing",
        "sku_performance": {"rows": []},
    }, "not_found"


def run(seller_path: str | Path) -> dict[str, Any]:
    """Run profit calculations for seller and persist sku_profit.json."""
    seller_root = Path(seller_path)
    analytics_dir = seller_root / "analytics"
    out_path = analytics_dir / "sku_profit.json"
    cogs_path = seller_root / "raw" / "cogs.xlsx"

    facts, facts_source = _load_facts_for_seller(seller_root)
    cogs_result = load_cogs_xlsx(cogs_path)
    cogs_items = cogs_result.get("items") if isinstance(cogs_result, dict) else {}
    if not isinstance(cogs_items, dict):
        cogs_items = {}

    payload = build_sku_profit(
        facts=facts if isinstance(facts, dict) else {},
        cogs_by_seller_sku={str(k).strip().lower(): float(v) for k, v in cogs_items.items()},
    )
    payload["input"] = {
        "facts_source": facts_source,
        "cogs_source": str(cogs_path),
        "cogs_status": str((cogs_result or {}).get("status", "unknown")),
    }
    cogs_warnings = (cogs_result or {}).get("warnings") if isinstance(cogs_result, dict) else []
    if isinstance(cogs_warnings, list) and cogs_warnings:
        merged = list(payload.get("warnings") or []) + [str(x) for x in cogs_warnings]
        # Deduplicate
        dedup = []
        seen = set()
        for item in merged:
            if item in seen:
                continue
            seen.add(item)
            dedup.append(item)
        payload["warnings"] = dedup

    if not payload.get("items"):
        payload["message"] = "No per-SKU rows found in facts. Output generated in safe-mode."

    write_json(out_path, payload)
    return {
        "status": str(payload.get("status", "ok")),
        "path": str(out_path),
        "items_count": len(payload.get("items") or []),
    }

