from __future__ import annotations
from typing import Any, Dict, List
import os
from datetime import datetime

from ..ctx import SellerContext
from ..pdf_render import write_text_pdf
from ..storage import ensure_dir, write_json


def run(ctx: SellerContext, facts: Dict[str, Any], metrics: Dict[str, Any], warnings: List[Dict[str, Any]]) -> str:
    run_paths = ctx.paths.for_date(ctx.run_date)
    ensure_dir(run_paths.reports_dir)

    pdf_path = os.path.join(run_paths.reports_dir, "report.pdf")
    confidence = str(facts.get("data_confidence", "n/a"))

    warning_lines = [f"- {w.get('code', '')}: {w.get('message', '')}" for w in warnings]
    if not warning_lines:
        warning_lines = ["- none"]

    lines = [
        f"seller_id: {ctx.seller_id}",
        f"date: {ctx.run_date}",
        f"confidence: {confidence}",
        "warnings:",
        *warning_lines,
    ]

    write_text_pdf(pdf_path, lines)

    write_json(
        os.path.join(run_paths.reports_dir, "report_meta.json"),
        {"pdf_path": pdf_path, "generated_at": datetime.utcnow().isoformat() + "Z"},
    )

    return pdf_path
