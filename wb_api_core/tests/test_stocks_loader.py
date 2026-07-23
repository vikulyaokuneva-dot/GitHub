from __future__ import annotations

from typing import Any

from wb_api_core import loaders
from wb_api_core.client import STOCKS_WB_WAREHOUSES_PATH
from wb_api_core.loaders import load_stocks
from wb_api_core.normalize import normalize_bundle
from wb_api_core.reconcile import reconcile_bundle


class _StocksClient:
    analytics_base_url = "https://seller-analytics-api.wildberries.ru"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        offset = int(kwargs["json_body"]["offset"])
        if offset == 0:
            rows = [
                {"nmId": 101, "quantity": 3, "warehouseName": "Коледино"},
                {"nmId": 102, "quantity": 4, "warehouseName": "Казань"},
            ]
        else:
            rows = [{"nmId": 103, "quantity": 5, "warehouseName": "Тула"}]
        return {
            "success": True,
            "payload": {"data": {"items": rows}},
            "status_code": 200,
            "attempts": 1,
            "base_url": self.analytics_base_url,
        }

    @staticmethod
    def extract_rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return []


def _empty_bundle(stocks: dict[str, Any]) -> dict[str, Any]:
    success = {"rows_raw": [], "debug": {"success": True}}
    return {
        "cabinet_commerce": success,
        "finance_final": success,
        "orders": success,
        "sales": success,
        "stocks": stocks,
        "ads": success,
        "search_report": success,
    }


def test_stocks_loader_uses_current_analytics_endpoint_and_paginates(monkeypatch: Any) -> None:
    monkeypatch.setattr(loaders, "STOCKS_WB_WAREHOUSES_PAGE_LIMIT", 2)
    client = _StocksClient()

    result = load_stocks(client, "2026-07-22")

    assert [row["nmId"] for row in result["rows_raw"]] == [101, 102, 103]
    assert len(client.calls) == 2
    assert all(call["path"] == STOCKS_WB_WAREHOUSES_PATH for call in client.calls)
    assert all(call["method"] == "POST" for call in client.calls)
    assert all(call["base_url"] == client.analytics_base_url for call in client.calls)
    assert client.calls[0]["json_body"] == {
        "nmIds": [],
        "chrtIds": [],
        "limit": 2,
        "offset": 0,
    }
    assert client.calls[1]["json_body"]["offset"] == 2
    assert 429 in client.calls[0]["retry_policy"]["retryable_statuses"]
    assert result["debug"]["source_family"] == "stocks_wb_warehouses"
    assert result["debug"]["pagination_complete"] is True


def test_current_stocks_source_reaches_live_operational_snapshot() -> None:
    stocks = {
        "rows_raw": [
            {
                "nmId": 101,
                "quantity": 3,
                "inWayToClient": 10,
                "inWayFromClient": 8,
                "warehouseName": "Коледино",
            },
            {"nmId": 101, "quantity": 2, "warehouseName": "Казань"},
        ],
        "debug": {"success": True},
    }
    raw_bundle = _empty_bundle(stocks)

    reconciled = reconcile_bundle(
        raw_bundle=raw_bundle,
        normalized_bundle=normalize_bundle(raw_bundle),
        target_date="2026-07-22",
    )

    live_stocks = reconciled["live_operational"]["stocks"]
    assert live_stocks["source"] == "stocks_wb_warehouses_api"
    assert live_stocks["available"] is True
    assert live_stocks["total_units"] == 5.0
