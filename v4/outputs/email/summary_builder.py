"""Email summary skeleton.

Input: ReportPayload.
Output: compact email body payload.
Does not send transport messages.
"""

from __future__ import annotations

from typing import Dict

from ...core.contracts import ReportPayload


def build(payload: ReportPayload) -> Dict[str, str]:
    _ = payload
    return {"status": "not_implemented", "stage": "skeleton"}
