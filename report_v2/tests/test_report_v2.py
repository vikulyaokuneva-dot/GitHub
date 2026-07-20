from __future__ import annotations

import json
from pathlib import Path

from report_v2.builders.report_payload_builder import (
    build_abc_analysis_section_v2,
    build_ads_efficiency_section_v2,
    build_ads_section_v2,
    build_commerce_section_v2,
    build_diagnostics_v2,
    build_finance_section_v2,
    build_finance_alignment_notice_v2,
    build_funnel_section_v2,
    build_hero_v2,
    build_live_section_v2,
    build_profit_contribution_section_v2,
    build_report_payload_v2,
    build_sku_health_section_v2,
)
from report_v2.renderers.pdf_renderer_v2 import write_report_pdf_v2
from report_v2.run_report_v2 import build_report_v2_from_files
from wb_api_core.normalize import normalize_bundle
from wb_api_core.reconcile import reconcile_bundle
from wb_api_core.snapshot import build_snapshot


MOJIBAKE_MARKERS = (
    "\u0420\u0405\u0420\u00b5",
    "\u0420\u0491\u0420\u00b0",
    "\u0421\u2039",
    "\u0432\u201a\u0405",
)


def _assert_no_mojibake(text: str) -> None:
    assert not any(marker in text for marker in MOJIBAKE_MARKERS)


def _extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


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
            "gross_revenue": 554.0,
            "realized_sales_qty": 1.0,
            "realized_sales_revenue": 554.0,
            "seller_payout": 4868.22,
            "wb_commission": -329.75,
            "deliveries_qty": 3.0,
            "returns_qty": 2.0,
            "logistics": 166.40,
            "logistics_amount": 166.40,
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


def _rate_limited_commerce_snapshot() -> dict:
    snapshot = _sample_snapshot()
    snapshot["run_date"] = "2026-04-25"
    snapshot["operational_date"] = "2026-04-25"
    snapshot["cabinet_commerce_daily"] = {
        "source": "cabinet_commerce_daily",
        "available": False,
        "status": "unavailable",
        "target_date": "2026-04-25",
    }
    snapshot["finance_final_daily"].update(
        {
            "target_date": "2026-04-25",
            "actual_date": "2026-04-25",
            "date_aligned": True,
            "gross_revenue": 2680.0,
            "realized_sales_qty": 5.0,
            "realized_sales_revenue": 2680.0,
            "seller_payout": 2751.30,
            "returns_qty": 1.0,
            "deliveries_qty": 4.0,
            "logistics": 120.50,
            "logistics_amount": 120.50,
            "source": "finance_detailed_api",
        }
    )
    snapshot["live_operational"]["orders"].update(
        {
            "target_date": "2026-04-25",
            "available": True,
            "count": 8.0,
            "amount": 6657.60,
            "source": "orders_api",
        }
    )
    snapshot["live_operational"]["sales"].update(
        {
            "target_date": "2026-04-25",
            "available": True,
            "count": 5.0,
            "amount": 4020.20,
            "source": "sales_api",
        }
    )
    snapshot["live_operational"]["stocks"].update(
        {
            "available": True,
            "snapshot_date": "2026-04-25",
            "total_units": 337.0,
            "source": "stocks_api",
        }
    )
    return snapshot


def _rate_limited_debug() -> dict:
    debug = _sample_debug()
    debug["warnings"] = [
        {
            "code": "cabinet_commerce_rate_limited",
            "level": "warning",
            "block": "cabinet_commerce",
            "message": "429 too many requests from cabinet_commerce_daily.",
        }
    ]
    return debug


def _sample_ads_efficiency_artifact() -> dict:
    return {
        "seller_id": "seller_001",
        "report_date": "2026-04-21",
        "status": "ok",
        "analysis_mode": "full",
        "data_quality_status": "ok",
        "warnings": [],
        "summary": {
            "analysis_mode": "full",
            "portfolio_ad_spend": 1200.0,
            "portfolio_orders_from_ads": 10.0,
            "portfolio_buyouts_from_ads": 4.0,
            "portfolio_revenue_from_ads": 6000.0,
            "portfolio_profit_from_ads": 1800.0,
            "portfolio_ROMI": 150.0,
            "portfolio_DRR": 20.0,
            "portfolio_CPO": 120.0,
            "top_profitable_queries": [
                {
                    "query": "winner",
                    "ad_spend": 500.0,
                    "orders": 10.0,
                    "revenue": 6000.0,
                    "profit": 2500.0,
                    "ROMI": 500.0,
                    "classification": "profitable",
                }
            ],
            "top_unprofitable_queries": [
                {
                    "query": "leak",
                    "ad_spend": 700.0,
                    "orders": 0.0,
                    "revenue": 0.0,
                    "profit": -700.0,
                    "ROMI": -100.0,
                    "classification": "unprofitable",
                }
            ],
            "high_potential_queries": [
                {
                    "query": "scale-me",
                    "ad_spend": 100.0,
                    "orders": 2.0,
                    "revenue": 1000.0,
                    "profit": 600.0,
                    "ROMI": 600.0,
                    "classification": "profitable",
                }
            ],
        },
        "query_profitability": {
            "analysis_mode": "full",
            "status": "ok",
            "summary": {
                "query_count": 2,
                "profitable": 1,
                "neutral": 0,
                "unprofitable": 1,
                "insufficient_data": 0,
            },
            "items": [
                {
                    "query": "winner",
                    "impressions": 500,
                    "clicks": 50,
                    "ad_spend": 500.0,
                    "orders": 10.0,
                    "revenue": 6000.0,
                    "profit": 2500.0,
                    "ROMI": 500.0,
                    "classification": "profitable",
                    "confidence": "high",
                },
                {
                    "query": "leak",
                    "impressions": 1000,
                    "clicks": 100,
                    "ad_spend": 700.0,
                    "orders": 0.0,
                    "revenue": 0.0,
                    "profit": -700.0,
                    "ROMI": -100.0,
                    "classification": "unprofitable",
                    "confidence": "medium",
                },
            ],
        },
        "signals": [
            {
                "type": "ads_budget_leak",
                "recommendation": "Pause leak query and reallocate budget to profitable search traffic.",
            }
        ],
        "source": {"query_source": "advertising_efficiency.json"},
    }


def _sample_sku_health_artifacts() -> dict:
    return {
        "health_score": {
            "status": "ok",
            "warnings": ["funnel_insufficient_data"],
            "summary": {
                "status": "ok",
                "total_skus": 4,
                "sku_count": 4,
                "status_counts": {"risk": 1, "unstable": 1, "healthy": 1, "strong": 1},
                "average_health_score": 7.25,
                "LIQUIDATE": 1,
                "confidence": "medium",
                "reasons": ["partial funnel"],
            },
            "items": [
                {
                    "sku": "SKU-GROW",
                    "health_score": 8.8,
                    "health_status": "strong",
                    "status": "SCALE",
                    "reasons": ["growth"],
                    "actions": [{"title": "Scale SKU-GROW carefully"}],
                },
                {
                    "sku": "SKU-RISK",
                    "health_score": 2.1,
                    "health_status": "risk",
                    "status": "LIQUIDATE",
                    "warnings": ["dead_stock"],
                    "actions": [{"title": "Liquidate SKU-RISK stock"}],
                },
            ],
        },
        "sku_watchlists": {
            "date": "2026-04-21",
            "watchlists": {
                "top_growth": [
                    {
                        "sku": "SKU-GROW",
                        "attention_score": 12,
                        "reason": "Orders and revenue are growing",
                        "metrics": {"orders": 9, "stock": 12},
                    }
                ],
                "top_risk": [
                    {
                        "sku": "SKU-RISK",
                        "attention_score": 95,
                        "reason": "Low health score and stock pressure",
                        "metrics": {"stock": 50},
                    }
                ],
                "dead_stock": [
                    {
                        "sku": "SKU-RISK",
                        "attention_score": 95,
                        "reason": "Dead stock with no sales",
                        "metrics": {"stock": 50},
                    }
                ],
                "ad_inefficiency": [
                    {
                        "sku": "SKU-AD",
                        "attention_score": 70,
                        "reason": "Ads spend without confirmed orders",
                        "metrics": {"ads_spend": 300},
                    }
                ],
                "conversion_drop": [
                    {
                        "sku": "SKU-CONV",
                        "attention_score": 55,
                        "reason": "Conversion drop",
                        "metrics": {"orders": 1},
                    }
                ],
                "logistics_risk": [
                    {
                        "sku": "SKU-LOG",
                        "attention_score": 45,
                        "reason": "KTR risk",
                        "metrics": {"stock": 8},
                    }
                ],
            },
        },
        "sku_alerts": {
            "date": "2026-04-21",
            "items": [
                {
                    "sku": "SKU-RISK",
                    "attention_score": 95,
                    "alerts": [
                        {"type": "dead_stock", "status": "critical", "reason": "Stock exists without orders."}
                    ],
                },
                {
                    "sku": "SKU-AD",
                    "attention_score": 70,
                    "alerts": [
                        {
                            "type": "ad_inefficiency",
                            "status": "warning",
                            "reason": "Ads spend is inefficient.",
                        }
                    ],
                },
            ],
        },
        "sku_daily_dynamics": {
            "date": "2026-04-21",
            "sku_count": 4,
            "items": [
                {"sku": "SKU-GROW", "orders": 9, "stock": 12, "data_confidence": "medium"},
                {"sku": "SKU-RISK", "stock": 50, "data_confidence": "low"},
            ],
        },
    }


def _sample_profit_contribution_artifact() -> dict:
    return {
        "status": "ok",
        "warnings": [{"code": "profit_note", "message": "profit artifact warning"}],
        "summary": {
            "sku_count": 3,
            "loss_sku_count": 1,
            "total_profit": 800.0,
            "total_revenue": 5000.0,
            "top_sku_share": 0.875,
        },
        "items": [
            {"sku": "SKU-GROW", "name": "Growth item", "revenue": 3000.0, "profit": 700.0, "profit_share": 0.875, "status": "ok"},
            {"sku": "SKU-RISK", "name": "Risk item", "revenue": 1000.0, "profit": -100.0, "profit_share": -0.125, "status": "ok"},
            {"sku": "SKU-FLAT", "name": "Flat item", "revenue": 1000.0, "profit": 200.0, "profit_share": 0.25, "status": "ok"},
        ],
        "top_profit_skus": [
            {"sku": "SKU-GROW", "name": "Growth item", "revenue": 3000.0, "profit": 700.0, "profit_share": 0.875, "status": "ok"}
        ],
        "top_loss_sku": [
            {"sku": "SKU-RISK", "name": "Risk item", "revenue": 1000.0, "profit": -100.0, "profit_share": -0.125, "status": "ok"}
        ],
    }


def _sample_abc_analysis_artifact() -> list[dict]:
    return [
        {"sku": "SKU-GROW", "name": "Growth item", "profit": 700.0, "share": 0.70, "cumulative_share": 0.70, "abc_class": "A"},
        {"sku": "SKU-FLAT", "name": "Flat item", "profit": 200.0, "share": 0.20, "cumulative_share": 0.90, "abc_class": "B"},
        {"sku": "SKU-RISK", "name": "Risk item", "profit": -100.0, "share": -0.10, "cumulative_share": 0.80, "abc_class": "C"},
    ]


def test_build_report_payload_v2_maps_valid_snapshot() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    assert payload["meta"]["seller_id"] == "seller_001"
    assert payload["meta"]["report_date"] == "2026-04-21"
    assert payload["cabinet_commerce"]["orders_count"] == 5
    assert payload["cabinet_commerce"]["orders_amount"] == 4260.0
    assert payload["cabinet_commerce"]["buyouts_count"] == 2
    assert payload["cabinet_commerce"]["buyouts_amount"] == 1700.0
    assert payload["finance_final"]["seller_payout"] == 4868.22
    assert payload["finance_final"]["realized_sales_qty"] == 1.0
    assert payload["finance_final"]["realized_sales_revenue"] == 554.0
    assert payload["finance_final"]["returns_qty"] == 2.0
    assert payload["finance_final"]["deliveries_qty"] == 3.0
    assert payload["finance_final"]["logistics_amount"] == 166.40
    assert payload["finance_alignment_notice"]["state"] == "ok"
    assert payload["live_operational"]["stocks"]["total_units"] == 322
    assert payload["source_flags"]["buyouts_owner"] == "cabinet_commerce_daily"
    assert payload["diagnostics"]["warnings_count"] == len(payload["diagnostics"]["warnings"])
    assert any(item.get("code") == "buyouts_owner_from_cabinet_commerce" for item in payload["diagnostics"]["warnings"])
    assert payload["hero"]["title"] == "Ежедневный отчёт WB"
    assert len(payload["hero"]["cards"]) == 5
    assert payload["commerce_section"]["status"] == "ok"
    assert payload["funnel_section"]["status"] == "partial"
    assert payload["ads_section"]["status"] == "no_data"
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

    assert rows["Продажи/реализация"]["value"] == "1 шт"
    assert "554 ₽" in rows["Продажи/реализация"]["note"]
    assert rows["К перечислению продавцу"]["value"] == "4 868,22 ₽"
    assert rows["Возвраты"]["value"] == "2 шт"
    assert rows["Доставки"]["value"] == "3 шт"
    assert rows["Комиссия WB"]["value"] == "-329,75 ₽"
    assert rows["Логистика"]["value"] == "166,40 ₽"
    assert rows["Хранение"]["value"] == "68,37 ₽"
    assert rows["Эквайринг"]["value"] == "186,08 ₽"


def test_profit_table_uses_total_buyouts_for_every_calculation(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    snapshot["cabinet_commerce_daily"].update(
        {
            "buyouts_count": 4.0,
            "buyouts_amount": 4500.77,
        }
    )
    snapshot["finance_final_daily"].update(
        {
            "realized_sales_revenue": 2714.24,
            "gross_revenue": 2714.24,
            "wb_commission": -353.48,
            "logistics": 1809.0,
            "logistics_amount": 1809.0,
            "rebill_logistic_cost": 219.40,
            "storage": 24.55,
            "acquiring": 108.57,
            "deductions": 3005.0,
            "penalties": 0.0,
            "tax": 0.0,
            "returns_qty": 3.0,
        }
    )
    snapshot["live_operational"]["sales"].update(
        {
            "count": 4.0,
            "amount": 4500.77,
            "rows": [
                {"nm_id": "333615320", "quantity": 1.0, "amount": 1500.77},
                {"nm_id": "898642228", "quantity": 1.0, "amount": 2300.0},
                {"nm_id": "453526507", "quantity": 2.0, "amount": 700.0},
            ],
        }
    )
    snapshot["live_operational"]["ads"] = {
        "available": True,
        "ads_spend_total": 298.77,
    }

    artifact_dir = tmp_path / "cabinets" / "seller_001" / "artifacts" / "wb_api_core" / "2026-07-12"
    config_dir = tmp_path / "cabinets" / "seller_001" / "config"
    artifact_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    (config_dir / "cogs.json").write_text(
        json.dumps(
            {
                "values": {
                    "333615320": "210",
                    "898642228": "600",
                    "453526507": "210",
                }
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "abc_analysis.json").write_text(
        json.dumps(
            [
                {"sku": "333615320", "revenue": 1500.77, "profit": 400.0, "abc_class": "A"},
                {"sku": "898642228", "revenue": 2300.0, "profit": 300.0, "abc_class": "B"},
            ]
        ),
        encoding="utf-8",
    )

    payload = build_report_payload_v2(snapshot, debug=_sample_debug(), artifact_dir=artifact_dir)
    profit_rows = {row["label"]: row["value"] for row in payload["profit_section"]["rows"]}
    hero_rows = {row["label"]: row["value"] for row in payload["hero_section"]["rows"]}

    assert profit_rows["Выручка от выкупов"] == "4 500,77 ₽"
    assert profit_rows["Комиссия WB"] == "-353,48 ₽"
    assert profit_rows["Логистика"] == "-1 809 ₽"
    assert profit_rows["Ребиллинг логистики"] == "-219,40 ₽"
    assert profit_rows["Хранение"] == "-24,55 ₽"
    assert profit_rows["Эквайринг"] == "-108,57 ₽"
    assert profit_rows["Удержания"] == "-3 005 ₽"
    assert profit_rows["Возвраты (шт)"] == "3 шт"
    assert profit_rows["Себестоимость товаров"] == "-1 230 ₽"
    assert profit_rows["Реклама"] == "-298,77 ₽"
    assert profit_rows["Итого затраты"] == "-7 048,77 ₽"
    assert profit_rows["Чистая прибыль"] == "-2 548 ₽"
    assert profit_rows["Маржа"] == "-56.6%"
    assert hero_rows["Сумма выкупов"] == "4 500,77 ₽"
    assert hero_rows["Прибыль"] == "-2 548 ₽"
    assert payload["profit_section"]["revenue_basis"] == "buyouts_amount"


def test_wb_reference_kpis_split_funnel_orders_from_finance_realization() -> None:
    raw_bundle = {
        "cabinet_commerce": {
            "rows_raw": [
                {
                    "product": {"nmId": 101, "vendorCode": "SKU-101"},
                    "statistic": {
                        "selected": {
                            "period": {"start": "2026-04-29", "end": "2026-04-29"},
                            "openCount": 370,
                            "cartCount": 44,
                            "orderCount": 2,
                            "orderSum": 1760.0,
                            "buyoutCount": 0,
                            "buyoutSum": 0.0,
                        }
                    },
                }
            ],
            "debug": {"success": True},
        },
        "finance_final": {
            "rows_raw": [
                {
                    "rrDate": "2026-04-29",
                    "saleDt": "2026-04-29T10:00:00Z",
                    "quantity": 1,
                    "retailAmount": 554.0,
                    "ppvzForPay": 593.36,
                    "ppvzSalesCommission": -54.43,
                    "acquiringFee": 27.04,
                    "paidStorage": 68.96,
                    "deliveryAmount": 3,
                    "deliveryRub": 166.40,
                    "docTypeName": "Продажа",
                },
                {
                    "rrDate": "2026-04-29",
                    "saleDt": "2026-04-29T12:00:00Z",
                    "quantity": 2,
                    "docTypeName": "Возврат",
                },
            ],
            "debug": {"success": True},
        },
        "orders": {"rows_raw": [], "debug": {"success": False}},
        "sales": {"rows_raw": [], "debug": {"success": False}},
        "stocks": {"rows_raw": [], "debug": {"success": False}},
    }

    normalized = normalize_bundle(raw_bundle)
    reconciled = reconcile_bundle(raw_bundle=raw_bundle, normalized_bundle=normalized, target_date="2026-04-29")
    snapshot = build_snapshot(
        seller_id="seller_001",
        run_date="2026-04-30",
        operational_date="2026-04-29",
        timezone_name="Europe/Moscow",
        reconcile_result=reconciled,
    )
    payload = build_report_payload_v2(snapshot, debug={"warnings": []})
    cards = {item["label"]: item for item in payload["hero"]["cards"]}
    finance_rows = {item["label"]: item for item in payload["finance_section"]["rows"]}

    assert cards["Заказы"]["value"] == "2 шт"
    assert cards["Заказы"]["subvalue"] == "1 760 ₽"
    assert cards["Продажи/реализация"]["value"] == "1 шт"
    assert cards["Продажи/реализация"]["subvalue"] == "554 ₽"
    assert cards["К перечислению"]["value"] == "593,36 ₽"
    assert cards["Возвраты"]["value"] == "2 шт"
    assert cards["Возвраты"]["subvalue"] == "Доставки: 3 шт"
    assert "Выкупы" not in cards
    assert payload["finance_final"]["deliveries_qty"] == 3.0
    assert payload["finance_final"]["logistics_amount"] == 166.40
    assert payload["finance_final"]["logistics_amount"] != payload["finance_final"]["deliveries_qty"]
    assert finance_rows["Логистика"]["value"] == "166,40 ₽"
    assert finance_rows["Доставки"]["value"] == "3 шт"


def test_funnel_section_v2_uses_cabinet_commerce_lower_funnel() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["stage"]: item for item in payload["funnel_section"]["rows"]}

    assert payload["funnel_section"]["status"] == "partial"
    assert rows["Заказы"]["value"] == "5 шт"
    assert rows["Заказы"]["source"] == "sales_funnel_api"
    assert rows["Выкупы"]["value"] == "2 шт"
    assert rows["Выкупы"]["source"] == "sales_funnel_api"


def test_report_payload_v2_uses_funnel_daily_when_present() -> None:
    snapshot = _sample_snapshot()
    snapshot["funnel_daily"] = {
        "source": "sales_funnel_api",
        "available": True,
        "status": "ok",
        "open_count": 423,
        "cart_count": 42,
        "orders_count": 5,
        "buyouts_count": 2,
        "open_to_cart_rate": 9.93,
        "cart_to_order_rate": 11.9,
        "order_to_buyout_rate": 40.0,
    }

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    rows = {item["stage"]: item for item in payload["funnel_section"]["rows"]}

    assert payload["funnel_section"]["status"] == "ok"
    assert payload["funnel_section"]["message"] == "Воронка собрана из sales_funnel_api."
    assert rows["Открытия карточек"]["value"] == "423 шт"
    assert rows["Открытия карточек"]["source"] == "sales_funnel_api"
    assert rows["Корзина"]["value"] == "42 шт"
    assert rows["Открытие → корзина"]["value"] == "9.93%"
    assert rows["Корзина → заказ"]["value"] == "11.9%"
    assert rows["Заказ → выкуп"]["value"] == "40%"
    assert "Клики" not in rows


def test_funnel_section_v2_uses_funnel_daily_partial_message() -> None:
    snapshot = _sample_snapshot()
    snapshot["funnel_daily"] = {
        "source": "sales_funnel_api",
        "available": True,
        "status": "partial",
        "open_count": 423,
    }

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())

    assert payload["funnel_section"]["status"] == "partial"
    assert payload["funnel_section"]["message"] == "Воронка частично доступна из sales_funnel_api."


def test_funnel_section_v2_does_not_fake_missing_upper_funnel_zeroes() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    rows = {item["stage"]: item for item in payload["funnel_section"]["rows"]}

    for stage in ("Показы", "Клики", "Корзина"):
        assert rows[stage]["value"] == "нет данных"
        assert rows[stage]["status"] == "unavailable"
        assert rows[stage]["value"] != "0 шт"


def test_funnel_section_v2_computes_order_to_buyout_conversion_in_builder() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    rows = {item["stage"]: item for item in payload["funnel_section"]["rows"]}

    assert rows["Конверсия заказ → выкуп"]["value"] == "40%"
    assert rows["Конверсия заказ → выкуп"]["status"] == "ok"
    assert "builder" in rows["Конверсия заказ → выкуп"]["note"]


def test_funnel_section_v2_unavailable_without_orders_and_buyouts() -> None:
    funnel = build_funnel_section_v2({}, {"available": False}, debug=None)

    rows = {item["stage"]: item for item in funnel["rows"]}

    assert funnel["status"] == "unavailable"
    assert rows["Заказы"]["value"] == "нет данных"
    assert rows["Выкупы"]["value"] == "нет данных"
    assert rows["Конверсия заказ → выкуп"]["value"] == "нет данных"


def test_report_payload_v2_fills_orders_from_live_operational_when_cabinet_commerce_rate_limited() -> None:
    payload = build_report_payload_v2(_rate_limited_commerce_snapshot(), debug=_rate_limited_debug())

    warning_codes = {item.get("code") for item in payload["warnings"]}
    diagnostic_codes = {item.get("code") for item in payload["diagnostics"]["warnings"]}
    orders_card = payload["hero"]["cards"][0]
    sales_card = payload["hero"]["cards"][1]
    commerce_rows = {item["label"]: item for item in payload["commerce_section"]["rows"]}

    assert payload["cabinet_commerce"]["available"] is False
    assert payload["cabinet_commerce"]["status"] == "unavailable"
    assert payload["cabinet_commerce"]["orders_count"] == 8
    assert payload["cabinet_commerce"]["orders_amount"] == 6657.60
    assert payload["cabinet_commerce"]["orders_source"] == "orders_api"
    assert payload["cabinet_commerce"]["orders_fallback"] is True
    assert orders_card["value"] == "8 шт"
    assert "6 657,60" in orders_card["subvalue"]
    assert "orders_api" in orders_card["subvalue"]
    assert orders_card["status"] != "unavailable"
    assert sales_card["value"] == "5 шт"
    assert "2 680" in sales_card["subvalue"]
    assert sales_card["label"] == "Продажи/реализация"
    assert payload["commerce_section"]["status"] == "partial"
    assert commerce_rows["Заказы"]["value"] == "8 шт"
    assert "live_operational.orders" in commerce_rows["Заказы"]["note"]
    assert "cabinet_commerce_rate_limited" in warning_codes
    assert "commerce_filled_from_live_operational" in warning_codes
    assert "cabinet_commerce_rate_limited" in diagnostic_codes
    assert "commerce_filled_from_live_operational" in diagnostic_codes


def test_report_payload_v2_does_not_label_sales_api_as_confirmed_buyouts() -> None:
    payload = build_report_payload_v2(_rate_limited_commerce_snapshot(), debug=_rate_limited_debug())

    commerce_rows = {item["label"]: item for item in payload["commerce_section"]["rows"]}
    funnel_rows = {item["stage"]: item for item in payload["funnel_section"]["rows"]}
    warning_codes = {item.get("code") for item in payload["warnings"]}

    assert payload["cabinet_commerce"]["buyouts_count"] is None
    assert payload["cabinet_commerce"]["buyouts_amount"] is None
    assert payload["cabinet_commerce"]["sales_count"] == 5
    assert payload["cabinet_commerce"]["sales_amount"] == 4020.20
    assert payload["cabinet_commerce"]["sales_source"] == "sales_api"
    assert payload["hero"]["cards"][1]["label"] == "Продажи/реализация"
    assert "Выкупы" not in {card["label"] for card in payload["hero"]["cards"]}
    assert "Оперативные продажи" in commerce_rows
    assert commerce_rows["Оперативные продажи"]["value"] == "5 шт"
    assert "live_operational.sales" in commerce_rows["Оперативные продажи"]["note"]
    assert "confirmed buyouts" in commerce_rows["Сумма оперативных продаж"]["note"]
    assert "Оперативные продажи" in funnel_rows
    assert "Выкупы" not in funnel_rows
    assert funnel_rows["Конверсия заказ → выкуп"]["status"] == "unavailable"
    assert "operational_sales_not_confirmed_buyouts" in warning_codes


def test_report_payload_v2_keeps_no_data_when_no_cabinet_and_no_live_operational() -> None:
    snapshot = _rate_limited_commerce_snapshot()
    snapshot["live_operational"]["orders"] = {"source": "orders_api", "available": False}
    snapshot["live_operational"]["sales"] = {"source": "sales_api", "available": False}

    payload = build_report_payload_v2(snapshot, debug=_rate_limited_debug())
    warning_codes = {item.get("code") for item in payload["warnings"]}

    assert payload["cabinet_commerce"]["orders_count"] is None
    assert payload["cabinet_commerce"]["orders_amount"] is None
    assert payload["cabinet_commerce"]["sales_count"] is None
    assert payload["cabinet_commerce"]["sales_amount"] is None
    assert payload["hero"]["cards"][0]["status"] == "unavailable"
    assert payload["hero"]["cards"][1]["status"] == "ok"
    assert payload["commerce_section"]["status"] == "unavailable"
    assert "commerce_filled_from_live_operational" not in warning_codes
    assert "cabinet_commerce_unavailable" in warning_codes


def test_report_payload_v2_preserves_finance_when_commerce_unavailable() -> None:
    payload = build_report_payload_v2(_rate_limited_commerce_snapshot(), debug=_rate_limited_debug())

    finance_rows = {item["label"]: item for item in payload["finance_section"]["rows"]}
    finance_card = payload["hero"]["cards"][2]

    assert payload["finance_final"]["available"] is True
    assert payload["finance_final"]["status"] == "ok"
    assert payload["finance_final"]["date_aligned"] is True
    assert payload["finance_final"]["seller_payout"] == 2751.30
    assert payload["finance_final"]["gross_revenue"] == 2680.0
    assert payload["finance_section"]["status"] == "ok"
    assert finance_card["value"] == "2 751,30 ₽"
    assert finance_card["subvalue"] == "finance_detailed_api"
    assert finance_rows["К перечислению продавцу"]["value"] == "2 751,30 ₽"


def test_ads_section_renders_no_data_when_artifacts_missing() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["label"]: item for item in payload["ads_section"]["rows"]}

    assert payload["ads_section"]["title"] == "Реклама"
    assert payload["ads_section"]["status"] == "no_data"
    assert payload["ads_efficiency_section"]["status"] == "no_data"
    assert payload["ads_section"]["message"] == "Данные advertising_efficiency отсутствуют в snapshot и artifacts."
    assert rows["Расход на рекламу"]["value"] == "нет данных"
    assert rows["Показы"]["value"] == "нет данных"
    assert rows["Клики"]["value"] == "нет данных"
    assert rows["Заказы из рекламы"]["value"] == "нет данных"
    assert rows["Выручка из рекламы"]["value"] == "нет данных"
    assert rows["ДРР"]["value"] == "нет данных"


def test_ads_section_v2_missing_values_do_not_become_zero() -> None:
    snapshot = {
        "advertising_efficiency": {
            "status": "ok",
            "analysis_mode": "full",
            "summary": {"portfolio_ad_spend": 1200.0},
        }
    }

    ads = build_ads_section_v2(snapshot, debug=None)
    rows = {item["label"]: item for item in ads["rows"]}

    assert ads["status"] == "partial"
    assert rows["Расход на рекламу"]["value"] == "1 200 ₽"
    assert rows["Выручка из рекламы"]["value"] == "нет данных"
    assert rows["Выручка из рекламы"]["value"] != "0 ₽"
    assert rows["ДРР"]["value"] == "нет данных"
    assert rows["Заказы из рекламы"]["value"] != "0 шт"


def test_ads_section_uses_advertising_efficiency_artifact_when_present() -> None:
    snapshot = {"advertising_efficiency": _sample_ads_efficiency_artifact()}

    ads_efficiency = build_ads_efficiency_section_v2(snapshot, debug=None)
    ads = build_ads_section_v2(snapshot, debug=None, ads_efficiency_section=ads_efficiency)
    rows = {item["label"]: item for item in ads["rows"]}

    assert ads["status"] == "ok"
    assert ads_efficiency["source"] == "advertising_efficiency.json"
    assert ads_efficiency["spend"] == 1200.0
    assert ads_efficiency["impressions"] == 1500
    assert ads_efficiency["clicks"] == 150
    assert ads_efficiency["ctr"] == 10.0
    assert ads_efficiency["cpc"] == 8.0
    assert ads_efficiency["cpm"] == 800.0
    assert ads_efficiency["ad_orders"] == 10.0
    assert ads_efficiency["ad_revenue"] == 6000.0
    assert ads_efficiency["ad_buyouts"] == 4.0
    assert ads_efficiency["drr"] == 20.0
    assert ads_efficiency["roas"] == 5.0
    assert ads_efficiency["romi"] == 150.0
    assert ads_efficiency["cpo"] == 120.0
    assert ads_efficiency["profit_from_ads"] == 1800.0
    assert ads_efficiency["wasted_spend"] == 700.0
    assert ads_efficiency["inefficient_items_count"] == 1
    assert ads_efficiency["top_unprofitable_queries"][0]["query"] == "leak"
    assert ads_efficiency["top_profitable_queries"][0]["query"] == "winner"
    assert ads_efficiency["high_potential_queries"][0]["query"] == "scale-me"
    assert rows["Расход на рекламу"]["value"] == "1 200 ₽"
    assert rows["Расход на рекламу"]["source"] == "advertising_efficiency.json"
    assert rows["Показы"]["value"] == "1 500 шт"
    assert rows["Клики"]["value"] == "150 шт"
    assert rows["CTR"]["value"] == "10%"
    assert rows["CPC"]["value"] == "8 ₽"
    assert rows["CPM"]["value"] == "800 ₽"
    assert rows["Заказы из рекламы"]["value"] == "10"
    assert rows["Выручка из рекламы"]["value"] == "6 000 ₽"
    assert rows["ДРР"]["value"] == "20%"
    assert rows["ROAS"]["value"] == "5,00x"
    assert rows["ROMI"]["value"] == "150%"
    assert rows["Потери рекламы"]["value"] == "700 ₽"


def test_ads_section_v2_maps_ads_efficiency_daily_values() -> None:
    snapshot = {
        "ads_efficiency_daily": {
            "source": "ads_efficiency_api",
            "ads_spend": 1200.0,
            "orders_from_ads": 4,
            "revenue_from_ads": 6000.0,
        }
    }

    ads = build_ads_section_v2(snapshot, debug=None)
    rows = {item["label"]: item for item in ads["rows"]}

    assert ads["status"] == "ok"
    assert rows["Расход на рекламу"]["value"] == "1 200 ₽"
    assert rows["Расход на рекламу"]["source"] == "ads_efficiency_api"
    assert rows["Заказы из рекламы"]["value"] == "4"
    assert rows["Выручка из рекламы"]["value"] == "6 000 ₽"
    assert rows["ДРР"]["value"] == "20%"
    assert rows["ROAS"]["value"] == "5,00x"


def test_ads_section_v2_partial_data_produces_partial_status() -> None:
    snapshot = {"advertising_efficiency": {"status": "ok", "analysis_mode": "full", "summary": {"portfolio_ad_spend": 1200.0}}}

    ads = build_ads_section_v2(snapshot, debug=None)
    rows = {item["label"]: item for item in ads["rows"]}

    assert ads["status"] == "partial"
    assert rows["Расход на рекламу"]["value"] == "1 200 ₽"
    assert rows["ДРР"]["value"] == "нет данных"
    assert rows["ДРР"]["status"] == "unavailable"


def test_sku_health_section_is_no_data_when_artifacts_missing() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    section = payload["sku_health_section"]
    rows = {item["label"]: item for item in section["summary_rows"]}

    assert section["status"] == "no_data"
    assert section["summary"]["total_skus"] is None
    assert rows["Всего SKU"]["value"] == "нет данных"
    assert rows["Всего SKU"]["value"] != "0 шт"


def test_sku_health_section_is_partial_when_only_sku_watchlists_exists() -> None:
    artifacts = _sample_sku_health_artifacts()
    snapshot = {"sku_watchlists": artifacts["sku_watchlists"]}

    section = build_sku_health_section_v2(snapshot, debug=None)

    assert section["status"] == "partial"
    assert section["source"] == "sku_watchlists.json"
    assert section["summary"]["growth_count"] == 1
    assert section["summary"]["risk_count"] == 1
    assert section["summary"]["total_skus"] is None
    assert section["watchlists"]["top_growth"][0]["sku"] == "SKU-GROW"
    assert section["watchlists"]["top_growth"][0]["reason"] == "Orders and revenue are growing"


def test_sku_health_section_is_ok_when_health_score_watchlists_and_alerts_exist() -> None:
    artifacts = _sample_sku_health_artifacts()
    snapshot = {
        "health_score": artifacts["health_score"],
        "sku_watchlists": artifacts["sku_watchlists"],
        "sku_alerts": artifacts["sku_alerts"],
        "sku_daily_dynamics": artifacts["sku_daily_dynamics"],
    }

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    section = payload["sku_health_section"]
    warning_codes = {item.get("code") for item in payload["warnings"]}
    diagnostic_codes = {item.get("code") for item in payload["diagnostics"]["warnings"]}

    assert section["status"] == "ok"
    assert section["summary"]["total_skus"] == 4
    assert section["summary"]["healthy_count"] == 2
    assert section["summary"]["growth_count"] == 1
    assert section["summary"]["risk_count"] == 1
    assert section["summary"]["dead_stock_count"] == 1
    assert section["summary"]["ad_inefficiency_count"] == 1
    assert section["summary"]["conversion_drop_count"] == 1
    assert section["summary"]["logistics_risk_count"] == 1
    assert section["health_score"]["value"] == 7.25
    assert section["risk_rows"][0]["sku"] == "SKU-RISK"
    assert section["growth_rows"][0]["sku"] == "SKU-GROW"
    assert "sku_health_warning" in warning_codes
    assert "sku_health_warning" in diagnostic_codes


def test_sku_health_missing_numeric_values_are_not_converted_to_zero() -> None:
    snapshot = {
        "sku_watchlists": {
            "watchlists": {
                "top_risk": [
                    {"sku": "SKU-MISSING", "reason": "Metrics are missing"}
                ]
            }
        }
    }

    section = build_sku_health_section_v2(snapshot, debug=None)
    item = section["watchlists"]["top_risk"][0]

    assert section["status"] == "partial"
    assert item["sku"] == "SKU-MISSING"
    assert item["attention_score"] is None
    assert item["metric_value"] is None
    assert item["metric_value"] != 0


def test_sku_health_watchlists_preserve_sku_ids_and_reasons() -> None:
    artifacts = _sample_sku_health_artifacts()
    section = build_sku_health_section_v2({"sku_watchlists": artifacts["sku_watchlists"]}, debug=None)

    assert section["watchlists"]["dead_stock"][0]["sku"] == "SKU-RISK"
    assert section["watchlists"]["dead_stock"][0]["reason"] == "Dead stock with no sales"
    assert section["watchlists"]["ad_inefficiency"][0]["sku"] == "SKU-AD"
    assert section["watchlists"]["conversion_drop"][0]["reason"] == "Conversion drop"


def test_live_section_v2_contains_display_rows() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    rows = {item["label"]: item for item in payload["live_section"]["rows"]}

    assert rows["Оперативные заказы"]["value"] == "3 шт"
    assert rows["Оперативные продажи"]["value"] == "3 шт"
    assert rows["Оперативные остатки"]["value"] == "322 шт"
    assert "live snapshot stocks_api" in rows["Оперативные остатки"]["note"]
    assert "товарного отчёта WB" in rows["Оперативные остатки"]["note"]
    assert rows["Дата среза оперативных остатков"]["value"] == "2026-04-22"


def test_stock_section_does_not_substitute_live_stocks_as_goods_stock() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    stock_section = payload["stock_section"]

    assert stock_section["status"] == "no_data"
    assert stock_section["stock_wb_qty"] is None
    assert stock_section["stock_mp_qty"] is None
    assert stock_section["stock_total_qty"] is None
    assert stock_section["stock_value"] is None
    assert stock_section["sku_rows_count"] is None
    assert payload["live_operational"]["stocks"]["total_units"] == 322

    warning_codes = {item.get("code") for item in payload["diagnostics"]["warnings"]}
    assert "operational_stock_differs_from_goods_stock" in warning_codes


def test_stock_section_uses_separate_goods_stock_fields_when_available() -> None:
    snapshot = _sample_snapshot()
    snapshot["stock_section"] = {
        "source": "supplier_goods",
        "stock_wb_qty": 465,
        "stock_mp_qty": 259,
        "stock_value": 1079217.0,
        "sku_rows_count": 27,
    }

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())

    stock_section = payload["stock_section"]
    assert stock_section["status"] == "ok"
    assert stock_section["source"] == "supplier_goods"
    assert stock_section["stock_wb_qty"] == 465
    assert stock_section["stock_mp_qty"] == 259
    assert stock_section["stock_total_qty"] == 724
    assert stock_section["stock_value"] == 1079217.0
    assert stock_section["sku_rows_count"] == 27


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
    assert cards["Продажи/реализация"]["value"] == "1 шт"
    assert cards["Продажи/реализация"]["subvalue"] == "554 ₽"
    assert cards["К перечислению"]["value"] == "4 868,22 ₽"
    assert cards["Возвраты"]["value"] == "2 шт"
    assert cards["Возвраты"]["subvalue"] == "Доставки: 3 шт"
    assert cards["Оперативные остатки"]["value"] == "322 шт"
    assert "дата среза 2026-04-22" in cards["Оперативные остатки"]["subvalue"]
    assert "2026-04-21" not in cards["Оперативные остатки"]["subvalue"]
    assert "Выкупы" not in cards


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
        finance_final={
            "available": True,
            "status": "ok",
            "realized_sales_qty": 1,
            "realized_sales_revenue": 554,
            "seller_payout": 4868.22,
            "returns_qty": 2,
            "deliveries_qty": 3,
            "source": "finance_detailed_api",
        },
        live_operational={"stocks": {"available": True, "total_units": 322, "snapshot_date": "2026-04-22"}},
        warnings=[],
    )

    assert hero["subtitle"] == "Кабинет: seller_001 | Дата: 2026-04-21"
    assert hero["data_status"] == "ok"
    assert len(hero["cards"]) == 5


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
    assert info["hero_rows_count"] == 6
    assert info["top_skus_count"] >= 0



def test_write_report_pdf_v2_creates_pdf_with_display_sections(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_sections.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_rows_count"] >= 0


def test_write_report_pdf_v2_creates_pdf_with_funnel_minimal(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_funnel.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["funnel_section"]["title"] == "Воронка продаж"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_write_report_pdf_v2_creates_pdf_with_ads_minimal(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_ads.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["ads_section"]["title"] == "Реклама"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_rows_count"] >= 0


def test_pdf_contains_ads_spend_drr_roas_when_data_exists(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    snapshot["advertising_efficiency"] = _sample_ads_efficiency_artifact()
    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_ads_efficiency.pdf"

    info = write_report_pdf_v2(pdf_path, payload)
    rows = {item["label"]: item for item in payload["ads_section"]["rows"]}

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["ads_section_status"] == "ok"
    assert info["ads_efficiency_section_status"] == "ok"
    assert info["ads_efficiency_loss_rows_count"] == 1
    assert rows["Расход на рекламу"]["value"] == "1 200 ₽"
    assert rows["ДРР"]["value"] == "20%"
    assert rows["ROAS"]["value"] == "5,00x"


def test_pdf_renders_top_risk_and_top_growth_sku(tmp_path: Path) -> None:
    artifacts = _sample_sku_health_artifacts()
    snapshot = _sample_snapshot()
    snapshot.update(
        {
            "health_score": artifacts["health_score"],
            "sku_watchlists": artifacts["sku_watchlists"],
            "sku_alerts": artifacts["sku_alerts"],
            "sku_daily_dynamics": artifacts["sku_daily_dynamics"],
        }
    )
    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_sku_health.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert payload["sku_health_section"]["risk_rows"][0]["sku"] == "SKU-RISK"
    assert payload["sku_health_section"]["growth_rows"][0]["sku"] == "SKU-GROW"


def test_pdf_renderer_accepts_payload_without_sku_health_section(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    payload.pop("sku_health_section")
    pdf_path = tmp_path / "report_v2_without_sku_health.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["sku_health_section_status"] == "нет данных"
    assert info["sku_health_summary_rows_count"] == 0


def test_write_report_pdf_v2_creates_pdf_with_hero_block(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_hero.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert payload["hero"]["cards"][0]["label"] == "Заказы"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_rows_count"] == 6


def test_pdf_renderer_visual_polish_removes_technical_hero_text() -> None:
    renderer_source = (Path(__file__).resolve().parents[1] / "renderers" / "pdf_renderer_v2.py").read_text(encoding="utf-8")

    assert "status:" not in renderer_source
    assert "data_status:" not in renderer_source
    assert "snapshot_source_mode:" not in renderer_source


def test_write_report_pdf_v2_creates_pdf_with_diagnostics_section(tmp_path: Path) -> None:
    debug = {"warnings": [{"code": "debug_pdf_warning", "message": "Debug PDF warning.", "block": "debug"}]}
    payload = build_report_payload_v2(_sample_snapshot(), debug=debug)
    pdf_path = tmp_path / "report_v2_diagnostics.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert any(item.get("code") == "debug_pdf_warning" for item in payload["diagnostics"]["warnings"])
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_pdf_renderer_keeps_diagnostics_on_second_page() -> None:
    renderer_source = (Path(__file__).resolve().parents[1] / "renderers" / "pdf_renderer_v2.py").read_text(encoding="utf-8")

    assert "PageBreak" in renderer_source


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


def test_pdf_renderer_accepts_missing_new_finance_kpi_fields(tmp_path: Path) -> None:
    snapshot = _sample_snapshot()
    for key in ("realized_sales_qty", "realized_sales_revenue", "returns_qty", "deliveries_qty", "logistics_amount"):
        snapshot["finance_final_daily"].pop(key, None)

    payload = build_report_payload_v2(snapshot, debug=_sample_debug())
    pdf_path = tmp_path / "report_v2_missing_new_finance_fields.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert payload["finance_section"]["rows"][1]["status"] != "error"


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


def test_build_report_v2_from_files_reads_advertising_artifact_from_artifacts_root(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "cabinets" / "seller_001" / "artifacts"
    snapshot_dir = artifacts_dir / "wb_api_core" / "2026-04-21"
    snapshot_dir.mkdir(parents=True)
    snapshot_path = snapshot_dir / "snapshot.json"
    debug_path = snapshot_dir / "debug.json"
    snapshot_path.write_text(json.dumps(_sample_snapshot(), ensure_ascii=False), encoding="utf-8")
    debug_path.write_text(json.dumps(_sample_debug(), ensure_ascii=False), encoding="utf-8")
    (artifacts_dir / "advertising_efficiency.json").write_text(
        json.dumps(_sample_ads_efficiency_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )

    result = build_report_v2_from_files(snapshot_path=snapshot_path, debug_path=debug_path, out_dir=tmp_path / "out")
    payload = result["payload"]

    assert payload["ads_efficiency_section"]["status"] == "ok"
    assert payload["ads_efficiency_section"]["source"] == "advertising_efficiency.json"
    assert payload["ads_efficiency_section"]["spend"] == 1200.0
    assert payload["ads_section"]["status"] == "ok"


def test_build_report_v2_from_files_reads_sku_artifacts_from_artifacts_root(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "cabinets" / "seller_001" / "artifacts"
    snapshot_dir = artifacts_dir / "wb_api_core" / "2026-04-21"
    snapshot_dir.mkdir(parents=True)
    snapshot_path = snapshot_dir / "snapshot.json"
    debug_path = snapshot_dir / "debug.json"
    snapshot_path.write_text(json.dumps(_sample_snapshot(), ensure_ascii=False), encoding="utf-8")
    debug_path.write_text(json.dumps(_sample_debug(), ensure_ascii=False), encoding="utf-8")
    sku_artifacts = _sample_sku_health_artifacts()
    for name, payload in (
        ("health_score.json", sku_artifacts["health_score"]),
        ("sku_watchlists.json", sku_artifacts["sku_watchlists"]),
        ("sku_alerts.json", sku_artifacts["sku_alerts"]),
        ("sku_daily_dynamics.json", sku_artifacts["sku_daily_dynamics"]),
    ):
        (artifacts_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = build_report_v2_from_files(snapshot_path=snapshot_path, debug_path=debug_path, out_dir=tmp_path / "out")
    payload = result["payload"]

    assert payload["sku_health_section"]["status"] == "ok"
    assert payload["sku_health_section"]["source"] == (
        "health_score.json, sku_watchlists.json, sku_alerts.json, sku_daily_dynamics.json"
    )
    assert payload["sku_health_section"]["risk_rows"][0]["sku"] == "SKU-RISK"


def test_profit_contribution_section_is_no_data_when_artifact_missing(tmp_path: Path) -> None:
    section = build_profit_contribution_section_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)

    assert section["status"] == "no_data"
    assert section["source"] == "missing"
    assert section["summary"]["total_profit"] is None
    assert section["top_profit_skus"] == []


def test_abc_analysis_section_is_no_data_when_artifact_missing(tmp_path: Path) -> None:
    section = build_abc_analysis_section_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)

    assert section["status"] == "no_data"
    assert section["source"] == "missing"
    assert section["summary"]["total_skus"] is None
    assert section["categories"] == {"A": [], "B": [], "C": []}


def test_profit_contribution_section_is_ok_when_artifact_exists(tmp_path: Path) -> None:
    (tmp_path / "profit_contribution.json").write_text(
        json.dumps(_sample_profit_contribution_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )
    sku_health_section = build_sku_health_section_v2(
        {**_sample_snapshot(), **_sample_sku_health_artifacts()},
        debug=_sample_debug(),
    )

    section = build_profit_contribution_section_v2(
        _sample_snapshot(),
        debug=_sample_debug(),
        artifact_dir=tmp_path,
        sku_health_section=sku_health_section,
    )

    assert section["status"] == "ok"
    assert section["source"] == "profit_contribution.json"
    assert section["summary"]["total_profit"] == 800.0
    assert section["summary"]["total_revenue"] == 5000.0
    assert section["summary"]["top_sku_share"] == 0.875
    assert section["top_profit_skus"][0]["sku"] == "SKU-GROW"
    assert section["loss_skus"][0]["sku"] == "SKU-RISK"
    assert section["loss_skus"][0]["recommended_action"] == "Liquidate SKU-RISK stock"


def test_profit_contribution_total_revenue_falls_back_to_item_revenue(tmp_path: Path) -> None:
    artifact = _sample_profit_contribution_artifact()
    artifact["summary"].pop("total_revenue")
    artifact["meta"] = {}
    artifact.pop("total_revenue", None)
    (tmp_path / "profit_contribution.json").write_text(
        json.dumps(artifact, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)
    section = payload["profit_contribution_section"]

    assert section["summary"]["total_revenue"] == 5000.0
    summary_rows = {row["label"]: row for row in section["summary_rows"]}
    assert summary_rows["Общая выручка"]["value"] == "5 000 ₽"
    assert summary_rows["Общая выручка"]["value"] != "нет данных"

    payload_text = json.dumps(payload, ensure_ascii=False)
    _assert_no_mojibake(payload_text)

    pdf_path = tmp_path / "report_v2_profit_revenue_fallback.pdf"
    write_report_pdf_v2(pdf_path, payload)
    pdf_text = _extract_pdf_text(pdf_path)

    assert "Общая выручка" in pdf_text
    assert "5 000 ₽" in pdf_text
    _assert_no_mojibake(pdf_text)


def test_abc_analysis_section_is_ok_when_artifact_exists(tmp_path: Path) -> None:
    (tmp_path / "abc_analysis.json").write_text(
        json.dumps(_sample_abc_analysis_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )

    section = build_abc_analysis_section_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)

    assert section["status"] == "ok"
    assert section["source"] == "abc_analysis.json"
    assert section["summary"]["total_skus"] == 3
    assert section["summary"]["category_A_count"] == 1
    assert section["summary"]["category_B_count"] == 1
    assert section["summary"]["category_C_count"] == 1
    assert section["summary"]["category_A_share"] == 0.70
    assert section["categories"]["A"][0]["sku"] == "SKU-GROW"


def test_profit_and_abc_missing_values_are_not_converted_to_zero(tmp_path: Path) -> None:
    (tmp_path / "profit_contribution.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "items": [{"sku": "SKU-MISSING", "profit": None}],
                "top_profit_skus": [{"sku": "SKU-MISSING", "profit": None}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "abc_analysis.json").write_text(
        json.dumps([{"sku": "SKU-MISSING", "abc_class": "A", "cumulative_share": None}], ensure_ascii=False),
        encoding="utf-8",
    )

    profit = build_profit_contribution_section_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)
    abc = build_abc_analysis_section_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)

    assert profit["status"] == "partial"
    assert profit["top_profit_skus"][0]["profit"] is None
    assert profit["summary"]["total_profit"] is None
    assert abc["status"] == "partial"
    assert abc["categories"]["A"][0]["metric_value"] is None


def test_payload_includes_profit_and_abc_sections_from_artifacts_root(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "cabinets" / "seller_001" / "artifacts"
    snapshot_dir = artifacts_dir / "wb_api_core" / "2026-04-21"
    snapshot_dir.mkdir(parents=True)
    snapshot_path = snapshot_dir / "snapshot.json"
    debug_path = snapshot_dir / "debug.json"
    snapshot_path.write_text(json.dumps(_sample_snapshot(), ensure_ascii=False), encoding="utf-8")
    debug_path.write_text(json.dumps(_sample_debug(), ensure_ascii=False), encoding="utf-8")
    (artifacts_dir / "profit_contribution.json").write_text(
        json.dumps(_sample_profit_contribution_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )
    (artifacts_dir / "abc_analysis.json").write_text(
        json.dumps(_sample_abc_analysis_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )

    result = build_report_v2_from_files(snapshot_path=snapshot_path, debug_path=debug_path, out_dir=tmp_path / "out")
    payload = result["payload"]

    assert payload["profit_contribution_section"]["status"] == "ok"
    assert payload["profit_contribution_section"]["top_profit_skus"][0]["sku"] == "SKU-GROW"
    assert payload["abc_analysis_section"]["status"] == "ok"
    assert payload["abc_analysis_section"]["categories"]["A"][0]["sku"] == "SKU-GROW"


def test_pdf_renders_profit_and_abc_sections(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "profit_contribution.json").write_text(
        json.dumps(_sample_profit_contribution_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )
    (artifacts_dir / "abc_analysis.json").write_text(
        json.dumps(_sample_abc_analysis_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=artifacts_dir)
    pdf_path = tmp_path / "report_v2_profit_abc.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_rows_count"] >= 0


def test_pdf_renderer_accepts_payload_without_profit_and_abc_sections(tmp_path: Path) -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    payload.pop("profit_contribution_section")
    payload.pop("abc_analysis_section")
    pdf_path = tmp_path / "report_v2_without_profit_abc.pdf"

    info = write_report_pdf_v2(pdf_path, payload)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert info["hero_rows_count"] >= 0


def test_report_v2_does_not_import_legacy_daily_report_stage() -> None:
    package_root = Path(__file__).resolve().parents[1]
    checked_files = [
        package_root / "contracts" / "report_payload_schema.py",
        package_root / "builders" / "report_payload_builder.py",
        package_root / "renderers" / "pdf_renderer_v2.py",
    ]

    for path in checked_files:
        content = path.read_text(encoding="utf-8")
        assert "cabinet_funnel" not in content
        assert "analytics_api" not in content
        assert "daily_report_stage" not in content
        assert "daily_kpi" not in content
        assert "render_kpi" not in content
        assert "financial_kpi" not in content
        assert 'metrics["totals"]' not in content
        assert "metrics['totals']" not in content
