"""Tests for v5 JSON exporter required artifacts."""

from __future__ import annotations

import json
from datetime import date

from ..domain.cabinet import Cabinet, CabinetConfig, CabinetContext
from ..domain.contracts import (
    FactsBundle,
    MetricsBundle,
    NormalizedDataBundle,
    PortfolioMetrics,
    RawDataBundle,
)
from ..outputs.json_exporter import JsonExporter


def _build_ctx(tmp_path) -> CabinetContext:
    return CabinetContext(
        cabinet=Cabinet(
            id="seller_001",
            name="Seller 001",
            api_key="token",
            wb_seller_id="seller_001",
        ),
        config=CabinetConfig(),
        cabinet_root=tmp_path / "seller_001" / "v5",
    )


def test_export_required_artifacts_writes_source_counts_comparison(tmp_path) -> None:
    ctx = _build_ctx(tmp_path)
    exporter = JsonExporter(ctx)

    target_date = date(2026, 4, 1)
    report_pdf = ctx.outputs_dir / "report_temp.pdf"
    report_pdf.parent.mkdir(parents=True, exist_ok=True)
    report_pdf.write_bytes(b"%PDF-1.4\n%v5 test\n")

    metrics = MetricsBundle(
        cabinet_id=ctx.cabinet.id,
        period_date=target_date,
        portfolio_metrics=PortfolioMetrics(
            total_spend=0.0,
            total_revenue=0.0,
            total_profit=0.0,
            avg_roas=0.0,
            avg_cpc=0.0,
            avg_ctr=0.0,
            portfolio_efficiency_score=0.0,
        ),
        financial_summary={"financial_finality_status": "partial", "debug": {"rows_count": 0}},
    )
    facts = FactsBundle(cabinet_id=ctx.cabinet.id, period_date=target_date)
    raw_bundle = RawDataBundle(
        cabinet_id=ctx.cabinet.id,
        period_date=target_date,
        source="api",
        debug={
            "source_counts_comparison": {
                "v2_truth_counts": {"ads_count": 5},
                "v5_compat_counts": {"ads_count": 6},
                "not_less_than_v2": {"ads_count": True},
            }
        },
    )
    normalized = NormalizedDataBundle(cabinet_id=ctx.cabinet.id, period_date=target_date)

    exported = exporter.export_required_artifacts(
        run_date=date(2026, 4, 2),
        report_date=target_date,
        date_shift_applied=True,
        date_shift_reason="daily mode uses previous day because WB current-day data is incomplete",
        mode="daily",
        metrics=metrics,
        facts=facts,
        warnings=[],
        report_pdf_path=report_pdf,
        raw_bundle=raw_bundle,
        normalized_bundle=normalized,
    )

    comparison_path = exported.get("debug_source_counts_comparison")
    assert comparison_path is not None
    assert comparison_path.exists()

    payload = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert payload["v2_truth_counts"]["ads_count"] == 5

    report_meta = json.loads(ctx.report_meta_path.read_text(encoding="utf-8"))
    assert report_meta["paths"]["source_counts_comparison_json"]

