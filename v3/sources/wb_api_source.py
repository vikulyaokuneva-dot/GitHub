from __future__ import annotations
from typing import Any, Dict, List, Tuple
import traceback

from ..ctx import SellerContext

def collect(ctx: SellerContext) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Скелет: пытаемся достать WB токен, но НЕ падаем, если его нет.
    На следующем шаге тут подключим реальные сборщики из v2-5 (WBClient + facts_builder).
    """
    warnings: List[Dict[str, Any]] = []
    token = ctx.get_wb_token()
    if not token:
        warnings.append({
            "code": "wb_token_missing",
            "message": f"WB token missing for token_ref={ctx.token_ref or '(empty)'}",
        })
        # return empty raw
        return {"raw": {}}, warnings

    # Skeleton: no real api calls yet
    warnings.append({
        "code": "wb_api_stub",
        "message": "WB API calls not connected yet in v3 skeleton (stub).",
    })
    return {"raw": {}}, warnings
