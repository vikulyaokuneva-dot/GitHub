"""Daily entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end daily pipeline result.
Does not implement business logic.
"""

from __future__ import annotations

from typing import Any

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


def run(payload: dict[str, Any] | None = None) -> dict:
    data = dict(payload or {})
    seller_ids = _parse_seller_ids(data.get("seller_ids") or data.get("sellers"))
    seller_id = str(data.get("seller_id") or "").strip()
    if seller_id:
        seller_ids = [seller_id]
    elif seller_ids:
        seller_id = seller_ids[0]
    is_multi = len(seller_ids) > 1
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
            output_dir=data.get("output_dir"),
            cli_mode=str(production_mode) if production_mode is not None else None,
            allow_fallback_to_legacy=allow_fallback_to_legacy,
            run_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )
        return result

    run_context = {
        "seller_id": seller_id,
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "cabinet_id": data.get("cabinet_id"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": bool(data.get("dry_run", False)),
        "feature_flags": data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else {},
    }
    result = run_daily_pipeline(
        run_context=run_context,
        output_dir=data.get("output_dir"),
    )

    enable_pdf_render = bool(data.get("render_pdf", False))
    enable_email_preview = bool(data.get("email_preview", False))
    if enable_pdf_render or enable_email_preview:
        delivery = run_delivery_stage(
            outputs=result.get("outputs", {}),
            output_dir=data.get("output_dir"),
            enable_pdf_render=enable_pdf_render,
            enable_email_preview=enable_email_preview,
        )
        enriched = dict(result)
        enriched["delivery"] = delivery
        return enriched

    return result
