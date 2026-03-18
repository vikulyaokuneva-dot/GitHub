"""PDF renderer skeleton.

Input: ReportPayload.
Output: render metadata.
Does not compute metrics and does not send email.
"""

from __future__ import annotations

from typing import Dict

from ...core.contracts import ReportPayload


def render(payload: ReportPayload) -> Dict[str, str]:
    _ = payload
    return {"status": "not_implemented", "stage": "skeleton"}
