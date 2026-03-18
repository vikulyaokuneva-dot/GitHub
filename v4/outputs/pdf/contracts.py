"""PDF payload contracts.

Input: FactsBundle + DecisionsBundle.
Output: PDF-ready payload (no rendering engine yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PdfBlock:
    """Block of tabular rows for a PDF page."""

    title: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    status: str = "unavailable"
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PdfPage:
    """Single logical PDF page payload."""

    title: str
    blocks: list[PdfBlock] = field(default_factory=list)


@dataclass
class PdfPayload:
    """Top-level PDF payload for future renderer."""

    mode: str
    pages: list[PdfPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

