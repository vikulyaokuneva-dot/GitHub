"""Email orchestrator skeleton.

Input: report payload and transport dependencies.
Output: delivery status payload.
Does not implement SMTP transport in stage 1.
"""

from __future__ import annotations

from typing import Dict

from ...core.contracts import ReportPayload


def send(payload: ReportPayload) -> Dict[str, str]:
    _ = payload
    return {"status": "not_implemented", "stage": "skeleton"}
