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


def _sample_ads_efficiency() -> dict:
    return {
        "status": "ok",
        "analysis_mode": "full",
        "summary": {
            "portfolio_ad_spend": 1200.0,
            "portfolio_revenue_from_ads": 6000.0,
            "portfolio_profit_from_ads": 1800.0,
            "portfolio_ROMI": 150.0,
            "portfolio_DRR": 20.0,
            "portfolio_CPO": 120.0,
        },
        "query_profitability": {
            "status": "ok",
            "analysis_mode": "full",
            "items": [
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
                }
            ],
        },
        "signals": [
            {
                "type": "ads_budget_leak",
                "recommendation": "Pause leak query and move budget to profitable traffic.",
            }
        ],
        "source": {"query_source": "advertising_efficiency.json"},
    }


def _sample_sku_health() -> dict:
    return {
        "health_score": {
            "status": "ok",
            "summary": {
                "status": "ok",
                "total_skus": 3,
                "status_counts": {"risk": 1, "healthy": 1, "strong": 1},
                "average_health_score": 7.4,
                "LIQUIDATE": 1,
            },
            "items": [{"sku": "SKU-RISK", "health_score": 2.0, "status": "LIQUIDATE"}],
        },
        "sku_watchlists": {
            "watchlists": {
                "top_growth": [{"sku": "SKU-GROW", "attention_score": 10, "reason": "Growth"}],
                "top_risk": [{"sku": "SKU-RISK", "attention_score": 90, "reason": "Risk"}],
                "dead_stock": [{"sku": "SKU-RISK", "attention_score": 90, "reason": "Dead stock"}],
                "ad_inefficiency": [],
                "conversion_drop": [],
                "logistics_risk": [],
            }
        },
        "sku_alerts": {
            "items": [
                {
                    "sku": "SKU-RISK",
                    "attention_score": 90,
                    "alerts": [{"type": "dead_stock", "status": "critical", "reason": "Liquidate stale stock."}],
                }
            ]
        },
    }


def _sample_profit_contribution() -> dict:
    return {
        "status": "ok",
        "summary": {
            "total_profit": 800.0,
            "total_revenue": 5000.0,
            "top_sku_share": 0.875,
            "loss_sku_count": 1,
        },
        "items": [
            {"sku": "SKU-GROW", "revenue": 3000.0, "profit": 700.0, "profit_share": 0.875, "status": "ok"},
            {"sku": "SKU-RISK", "revenue": 1000.0, "profit": -100.0, "profit_share": -0.125, "status": "ok"},
        ],
        "top_profit_skus": [
            {"sku": "SKU-GROW", "revenue": 3000.0, "profit": 700.0, "profit_share": 0.875, "status": "ok"}
        ],
        "top_loss_sku": [
            {"sku": "SKU-RISK", "revenue": 1000.0, "profit": -100.0, "profit_share": -0.125, "status": "ok"}
        ],
    }


def _sample_abc_analysis() -> list[dict]:
    return [
        {"sku": "SKU-GROW", "profit": 700.0, "share": 0.70, "cumulative_share": 0.70, "abc_class": "A"},
        {"sku": "SKU-RISK", "profit": -100.0, "share": -0.10, "cumulative_share": 0.80, "abc_class": "C"},
    ]


def test_render_email_html_contains_seller_and_orders_count() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    html = render_email_html(payload)

    assert "seller_001" in html
    assert "Заказы" in html
    assert "5" in html


def test_render_email_text_contains_finance_block() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    text = render_email_text(payload)

    assert "Finance:" in text
    assert "Gross revenue: 4 652.00" in text
    assert "Seller payout: 4 868.22" in text


def test_email_contains_ads_summary_when_data_exists() -> None:
    snapshot = _sample_snapshot()
    snapshot["advertising_efficiency"] = _sample_ads_efficiency()
    payload = build_report_payload_v2(snapshot, debug=_sample_debug())

    html = render_email_html(payload)
    text = render_email_text(payload)

    assert "Advertising" in html
    assert "1 200.00" in html
    assert "20,00%" in html
    assert "5,00x" in html
    assert "Wasted spend: 700.00" in text
    assert "Pause leak query" in text


def test_email_renders_sku_summary_when_data_exists() -> None:
    snapshot = _sample_snapshot()
    snapshot.update(_sample_sku_health())
    payload = build_report_payload_v2(snapshot, debug=_sample_debug())

    html = render_email_html(payload)
    text = render_email_text(payload)

    assert "Товары" in html
    assert "SKU в росте: 1" in text
    assert "SKU под риском: 1" in text
    assert "Требуют внимания: 1" in text
    assert "Liquidate stale stock." in text


def test_email_renders_profit_and_assortment_summary(tmp_path: Path) -> None:
    (tmp_path / "profit_contribution.json").write_text(
        json.dumps(_sample_profit_contribution(), ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "abc_analysis.json").write_text(
        json.dumps(_sample_abc_analysis(), ensure_ascii=False),
        encoding="utf-8",
    )
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug(), artifact_dir=tmp_path)

    html = render_email_html(payload)
    text = render_email_text(payload)

    assert "Прибыль и ассортимент" in html
    assert "Прибыль и ассортимент:" in text
    assert "1 SKU дают 87,50% прибыли" in text
    assert "Убыточные SKU: 1" in text
    assert "A-категория: 1 SKU" in text


def test_email_profit_and_assortment_no_data_message() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())

    text = render_email_text(payload)

    assert "Данные по прибыли и ассортименту недоступны" in text


def test_email_renderer_accepts_payload_without_sku_health_section() -> None:
    payload = build_report_payload_v2(_sample_snapshot(), debug=_sample_debug())
    payload.pop("sku_health_section")
    payload.pop("profit_contribution_section")
    payload.pop("abc_analysis_section")

    html = render_email_html(payload)
    text = render_email_text(payload)

    assert "Товары" in html
    assert "SKU-аналитика недоступна" in text


    assert "Данные по прибыли и ассортименту недоступны" in text


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
