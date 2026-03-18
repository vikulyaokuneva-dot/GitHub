"""Normalization model aliases.

Input: contract imports.
Output: named exports for normalization layer.
Does not apply transformations.
"""

from __future__ import annotations

from ..core.contracts import NormalizedBundle, NormalizedRecord

__all__ = ["NormalizedBundle", "NormalizedRecord"]
