"""Tests for v2-compatible ingestion loader in v5."""

from __future__ import annotations

from datetime import date

from ..domain.cabinet import Cabinet, CabinetConfig, CabinetContext
from ..infrastructure.sources_v2_compat import wb_v2_compat_loader as mod


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


class _FakeV2Client:
    def __init__(self, token: str, raw_dir: str):
        self.token = token
        self.raw_dir = raw_dir

    def fetch_sales_funnel(self, date_from: str, date_to: str):
        return {
            "data": {
                "products": [
                    {
                        "nmId": 101,
                        "rating": 4.7,
                        "feedbackCount": 12,
                        "statistic": {"selected": {"orderCount": 2}},
                    }
                ]
            }
        }

    def fetch_stocks(self):
        return [{"nmId": 101, "quantity": 5}]

    def fetch_realization_report(self, date_from: str, date_to: str):
        # First date (target) returns empty, lag day returns data.
        if date_from == "2026-04-01":
            return []
        return [
            {
                "rrdId": 1,
                "nmId": 101,
                "date": "2026-03-31",
                "quantity": 1,
                "saleSum": 1000,
                "commission": 100,
                "price": 1200,
                "costPrice": 700,
                "status": "sale",
            },
            {
                "rrdId": 2,
                "nmId": 101,
                "date": "2026-03-31",
                "quantity": 1,
                "saleSum": 1000,
                "status": "return",
            },
        ]


def test_v2_compat_loader_builds_counts_and_uses_v5_raw_dir(tmp_path, monkeypatch) -> None:
    ctx = _build_ctx(tmp_path)
    target_date = date(2026, 4, 1)

    monkeypatch.setattr(mod, "V2WBClient", _FakeV2Client)
    monkeypatch.setattr(
        mod,
        "v2_load_ads_stats",
        lambda client, date_from, date_to, manual_dir: (
            [
                {
                    "advertId": 77,
                    "advertName": "Ad 77",
                    "statistic": [
                        {"date": "2026-04-01T00:00:00", "shows": 100, "clicks": 10, "spend": 50}
                    ],
                }
            ],
            "api",
            None,
        ),
    )
    monkeypatch.setattr(mod, "calc_funnel_metrics", lambda funnel_raw: {"orders": 2})
    monkeypatch.setattr(mod, "calc_financial_metrics", lambda realization_raw, tax_rate=0.06: {"returns_qty": 1})

    loader = mod.V2CompatibleWBAPILoader(max_finance_lag_days=2, manual_ads_dir="data/manual_ads", tax_rate=0.06)
    raw = loader._load_data_sync(ctx, target_date)

    assert raw.source == "api"
    assert raw.debug["ingestion_path"] == "v2_compat"
    assert raw.debug["finance_lag_days"] == 1
    assert raw.debug["finance_date_used"] == "2026-03-31"

    comparison = raw.debug["source_counts_comparison"]
    assert comparison["v2_truth_counts"]["orders_count"] == 2
    assert comparison["v5_compat_counts"]["ads_count"] >= comparison["v2_truth_counts"]["ads_count"]
    assert (ctx.raw_data_dir / "v2_compat_raw").exists()

