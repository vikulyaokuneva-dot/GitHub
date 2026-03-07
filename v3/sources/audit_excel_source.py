from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os

from ..ctx import SellerContext

def collect(ctx: SellerContext, input_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    warnings: List[Dict[str, Any]] = []
    if not input_path or not os.path.exists(input_path):
        warnings.append({"code":"audit_input_missing","message": f"Audit input not found: {input_path}"})
        return {"raw": {}}, warnings

    # Stub: no parsing yet
    warnings.append({"code":"audit_stub","message":"Audit Excel parsing not connected yet in v3 skeleton (stub)."})
    return {"raw": {"input_path": input_path}}, warnings
