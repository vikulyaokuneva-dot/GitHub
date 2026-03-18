"""Event-date model skeleton.

Input: run date context and source diagnostics.
Output: minimal event model for contracts.
Does not infer business metrics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventDateModel:
    report_date: str
    operational_date: str
    timezone: str
    shifted_to_previous_day: bool = False
