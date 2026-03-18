"""API client skeleton for v4 ingestion.

Input: endpoint name and params.
Output: raw API payload.
Does not normalize and does not compute metrics.
"""

from __future__ import annotations

from typing import Any, Dict


class ApiClient:
    """Thin transport abstraction for API loaders."""

    def __init__(self, token: str) -> None:
        self.token = token

    def request_json(self, endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Placeholder transport call.

        Not implemented in stage 1 skeleton.
        """
        raise NotImplementedError("ApiClient.request_json is not implemented in stage 1")
