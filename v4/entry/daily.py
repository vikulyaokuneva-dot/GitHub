"""Daily entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end daily pipeline result.
Does not implement business logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cabinets.paths import path_label
from ..production.switch import run_production_daily
from ..pipeline.stages.delivery_stage import run_delivery_stage
from ..pipeline.runners.multi_cabinet_runner import run_daily_for_sellers
from ..pipeline.runners.daily_runner import run_daily_pipeline


def _parse_seller_ids(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    text = str(value).strip()
    if not text:
        return []
    parts = [part.strip() for part in text.split(",")]
    return [part for part in parts if part]


def _normalize_mode_hint(production_mode: object | None) -> str:
    text = str(production_mode or "").strip().lower()
    if text in {"legacy", "v4", "shadow"}:
        return text
    return "v4_direct"


def _attach_operator_diagnostics(
    *,
    result: dict[str, Any],
    seller_id: str,
    run_date: object,
    dry_run: bool,
    output_dir: object,
    requested_mode: object | None,
) -> None:
    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
        result["diagnostics"] = diagnostics

    summary = diagnostics.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        diagnostics["summary"] = summary

    summary["dry_run"] = bool(dry_run)
    summary["requested_run_date"] = str(run_date) if run_date is not None else None
    summary["selected_production_mode"] = _normalize_mode_hint(requested_mode)
    summary["seller_id"] = seller_id
    summary["output_dir_label"] = summary.get("output_dir_label") or path_label(output_dir)

    diagnostics["operator"] = {
        "selected_production_mode": _normalize_mode_hint(requested_mode),
        "switch_reason": "direct v4 daily path (without production switch)",
        "source_of_decision": "entry_default",
        "rollback_happened": False,
        "fallback_used": False,
        "dry_run": bool(dry_run),
        "seller_id": seller_id,
        "run_date": str(run_date) if run_date is not None else None,
        "output_dir_label": str(path_label(output_dir) or ""),
    }


def run(payload: dict[str, Any] | None = None) -> dict:
    data = dict(payload or {})
    seller_ids = _parse_seller_ids(data.get("seller_ids") or data.get("sellers"))
    seller_id = str(data.get("seller_id") or "").strip()
    if seller_id:
        seller_ids = [seller_id]
    elif seller_ids:
        seller_id = seller_ids[0]
    is_multi = len(seller_ids) > 1
    dry_run = bool(data.get("dry_run", False))
    output_dir = data.get("output_dir")
    production_mode = data.get("production_mode")
    if bool(data.get("shadow_mode")) and not production_mode:
        production_mode = "shadow"
    allow_fallback_to_legacy = bool(data.get("allow_fallback_to_legacy", False))
    use_production_switch = bool(production_mode is not None or allow_fallback_to_legacy)

    if is_multi:
        if use_production_switch:
            raise ValueError("production_mode is supported only for single-seller daily runs")
        return run_daily_for_sellers(
            seller_ids=seller_ids,
            run_date=data.get("run_date") or data.get("date"),
            output_root=data.get("output_dir"),
            timezone=str(data.get("timezone") or "Europe/Moscow"),
            dry_run=bool(data.get("dry_run", False)),
            feature_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )

    if not seller_id:
        raise ValueError("seller_id is required")

    if use_production_switch:
        result = run_production_daily(
            seller_id=seller_id,
            run_date=data.get("run_date") or data.get("date"),
            output_dir=output_dir,
            cli_mode=str(production_mode) if production_mode is not None else None,
            allow_fallback_to_legacy=allow_fallback_to_legacy,
            dry_run=dry_run,
            run_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )
        production = result.get("production", {}) if isinstance(result, dict) else {}
        diagnostics = production.get("diagnostics", {}) if isinstance(production, dict) else {}
        if isinstance(diagnostics, dict):
            diagnostics["dry_run"] = bool(dry_run)
        return result

    run_context = {
        "seller_id": seller_id,
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "cabinet_id": data.get("cabinet_id"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": dry_run,
        "feature_flags": data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else {},
    }
    result = run_daily_pipeline(
        run_context=run_context,
        output_dir=output_dir,
    )
    _attach_operator_diagnostics(
        result=result,
        seller_id=seller_id,
        run_date=data.get("run_date") or data.get("date"),
        dry_run=dry_run,
        output_dir=output_dir,
        requested_mode=production_mode,
    )

    enable_pdf_render = bool(data.get("render_pdf", False))
    enable_email_preview = bool(data.get("email_preview", False))
    if enable_pdf_render or enable_email_preview:
        if dry_run:
            enriched = dict(result)
            enriched["delivery"] = {
                "pdf_path": None,
                "email_preview_path": None,
                "diagnostics": {
                    "mode": "daily",
                    "delivery_enabled": False,
                    "rendered_pdf": False,
                    "email_preview_built": False,
                    "dry_run": True,
                    "output_dir": str(Path(str(output_dir)).resolve()) if output_dir else None,
                    "output_paths": {
                        "pdf_path": None,
                        "email_preview_path": None,
                    },
                    "warnings": ["dry-run: delivery side effects skipped"],
                },
            }
            return enriched
        delivery = run_delivery_stage(
            outputs=result.get("outputs", {}),
            output_dir=output_dir,
            enable_pdf_render=enable_pdf_render,
            enable_email_preview=enable_email_preview,
        )
        enriched = dict(result)
        enriched["delivery"] = delivery
        return enriched

    return result
