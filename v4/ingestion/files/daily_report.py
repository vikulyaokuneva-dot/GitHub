"""Daily local report parser skeleton.

Input: file path.
Output: raw parsed structure and SourceStatus.
Does not normalize and does not compute KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import SourceKind, SourceStatus, SourceStatusCode


def parse(path: str) -> tuple[dict[str, Any], SourceStatus]:
    _ = path
    return {
        "rows": None,
    }, SourceStatus(
        source_name="daily_file",
        kind=SourceKind.FILE,
        status=SourceStatusCode.NOT_IMPLEMENTED,
        is_required=True,
        warnings=["daily file parser is not implemented yet"],
    )
