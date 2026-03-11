from __future__ import annotations

from typing import Any, Dict


def load_ads_from_api_placeholder(date_from: str, date_to: str) -> Dict[str, Any]:
    return {
        "rows": [],
        "api_debug": {
            "endpoint": "ads",
            "success": False,
            "fail": True,
            "rows_loaded": 0,
            "date_from": date_from,
            "date_to": date_to,
            "error_text": "not_implemented: using legacy ads loader",
            "status_code": None,
            "attempts": 0,
        },
    }

