from __future__ import annotations

from typing import Any

from v3.api.endpoints import BASE_ANALYTICS, STOCKS
from v3.ingestion.api_stocks_loader import load_stocks_from_api


class _Client:
    def __init__(self) -> None:
        self.call: dict[str, Any] = {}

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.call = kwargs
        return {
            "success": True,
            "payload": {
                "data": {
                    "items": [
                        {
                            "nmId": 1001020,
                            "warehouseName": "Коледино",
                            "regionName": "Москва",
                            "quantity": 7,
                            "inWayToClient": 14,
                            "inWayFromClient": 11,
                        }
                    ]
                }
            },
            "status_code": 200,
            "attempts": 1,
        }

    @staticmethod
    def extract_rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return []


def test_v3_stocks_loader_uses_current_wb_warehouses_api() -> None:
    client = _Client()

    result = load_stocks_from_api(client, "2026-06-22", "2026-07-22")

    assert STOCKS.base == BASE_ANALYTICS
    assert STOCKS.path == "/api/analytics/v1/stocks-report/wb-warehouses"
    assert client.call["endpoint"] == STOCKS
    assert client.call["method"] == "POST"
    assert client.call["json_body"] == {
        "nmIds": [],
        "chrtIds": [],
        "limit": 250000,
        "offset": 0,
    }
    assert result["rows"][0]["stock"] == 7.0
    assert result["rows"][0]["_source_dataset"] == "stocks_wb_warehouses_api"
    assert result["api_debug"]["snapshot_kind"] == "current"
