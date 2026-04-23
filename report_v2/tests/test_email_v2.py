from __future__ import annotations

import json
from pathlib import Path

from report_v2.builders.report_payload_builder import build_report_payload_v2
from report_v2.renderers.email_renderer_v2 import render_email_html, render_email_text
from report_v2.run_report_v2 import build_report_v2_from_files


def _sample_snapshot() -> dict:
    return {
        "seller_id": "seller_001",
        "run_date": "2026-04-21",
        "operational_date": "2026-04-21",
        "source_mode": "wb_api_core_v2",
        "cabinet_commerce_daily": {
            "source": "sales_funnel_api",
            "available": True,
            "target_date": "2026-04-21",
            "orders_count": 5.0,
            "orders_amount": 4260.0,
            "buyouts_count": 2.0,
            "buyouts_amount": 1700.0,
        },
        "finance_final_daily": {
            "source": "finance_detailed_api",
            "available": True,
            "target_date": "2026-04-21",
            "actual_date": "2026-04-21",
            "date_aligned": True,
            "gross_revenue": 4652.0,
            "seller_payout": 4868.22,
            "wb_commission": -329.75,
            "logistics": 3.0,
            "storage": 68.37,
            "acquiring": 186.08,
        },
        "live_operational": {
            "orders": {
                "source": "orders_api",
                "available": True,
                "target_date": "2026-04-21",
                "count": 3.0,
                "amount": 2500.0,
            },
            "sales": {
                "source": "sales_api",
                "available": True,
                "target_date": "2026-04-21",
                "count": 3.0,
                "amount": 7160.0,
            },
            "stocks": {
                "source": "stocks_api",
                "available": True,
                "snapshot_kind": "live_snapshot",
                "operational_date_reference": "2026-04-21",
                "snapshot_date": "2026-04-22",
                "total_units": 322.0,
            },
        },
    }


def _sample_debug() -> dict:
    return {"warnings": [], "endpoints": {"cabinet_commerce": {}, "finance_final": {}, "orders": {}, "sales": {}, "stocks": {}}}


def test_render_email_html_contains_seller_and_orders_count() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    html = render_email_html(payload)

    assert "seller_001" in html
    assert "orders_count" in html
    assert "5" in html


def test_render_email_text_contains_finance_block() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    text = render_email_text(payload)

    assert "Finance:" in text
    assert "Gross revenue: 4 652.00" in text
    assert "Seller payout: 4 868.22" in text


def test_runner_writes_email_files(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    debug_path = tmp_path / "debug.json"
    snapshot_path.write_text(json.dumps(_sample_snapshot(), ensure_ascii=False), encoding="utf-8")
    debug_path.write_text(json.dumps(_sample_debug(), ensure_ascii=False), encoding="utf-8")

    result = build_report_v2_from_files(snapshot_path=snapshot_path, debug_path=debug_path, out_dir=tmp_path / "out")

    html_path = Path(result["email_html_path"])
    txt_path = Path(result["email_txt_path"])

    assert html_path.exists()
    assert txt_path.exists()
    assert "WB Core Report v2" in html_path.read_text(encoding="utf-8")
    assert "Finance:" in txt_path.read_text(encoding="utf-8")
