"""Realization API ingestion skeleton.

Input: RunContext and ApiClient.
Output: raw payload plus SourceStatus.
Does not normalize and does not compute metrics.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ...core.contracts import RunContext, SourceStatus
from .client import ApiClient


def load(context: RunContext, client: ApiClient) -> Tuple[Dict[str, Any], SourceStatus]:
    """Load raw realization payload (skeleton)."""
    _ = (context, client)
    return {}, SourceStatus(source="api", status="not_implemented", reason="stage_1_skeleton")
