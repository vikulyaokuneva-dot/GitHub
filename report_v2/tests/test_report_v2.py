from __future__ import annotations

import json
from pathlib import Path

from report_v2.builders.report_payload_builder import build_finance_alignment_notice_v2, build_report_payload_v2
from report_v2.renderers.pdf_renderer_v2 import write_report_pdf_v2
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


def test_build_report_payload_v2_maps_valid_snapshot() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    assert payload["meta"]["seller_id"] == "seller_001"
    assert payload["meta"]["report_date"] == "2026-04-21"
    assert payload["cabinet_commerce"]["orders_count"] == 5
    assert payload["cabinet_commerce"]["orders_amount"] == 4260.0
    assert payload["cabinet_commerce"]["buyouts_count"] == 2
    assert payload["cabinet_commerce"]["buyouts_amount"] == 1700.0
    assert payload["finance_final"]["seller_payout"] == 4868.22
    assert payload["finance_alignment_notice"]["state"] == "ok"
    assert payload["live_operational"]["stocks"]["total_units"] == 322
    assert payload["source_flags"]["buyouts_owner"] == "cabinet_commerce_daily"


def test_finance_alignment_notice_ok_for_aligned_finance() -> None:
    notice = build_finance_alignment_notice_v2(_sample_snapshot()["finance_final_daily"])

    assert notice["state"] == "ok"
    assert notice["title"] == ""
    assert notice["lines"] == []
    assert notice["target_date"] == "2026-04-21"
    assert notice["actual_date"] == "2026-04-21"


def test_finance_alignment_notice_lagged_for_misaligned_finance() -> None:
    finance = dict(_sample_snapshot()["finance_final_daily"])
    finance["date_aligned"] = False
    finance["actual_date"] = "2026-04-20"

    notice = build_finance_alignment_notice_v2(finance)

    assert notice["state"] == "lagged"
    assert notice["title"] == "Финансовые данные с лагом"
    assert "Финансовые данные относятся не к операционному дню отчёта." in notice["lines"]
    assert "Операционный день: 2026-04-21" in notice["lines"]
    assert "Фактическая дата финансов: 2026-04-20" in notice["lines"]


def test_finance_alignment_notice_unavailable_for_missing_or_unavailable_finance() -> None:
    missing_notice = build_finance_alignment_notice_v2(None)
    unavailable_finance = dict(_sample_snapshot()["finance_final_daily"])
    unavailable_finance["available"] = False

    unavailable_notice = build_finance_alignment_notice_v2(unavailable_finance)

    assert missing_notice["state"] == "unavailable"
    assert missing_notice["title"] == "Финансовый контур недоступен"
    assert missing_notice["lines"] == ["Финансовые данные за день не получены из wb_api_core."]
    assert unavailable_notice["state"] == "unavailable"


def test_write_report_pdf_v2_creates_pdf_for_valid_snapshot(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["finance_section_state"] == "ok"


def test_write_report_pdf_v2_creates_pdf_with_lagged_notice(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    snapshot["finance_final_daily"]["date_aligned"] = False
    snapshot["finance_final_daily"]["actual_date"] = "2026-04-20"
    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_lagged_finance.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["finance_alignment_notice"]["state"] == "lagged"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["finance_notice_state"] == "lagged"


def test_missing_finance_block_keeps_pdf_v2_buildable(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    snapshot.pop("finance_final_daily")
    payload = build_report_payload_v2(snapshot, debug=None)
    pdf_path = tmp_path / "report_v2_missing_finance.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["finance_final"]["available"] is False
    assert payload["finance_alignment_notice"]["state"] == "unavailable"
    assert any(item.get("code") == "finance_final_missing" for item in payload["warnings"])
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["finance_section_state"] == "unavailable"


def test_build_report_v2_from_files_writes_payload_and_pdf(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    debug_path = tmp_path / "debug.json"
    snapshot_path.write_text(json.dumps(_sample_snapshot(), ensure_ascii=False), encoding="utf-8")
    debug_path.write_text(json.dumps(_sample_debug(), ensure_ascii=False), encoding="utf-8")

    result = build_report_v2_from_files(snapshot_path=snapshot_path, debug_path=debug_path, out_dir=tmp_path / "out")

    payload_path = Path(result["payload_path"])
    pdf_path = Path(result["pdf_path"])
    saved_payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert payload_path.exists()
    assert pdf_path.exists()
    assert saved_payload["meta"]["seller_id"] == "seller_001"
    assert saved_payload["finance_alignment_notice"]["state"] == "ok"


def test_report_v2_does_not_import_legacy_daily_report_stage() -> None:
    package_root = Path(__file__).resolve().parents[1]
    checked_files = [
        package_root / "contracts" / "report_payload_schema.py",
        package_root / "builders" / "report_payload_builder.py",
        package_root / "renderers" / "pdf_renderer_v2.py",
    ]

    for path in checked_files:
        assert "daily_report_stage" not in path.read_text(encoding="utf-8")
