from __future__ import annotations

import json

from pypdf import PdfReader

from report_v2.builders.report_payload_builder import (
    _build_hero_section,
    _build_product_price_sections,
    _build_sku_detail_section,
    _normalize_abc_section_sku,
    build_abc_section_v2,
    build_funnel_section_v2,
)
from report_v2.renderers.pdf_renderer_v2 import write_report_pdf_v2


def test_daily_payload_price_section_contains_every_sku_and_unit_profit() -> None:
    snapshot = {
        "price_analytics": {
            "source": "goods_filter_v2+fbs_orders_v3",
            "sku_rows": [
                {
                    "nm_id": "101",
                    "seller_base_price": "1000.00",
                    "seller_discounted_price": "800.00",
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
                "financial_expenses_complete": True,
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
    assert rows["101"]["seller_price"] == "800.00"
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
        "search_section": {
            "title": "Поисковые запросы",
            "available": True,
            "summary": [
                {
                    "category": "Убыточные",
                    "count": 0,
                    "action": "Нет действий",
                    "priority": "—",
                    "detail": "Неэффективных запросов не найдено",
                }
            ],
            "sections": [],
            "total_actions": 0,
        },
        "product_price_analytics_section": {
            "title": "Цены по SKU",
            "subtitle": "Платформенная скидка WB отделена от скидки WB Кошелька.",
            "sku_rows": [
                {
                    "sku": "101",
                    "seller_price": "800.00",
                    "seller_base_price": "1000.00",
                    "platform_discount_percent": "52.00",
                    "buyer_final_price": "480.00",
                    "buyouts": 1,
                    "profit": "200.00",
                    "margin_percent": "41.67",
                    "financial_expenses_complete": True,
                },
                {
                    "sku": "102",
                    "seller_base_price": None,
                    "platform_discount_percent": None,
                    "buyer_final_price": None,
                    "buyouts": 0,
                    "profit": None,
                    "preliminary_income_before_wb_expenses": "100.00",
                    "margin_percent": None,
                    "financial_expenses_complete": False,
                },
            ],
            "reconciliation": {
                "sku_buyer_final_total": "480.00",
                "fbs_orders_buyer_final_total": "480.00",
                "status": "matched",
            },
            "status_rows": [
                {"label": "Цена продавца", "value": "available"},
                {"label": "FBS price data", "value": "unavailable"},
                {"label": "Цена покупателя", "value": "fallback/available"},
                {"label": "Финансовые расходы", "value": "unavailable"},
                {"label": "Чистая прибыль", "value": "unavailable"},
            ],
            "weighted_platform_discount_percent": "52.50",
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
    pages = PdfReader(target).pages
    page_texts = [(page.extract_text() or "").strip() for page in pages]
    text = "\n".join(page_texts)

    assert result["product_price_rows_count"] == 2
    assert "Цена продавца" in text
    assert "Скидка WB" in text
    assert "Цена покупателя" in text
    assert "Изменение цен и скидок" in text
    assert "нет данных" in text
    assert "800,00 ₽" in text
    assert "Предварит.:" in text
    assert "100,00 ₽" in text
    assert "Средневзвешенная платформенная скидка WB" in text
    assert all(page_texts[1:])


def test_price_section_keeps_active_skus_and_hides_inactive_price_only_rows() -> None:
    snapshot = {
        "price_analytics": {
            "sku_rows": [
                {"nm_id": "739377515", "seller_discounted_price": "2000.00"},
                {"nm_id": "453526507", "seller_discounted_price": "2000.00"},
                {"nm_id": "111111111", "seller_discounted_price": "1500.00"},
            ]
        }
    }
    detail = {
        "all_skus": [
            {"nm_id": "739377515", "buyouts_count": 1, "revenue": "999.97"},
            {"nm_id": "453526507", "buyouts_count": 1, "revenue": "900.00"},
        ]
    }

    price_section, changes_section = _build_product_price_sections(
        snapshot,
        sku_detail_section=detail,
    )

    assert [row["sku"] for row in price_section["sku_rows"]] == ["739377515", "453526507"]
    assert changes_section["rows"] == []
    assert changes_section["status"] == "unavailable"


def test_missing_financial_articles_show_preliminary_income_and_correct_share(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    config_dir = artifact_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "cogs.json").write_text(
        json.dumps({"values": {"739377515": "210", "453526507": "210"}}),
        encoding="utf-8",
    )
    snapshot = {
        "finance_final_daily": {
            "available": False,
            "expense_availability": {
                "commission": False,
                "logistics": False,
                "acquiring": False,
                "storage": False,
                "deductions": False,
                "tax": False,
            },
        },
        "live_operational": {
            "sales": {
                "rows": [
                    {"nm_id": "739377515", "quantity": 1, "amount": 999.97},
                    {"nm_id": "453526507", "quantity": 1, "amount": 900.00},
                ]
            },
            "orders": {"rows": []},
            "ads": {"rows": [], "ads_spend_total": 0},
        },
        "funnel_daily": {"sku_rows": []},
    }

    section = _build_sku_detail_section(snapshot, artifact_dir=artifact_dir)
    rows = {str(row["nm_id"]): row for row in section["all_skus"]}

    assert rows["739377515"]["share_pct"] == 52.63
    assert rows["739377515"]["profit"] is None
    assert rows["739377515"]["margin_pct"] is None
    assert rows["739377515"]["preliminary_income_before_wb_expenses"] == 789.97
    assert rows["453526507"]["preliminary_income_before_wb_expenses"] == 690.0


def test_daily_funnel_never_renders_order_to_buyout_without_cohort() -> None:
    section = build_funnel_section_v2(
        {
            "funnel_daily": {
                "available": True,
                "status": "ok",
                "source": "sales_funnel_api",
                "open_count": 234,
                "cart_count": 26,
                "orders_count": 2,
                "buyouts_count": 4,
                "open_to_cart_rate": 11.11,
                "cart_to_order_rate": 7.69,
                "order_to_buyout_rate": 200,
            },
            "live_operational": {"sales": {"available": False}},
        },
        {"available": True},
        None,
    )

    assert all("Заказ → Выкуп" not in str(row.get("stage")) for row in section["rows"])
    assert all("Конверсия заказ → выкуп" not in str(row.get("stage")) for row in section["rows"])


def test_zero_inefficient_queries_do_not_create_disable_action() -> None:
    section = _build_hero_section(
        {
            "seller_id": "seller_001",
            "operational_date": "2026-07-26",
            "finance_final_daily": {"available": False},
            "live_operational": {
                "ads": {"ads_spend_total": 158.56},
                "stocks": {"available": False},
                "sales": {"available": False},
            },
        },
        cabinet_commerce={
            "orders_count": 2,
            "orders_amount": None,
            "buyouts_count": 2,
            "buyouts_amount": None,
        },
        inefficient_query_count=0,
    )

    assert not any("Отключить" in action["text"] for action in section["actions"])
    amounts = {row["label"]: row["value"] for row in section["rows"]}
    assert amounts["Сумма заказов"] == "нет данных"
    assert amounts["Сумма выкупов"] == "нет данных"


def test_ads_only_sku_reason_is_not_low_margin() -> None:
    item = _normalize_abc_section_sku(
        {"sku": "898642228", "revenue": 0, "profit": -158.56},
        category="C",
        profit_by_sku={},
        ad_spend_by_sku={"898642228": 158.56},
        reason="низкая маржинальность",
        recommended_action="пересчитать цену",
    )

    assert item["reason"] == "рекламные расходы без атрибутированных заказов"


def test_abc_subtitle_describes_revenue_percentages(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "abc_analysis.json").write_text(
        json.dumps(
            {
                "basis": "buys",
                "items": [
                    {
                        "sku": "739377515",
                        "abc_class": "A",
                        "revenue": 999.97,
                        "profit": 100,
                        "share": 0.5263,
                    },
                    {
                        "sku": "453526507",
                        "abc_class": "C",
                        "revenue": 900,
                        "profit": 90,
                        "share": 0.4737,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    section = build_abc_section_v2({}, None, artifact_dir=artifact_dir)

    assert "проценты рассчитаны по выручке" in section["subtitle"]
