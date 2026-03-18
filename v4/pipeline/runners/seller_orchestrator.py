"""Seller orchestrator for v4 input stage.

Input: seller/mode/date runtime args.
Output: IngestionResult from input stage.
Does not execute metrics/facts/outputs.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from ...core.contracts import IngestionResult, RunContext, RunMode
from ..stages.input_stage import run as run_input_stage


def _coerce_mode(value: RunMode | str) -> RunMode:
    if isinstance(value, RunMode):
        return value
    text = str(value or "").strip()
    try:
        return RunMode(text)
    except ValueError as exc:
        raise ValueError(f"Unsupported run mode: {value}") from exc


def _coerce_date(value: Any) -> date | str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return text


def build_run_context(
    *,
    seller_id: str,
    mode: RunMode | str,
    run_date: Any = None,
    cabinet_name: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
) -> RunContext:
    resolved_mode = _coerce_mode(mode)
    requested_date = _coerce_date(run_date)
    resolved_date = requested_date if requested_date is not None else date.today()
    token_present = bool(str(os.getenv("WB_API_TOKEN", "")).strip())

    return RunContext(
        seller_id=str(seller_id).strip(),
        cabinet_name=(str(cabinet_name).strip() or None) if cabinet_name is not None else None,
        mode=resolved_mode,
        requested_date=requested_date,
        resolved_date=resolved_date,
        timezone=str(timezone or "Europe/Moscow"),
        wb_api_token_present=token_present,
        dry_run=bool(dry_run),
    )


def run_for_seller(
    *,
    seller_id: str,
    mode: RunMode | str,
    run_date: Any = None,
    cabinet_name: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
) -> IngestionResult:
    context = build_run_context(
        seller_id=seller_id,
        mode=mode,
        run_date=run_date,
        cabinet_name=cabinet_name,
        timezone=timezone,
        dry_run=dry_run,
    )
    return run_input_stage(context)
