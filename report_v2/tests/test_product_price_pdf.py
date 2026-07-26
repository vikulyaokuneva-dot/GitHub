from __future__ import annotations

from pypdf import PdfReader

from report_v2.builders.report_payload_builder import _build_product_price_sections
from report_v2.renderers.pdf_renderer_v2 import write_report_pdf_v2


def test_daily_payload_price_section_contains_every_sku_and_unit_profit() -> None:
    snapshot = {
        "price_analytics": {
            "source": "goods_filter_v2+fbs_orders_v3",
            "sku_rows": [
                {
                    "nm_id": "101",
                    "seller_base_price": "1000.00",
                    "platform_discount_percent": "52.00",
                    "buyer_price_before_wallet": "480.00",
                    "buyer_final_price": "432.00",
                    "wallet_discount_percent": "10.00",
                    "data_quality_status": "complete",
                }
            ],
            "reconciliation": {"status": "matched"},
        }
    }
    sku_detail = {
        "all_skus": [
            {
                "nm_id": "101",
                "buyouts_count": 2,
                "profit": "200.00",
                "margin_pct": "20.00",
                "finance_attribution": "direct",
            },
            {
                "nm_id": "102",
                "buyouts_count": 1,
                "profit": "50.00",
                "margin_pct": "10.00",
                "finance_attribution": "missing",
            },
        ]
    }

    price_section, changes_section = _build_product_price_sections(
        snapshot,
        sku_detail_section=sku_detail,
    )
    rows = {row["sku"]: row for row in price_section["sku_rows"]}

    assert set(rows) == {"101", "102"}
    assert rows["101"]["profit_per_unit"] == "100.00"
    assert rows["101"]["wallet_discount_percent"] == "10.00"
    assert rows["102"]["seller_base_price"] is None
    assert rows["102"]["profit"] is None
    assert changes_section["automatic_price_changes"] is False


def test_pdf_displays_product_price_columns_and_missing_state(tmp_path) -> None:
    target = tmp_path / "price_report.pdf"
    payload = {
        "meta": {"seller_id": "seller_1", "report_date": "2026-07-25", "operational_date": "2026-07-24"},
        "hero": {"title": "ИИ Директор WB", "subtitle": "", "cards": []},
        "diagnostics": {"warnings": [], "source_flags": []},
        "product_price_analytics_section": {
            "title": "Цены по SKU",
            "subtitle": "Платформенная скидка WB отделена от скидки WB Кошелька.",
            "sku_rows": [
                {
                    "sku": "101",
                    "seller_base_price": "1000.00",
                    "platform_discount_percent": "52.00",
                    "buyer_final_price": "480.00",
                    "buyouts": 1,
                    "profit": "200.00",
                    "margin_percent": "41.67",
                },
                {
                    "sku": "102",
                    "seller_base_price": None,
                    "platform_discount_percent": None,
                    "buyer_final_price": None,
                    "buyouts": 0,
                    "profit": None,
                    "margin_percent": None,
                },
            ],
            "reconciliation": {
                "sku_buyer_final_total": "480.00",
                "fbs_orders_buyer_final_total": "480.00",
                "status": "matched",
            },
        },
        "price_changes_section": {
            "title": "Изменение цен и скидок",
            "subtitle": "Только аналитика и рекомендации.",
            "rows": [
                {
                    "sku": "101",
                    "platform_discount_change_day": "2.00",
                    "seller_price_change_day": "0.00",
                    "buyer_price_change_day": "-20.00",
                    "potential_price_increase_reserve": "20.00",
                }
            ],
            "recommendations": [],
        },
    }

    result = write_report_pdf_v2(target, payload)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(target).pages)

    assert result["product_price_rows_count"] == 2
    assert "Цена продавца" in text
    assert "Скидка WB" in text
    assert "Цена покупателя" in text
    assert "Изменение цен и скидок" in text
    assert "нет данных" in text
