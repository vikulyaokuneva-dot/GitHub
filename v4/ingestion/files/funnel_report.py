"""Funnel local report parser skeleton.

Input: file path.
Output: raw parsed structure and SourceStatus.
Does not normalize and does not compute KPI.
"""

from __future__ import annotations

from typing import Dict, Tuple

from ...core.contracts import SourceStatus


def parse(path: str) -> Tuple[Dict[str, object], SourceStatus]:
    _ = path
    return {}, SourceStatus(source="file", status="not_implemented", reason="stage_1_skeleton")
