from __future__ import annotations

import json
from pathlib import Path

from report_v2.builders.report_payload_builder import (
    build_commerce_section_v2,
    build_diagnostics_v2,
    build_finance_section_v2,
    build_finance_alignment_notice_v2,
    build_hero_v2,
    build_live_section_v2,
    build_report_payload_v2,
)
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
    assert payload["diagnostics"]["warnings_count"] == len(payload["diagnostics"]["warnings"])
    assert any(item.get("code") == "buyouts_owner_from_cabinet_commerce" for item in payload["diagnostics"]["warnings"])
    assert payload["hero"]["title"] == "Ежедневный отчёт WB"
    assert len(payload["hero"]["cards"]) == 4
    assert payload["commerce_section"]["status"] == "ok"
    assert payload["finance_section"]["status"] == "ok"
    assert payload["live_section"]["status"] == "ok"


def test_commerce_section_v2_contains_display_rows() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["label"]: item for item in payload["commerce_section"]["rows"]}

    assert rows["Заказы"]["value"] == "5 шт"
    assert rows["Сумма заказов"]["value"] == "4 260 ₽"
    assert rows["Выкупы"]["value"] == "2 шт"
    assert rows["Сумма выкупов"]["value"] == "1 700 ₽"
    assert rows["Источник"]["value"] == "sales_funnel_api"


def test_finance_section_v2_contains_display_rows() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["label"]: item for item in payload["finance_section"]["rows"]}

    assert rows["К перечислению продавцу"]["value"] == "4 868,22 ₽"
    assert rows["Комиссия WB"]["value"] == "-329,75 ₽"
    assert rows["Логистика"]["value"] == "3 ₽"
    assert rows["Хранение"]["value"] == "68,37 ₽"
    assert rows["Эквайринг"]["value"] == "186,08 ₽"


def test_live_section_v2_contains_display_rows() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["label"]: item for item in payload["live_section"]["rows"]}

    assert rows["Live orders"]["value"] == "3 шт"
    assert rows["Live sales"]["value"] == "3 шт"
    assert rows["Остатки"]["value"] == "322 шт"
    assert rows["Дата среза остатков"]["value"] == "2026-04-22"


def test_section_helpers_mark_unavailable_values() -> None:
    commerce = build_commerce_section_v2({"available": False})
    finance = build_finance_section_v2({"available": False, "status": "unavailable"})
    live = build_live_section_v2({"status": "unavailable", "orders": {}, "sales": {}, "stocks": {}})

    assert commerce["rows"][0]["value"] == "нет данных"
    assert commerce["rows"][0]["status"] == "unavailable"
    assert finance["rows"][1]["value"] == "нет данных"
    assert finance["rows"][1]["status"] == "unavailable"
    assert live["rows"][0]["value"] == "нет данных"
    assert live["rows"][0]["status"] == "unavailable"


def test_hero_v2_formats_kpi_cards() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    cards = {item["label"]: item for item in payload["hero"]["cards"]}

    assert cards["Заказы"]["value"] == "5 шт"
    assert cards["Заказы"]["subvalue"] == "4 260 ₽"
    assert cards["Выкупы"]["value"] == "2 шт"
    assert cards["Выкупы"]["subvalue"] == "1 700 ₽"
    assert cards["К перечислению"]["value"] == "4 868,22 ₽"
    assert cards["Остатки"]["value"] == "322 шт"


def test_hero_v2_data_status_partial_for_missing_finance() -> None:
    snapshot = _sample_snapshot()
    snapshot.pop("finance_final_daily")

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    cards = {item["label"]: item for item in payload["hero"]["cards"]}

    assert payload["hero"]["data_status"] == "partial"
    assert "Часть основных данных" in payload["hero"]["data_status_message"]
    assert cards["К перечислению"]["value"] == "нет данных"
    assert cards["К перечислению"]["status"] == "unavailable"


def test_build_hero_v2_uses_prepared_blocks_only() -> None:
    hero = build_hero_v2(
        meta={"seller_id": "seller_001", "operational_date": "2026-04-21"},
        cabinet_commerce={"available": True, "orders_count": 5, "orders_amount": 4260, "buyouts_count": 2, "buyouts_amount": 1700},
        finance_final={"available": True, "status": "ok", "seller_payout": 4868.22, "source": "finance_detailed_api"},
        live_operational={"stocks": {"available": True, "total_units": 322, "snapshot_date": "2026-04-22"}},
        warnings=[],
    )

    assert hero["subtitle"] == "Кабинет: seller_001 | Дата: 2026-04-21"
    assert hero["data_status"] == "ok"
    assert len(hero["cards"]) == 4


def test_diagnostics_v2_contains_builder_warnings() -> None:
    builder_warnings = [
        {"code": "builder_warning", "level": "warning", "block": "builder", "message": "Builder warning."}
    ]

    diagnostics = build_diagnostics_v2(_sample_snapshot(), debug=None, builder_warnings=builder_warnings)

    assert diagnostics["warnings_count"] == 1
    assert diagnostics["warnings"][0] == {
        "code": "builder_warning",
        "level": "warning",
        "block": "builder",
        "message": "Builder warning.",
    }


def test_diagnostics_v2_contains_debug_warnings() -> None:
    debug = {
        "warnings": [
            {"code": "debug_source_warning", "level": "info", "block": "debug", "message": "Debug warning."},
            "Plain debug warning.",
        ],
    }

    diagnostics = build_diagnostics_v2(_sample_snapshot(), debug=debug, builder_warnings=[])

    warning_codes = {item.get("code") for item in diagnostics["warnings"]}
    assert "debug_source_warning" in warning_codes
    assert "warning" in warning_codes
    assert diagnostics["warnings_count"] == 2


def test_diagnostics_v2_contains_source_flags() -> None:
    diagnostics = build_diagnostics_v2(_sample_snapshot(), debug=_sample_debug(), builder_warnings=[])

    flags = {item["name"]: item for item in diagnostics["source_flags"]}

    assert flags["cabinet_commerce.available"]["value"] == "true"
    assert flags["cabinet_commerce.status"]["status"] == "ok"
    assert flags["cabinet_commerce.source"]["value"] == "sales_funnel_api"
    assert flags["finance_final.available"]["value"] == "true"
    assert flags["finance_final.status"]["value"] == "ok"
    assert flags["finance_final.source"]["value"] == "finance_detailed_api"
    assert flags["finance_final.date_aligned"]["value"] == "true"
    assert flags["live_operational.orders.available"]["value"] == "true"
    assert flags["live_operational.sales.available"]["value"] == "true"
    assert flags["live_operational.stocks.available"]["value"] == "true"
    assert flags["debug_present"]["value"] == "true"


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
    assert info["hero_cards_count"] == 4
    assert info["hero_data_status"] == payload["hero"]["data_status"]
    assert info["commerce_section_rows_count"] == 5
    assert info["finance_section_rows_count"] == 7
    assert info["live_section_rows_count"] == 4
    assert info["diagnostics_source_flags_count"] > 0


def test_write_report_pdf_v2_creates_pdf_with_display_sections(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_sections.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["commerce_section_rows_count"] == len(payload["commerce_section"]["rows"])
    assert info["finance_section_rows_count"] == len(payload["finance_section"]["rows"])
    assert info["live_section_rows_count"] == len(payload["live_section"]["rows"])


def test_write_report_pdf_v2_creates_pdf_with_hero_block(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_hero.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["hero"]["cards"][0]["label"] == "Заказы"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_cards_count"] == 4


def test_write_report_pdf_v2_creates_pdf_with_diagnostics_section(tmp_path: Path) -> None:
    debug = {"warnings": [{"code": "debug_pdf_warning", "message": "Debug PDF warning.", "block": "debug"}]}
    payload = build_report_payload_v2(_sample_snapshot(), debug=debug)
    pdf_path = tmp_path / "report_v2_diagnostics.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert any(item.get("code") == "debug_pdf_warning" for item in payload["diagnostics"]["warnings"])
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["diagnostics_warnings_count"] >= 1
    assert info["diagnostics_source_flags_count"] > 0


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
    assert any(item.get("code") == "finance_final_missing" for item in payload["diagnostics"]["warnings"])
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
        content = path.read_text(encoding="utf-8")
        assert "daily_report_stage" not in content
        assert "daily_kpi" not in content
        assert "render_kpi" not in content
        assert "financial_kpi" not in content
        assert 'metrics["totals"]' not in content
        assert "metrics['totals']" not in content
