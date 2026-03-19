"""Seller orchestrator for v4 input stage.

Input: seller/mode/date runtime args.
Output: IngestionResult from input stage.
Does not execute metrics/facts/outputs.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from ...cabinets.paths import path_label
from ...config.features import resolve_feature_flags
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
    cabinet_id: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
    output_dir: str | None = None,
    feature_flags: dict[str, bool] | None = None,
    path_labels: dict[str, str] | None = None,
    input_path_label: str | None = None,
) -> RunContext:
    resolved_mode = _coerce_mode(mode)
    requested_date = _coerce_date(run_date)
    resolved_date = requested_date if requested_date is not None else date.today()
    token_present = bool(str(os.getenv("WB_API_TOKEN", "")).strip())
    output_label = path_label(output_dir)
    normalized_path_labels: dict[str, str] = {}
    for key, value in (path_labels or {}).items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            normalized_path_labels[key_text] = value_text
    if output_label:
        normalized_path_labels["output_dir_label"] = output_label
    if input_path_label:
        normalized_path_labels["input_path_label"] = str(input_path_label)
    resolved_feature_flags = resolve_feature_flags(
        run_context={"mode": resolved_mode.value},
        run_overrides=feature_flags or {},
    )

    return RunContext(
        seller_id=str(seller_id).strip(),
        cabinet_name=(str(cabinet_name).strip() or None) if cabinet_name is not None else None,
        cabinet_id=(str(cabinet_id).strip() or None) if cabinet_id is not None else None,
        mode=resolved_mode,
        requested_date=requested_date,
        resolved_date=resolved_date,
        timezone=str(timezone or "Europe/Moscow"),
        wb_api_token_present=token_present,
        dry_run=bool(dry_run),
        output_dir=output_label,
        feature_flags=resolved_feature_flags,
        path_labels=normalized_path_labels,
        input_path_label=(str(input_path_label).strip() or None) if input_path_label else None,
    )


def run_for_seller(
    *,
    seller_id: str,
    mode: RunMode | str,
    run_date: Any = None,
    cabinet_name: str | None = None,
    cabinet_id: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
    output_dir: str | None = None,
    feature_flags: dict[str, bool] | None = None,
    path_labels: dict[str, str] | None = None,
    input_path_label: str | None = None,
) -> IngestionResult:
    context = build_run_context(
        seller_id=seller_id,
        mode=mode,
        run_date=run_date,
        cabinet_name=cabinet_name,
        cabinet_id=cabinet_id,
        timezone=timezone,
        dry_run=dry_run,
        output_dir=output_dir,
        feature_flags=feature_flags,
        path_labels=path_labels,
        input_path_label=input_path_label,
    )
    return run_input_stage(context)
