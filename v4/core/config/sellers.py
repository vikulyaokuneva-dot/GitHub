"""Seller config skeleton.

Input: repository-level seller identifiers.
Output: seller config metadata.
Does not perform discovery from runtime artifact folders.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SellerConfig:
    seller_id: str
    seller_name: str
    timezone: str = "Europe/Moscow"
