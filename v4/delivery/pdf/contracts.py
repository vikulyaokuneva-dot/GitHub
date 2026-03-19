"""PDF delivery contracts.

Input: PdfPayload from outputs layer.
Output: delivery diagnostics metadata for renderer integrations.
Does not recompute KPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PdfRenderInfo:
    """Lightweight metadata for rendered PDF artifact."""

    mode: str
    output_path: str
    rendered_pages: int = 0
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
