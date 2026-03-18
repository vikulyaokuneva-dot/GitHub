"""Seller orchestration skeleton.

Input: seller id, mode, run date.
Output: high-level run status placeholder.
Does not execute real stages in stage 1.
"""

from __future__ import annotations

from typing import Dict


def run_for_seller(*, seller_id: str, mode: str, run_date: str) -> Dict[str, str]:
    _ = (seller_id, mode, run_date)
    return {"status": "not_implemented", "stage": "skeleton"}
