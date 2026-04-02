"""Main pipeline runner."""

from __future__ import annotations

from pathlib import Path

from pipeline.steps.assortment import run as run_assortment
from pipeline.steps.finance import run as run_finance
from pipeline.steps.ingest import run as run_ingest
from pipeline.steps.reporting import run as run_reporting
from pipeline.steps.search_queries import run as run_search_queries
from shared.config.seller_config import load_seller_config
from shared.dates.date_policy import get_report_date
from shared.paths.paths import get_paths


def _ensure_runtime_dirs(paths: dict[str, Path]) -> None:
    for key in ("config", "raw", "normalized", "analytics", "artifacts", "outputs"):
        paths[key].mkdir(parents=True, exist_ok=True)


def run_pipeline(seller: str, mode: str = "daily") -> dict:
    """Run ingest -> finance -> assortment -> reporting."""
    paths = get_paths(seller)
    _ensure_runtime_dirs(paths)
    report_date = get_report_date()
    seller_config = load_seller_config(seller)

    run_ingest(paths=paths, mode=mode, report_date=report_date)
    finance_summary = run_finance(
        paths=paths,
        mode=mode,
        report_date=report_date,
        seller_config=seller_config,
    )
    assortment_summary = run_assortment(paths=paths, mode=mode, report_date=report_date)
    search_queries_summary = run_search_queries(paths=paths, mode=mode, report_date=report_date)
    report = run_reporting(
        paths=paths,
        mode=mode,
        report_date=report_date,
        seller_config=seller_config,
    )

    return {
        "seller": seller,
        "mode": mode,
        "report_date": report_date.isoformat(),
        "finance_summary": finance_summary,
        "assortment_summary": assortment_summary,
        "search_queries_summary": search_queries_summary,
        "report": report,
    }
