"""Audit entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end audit pipeline result.
Does not implement business logic.
"""

from __future__ import annotations

from typing import Any

from ..pipeline.stages.delivery_stage import run_delivery_stage
from ..pipeline.runners.multi_cabinet_runner import run_audit_for_sellers
from ..pipeline.runners.audit_runner import run_audit_pipeline


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
    return [part for part in [item.strip() for item in text.split(",")] if part]


def _parse_input_map(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        parsed: dict[str, str] = {}
        for key, path in value.items():
            seller_id = str(key or "").strip()
            input_path = str(path or "").strip()
            if seller_id and input_path:
                parsed[seller_id] = input_path
        return parsed
    text = str(value).strip()
    if not text:
        return {}
    parsed: dict[str, str] = {}
    chunks = [chunk.strip() for chunk in text.split(",")]
    for chunk in chunks:
        if "=" not in chunk:
            continue
        seller_id, input_path = chunk.split("=", 1)
        seller_id = seller_id.strip()
        input_path = input_path.strip()
        if seller_id and input_path:
            parsed[seller_id] = input_path
    return parsed


def run(payload: dict[str, Any] | None = None) -> dict:
    data = dict(payload or {})
    input_path = str(data.get("input_path") or "").strip()
    seller_ids = _parse_seller_ids(data.get("seller_ids") or data.get("sellers"))
    seller_id = str(data.get("seller_id") or "").strip()
    if seller_id:
        seller_ids = [seller_id]
    elif seller_ids:
        seller_id = seller_ids[0]

    input_map = _parse_input_map(data.get("input_map"))
    if input_map:
        return run_audit_for_sellers(
            input_map=input_map,
            run_date=data.get("run_date") or data.get("date"),
            output_root=data.get("output_dir"),
            timezone=str(data.get("timezone") or "Europe/Moscow"),
            dry_run=bool(data.get("dry_run", False)),
            seller_ids=seller_ids or None,
            feature_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )

    if len(seller_ids) > 1:
        if not input_path:
            raise ValueError("input_path is required for multi-seller audit without input_map")
        multi_input_map = {sid: input_path for sid in seller_ids}
        return run_audit_for_sellers(
            input_map=multi_input_map,
            run_date=data.get("run_date") or data.get("date"),
            output_root=data.get("output_dir"),
            timezone=str(data.get("timezone") or "Europe/Moscow"),
            dry_run=bool(data.get("dry_run", False)),
            feature_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )

    if not input_path:
        raise ValueError("input_path is required for audit mode")

    run_context = {
        "seller_id": seller_id or "seller_001",
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "cabinet_id": data.get("cabinet_id"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": bool(data.get("dry_run", False)),
        "feature_flags": data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else {},
        "input_path_label": data.get("input_path_label"),
    }
    result = run_audit_pipeline(
        input_path=input_path,
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
