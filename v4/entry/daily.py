"""Daily entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end daily pipeline result.
Does not implement KPI business logic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..cabinets.paths import path_label
from ..config.settings import get_settings
from ..core.contracts import DecisionsBundle, FactsBundle
from ..outputs.email.builder import build_email_payload
from ..pipeline.runners.daily_runner import run_daily_pipeline
from ..pipeline.runners.multi_cabinet_runner import run_daily_for_sellers
from ..pipeline.stages.delivery_stage import run_delivery_stage
from ..production.switch import run_production_daily


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


def _build_email_debug_diagnostics(
    *,
    result: dict[str, Any],
    output_dir: object,
    production_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = result.get("diagnostics", {}) if isinstance(result.get("diagnostics"), dict) else {}
    outputs = result.get("outputs", {}) if isinstance(result.get("outputs"), dict) else {}
    artifacts = outputs.get("artifacts", {}) if isinstance(outputs.get("artifacts"), dict) else {}
    saved_files = artifacts.get("saved_files", {}) if isinstance(artifacts.get("saved_files"), dict) else {}
    return {
        "job": diagnostics.get("job", {}) if isinstance(diagnostics.get("job"), dict) else {},
        "summary": diagnostics.get("summary", {}) if isinstance(diagnostics.get("summary"), dict) else {},
        "operator": diagnostics.get("operator", {}) if isinstance(diagnostics.get("operator"), dict) else {},
        "production": dict(production_diagnostics or {}),
        "warnings": list(result.get("warnings", [])) if isinstance(result.get("warnings"), list) else [],
        "artifacts": dict(saved_files),
        "output_dir": str(output_dir) if output_dir is not None else None,
    }


def _inject_full_email_debug_payload(
    *,
    result: dict[str, Any],
    mode: str,
    output_dir: object,
    production_diagnostics: dict[str, Any] | None = None,
) -> bool:
    facts_bundle = result.get("facts")
    decisions_bundle = result.get("decisions")
    outputs = result.get("outputs")
    if not isinstance(facts_bundle, FactsBundle):
        return False
    if not isinstance(decisions_bundle, DecisionsBundle):
        return False
    if not isinstance(outputs, dict):
        return False

    email_payload = build_email_payload(
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        mode=mode,
        diagnostics=_build_email_debug_diagnostics(
            result=result,
            output_dir=output_dir,
            production_diagnostics=production_diagnostics,
        ),
        full_debug=True,
    )
    outputs["email"] = email_payload
    result["outputs"] = outputs

    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
        result["diagnostics"] = diagnostics
    summary = diagnostics.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        diagnostics["summary"] = summary
    summary["full_email_debug"] = True
    return True


def _persist_diagnostics_artifact(
    *,
    result: dict[str, Any],
    output_dir: str | None,
    production_diagnostics: dict[str, Any] | None = None,
) -> str | None:
    if not output_dir:
        return None
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "diagnostics": result.get("diagnostics", {}),
        "warnings": result.get("warnings", []),
        "production": dict(production_diagnostics or {}),
    }
    path = root / "diagnostics.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _require_real_run_prerequisites(*, force_email: bool, dry_run: bool, output_dir: str | None) -> None:
    if not force_email:
        return
    if dry_run:
        raise ValueError("--force-email requires dry_run=false")
    if not str(output_dir or "").strip():
        raise ValueError("output_dir is required for --force-email")
    token_env = get_settings().wb_api_token_env
    if not str(os.getenv(token_env, "")).strip():
        raise RuntimeError("WB API token is required for real run")


def _enrich_feature_flags(base: dict[str, Any] | None, *, force_email: bool, full_email_debug: bool) -> dict[str, Any]:
    merged = dict(base or {})
    merged["enable_full_email_debug"] = bool(full_email_debug)
    if force_email:
        merged["enable_delivery"] = True
        merged["enable_pdf_render"] = True
        merged["enable_email_preview"] = True
    return merged


def _ensure_force_email_sent(delivery: dict[str, Any]) -> None:
    diagnostics = delivery.get("diagnostics", {}) if isinstance(delivery.get("diagnostics"), dict) else {}
    email_send = diagnostics.get("email_send", {}) if isinstance(diagnostics.get("email_send"), dict) else {}

    if not bool(diagnostics.get("email_send_attempted", False)):
        raise RuntimeError("Email send failed: send was not attempted")

    if not bool(diagnostics.get("email_sent", False)):
        reason = str(
            email_send.get("email_failure_reason_normalized")
            or "; ".join(diagnostics.get("warnings", []) if isinstance(diagnostics.get("warnings"), list) else [])
            or "unknown SMTP failure"
        ).strip()
        raise RuntimeError(f"Email send failed: {reason}")


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
    output_dir = str(data.get("output_dir") or "").strip() or None
    full_email_debug = bool(data.get("full_email_debug", False))
    force_email = bool(data.get("force_email", False))
    if force_email:
        full_email_debug = True

    production_mode = data.get("production_mode")
    if bool(data.get("shadow_mode")) and not production_mode:
        production_mode = "shadow"
    allow_fallback_to_legacy = bool(data.get("allow_fallback_to_legacy", False))
    use_production_switch = bool(production_mode is not None or allow_fallback_to_legacy)

    if is_multi:
        if full_email_debug or force_email:
            raise ValueError("full_email_debug/force_email are supported only for single-seller daily runs")
        if use_production_switch:
            raise ValueError("production_mode is supported only for single-seller daily runs")
        return run_daily_for_sellers(
            seller_ids=seller_ids,
            run_date=data.get("run_date") or data.get("date"),
            output_root=output_dir,
            timezone=str(data.get("timezone") or "Europe/Moscow"),
            dry_run=dry_run,
            feature_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )

    if not seller_id:
        raise ValueError("seller_id is required")

    _require_real_run_prerequisites(force_email=force_email, dry_run=dry_run, output_dir=output_dir)

    if use_production_switch:
        overrides = _enrich_feature_flags(
            data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else {},
            force_email=force_email,
            full_email_debug=full_email_debug,
        )
        result = run_production_daily(
            seller_id=seller_id,
            run_date=data.get("run_date") or data.get("date"),
            output_dir=output_dir,
            cli_mode=str(production_mode) if production_mode is not None else None,
            allow_fallback_to_legacy=allow_fallback_to_legacy,
            dry_run=dry_run,
            run_overrides=overrides,
        )
        production = result.get("production", {}) if isinstance(result, dict) else {}
        production_diag = production.get("diagnostics", {}) if isinstance(production.get("diagnostics"), dict) else {}
        if isinstance(production_diag, dict):
            production_diag["dry_run"] = bool(dry_run)

        if full_email_debug:
            selected_mode = str(production_diag.get("selected_mode") or "").strip().lower()
            run_result = result.get("run_result")
            if selected_mode != "v4" or not isinstance(run_result, dict):
                if force_email:
                    raise RuntimeError("force-email requires selected production mode v4")
                result["delivery"] = {
                    "pdf_path": None,
                    "email_preview_path": None,
                    "email_send": None,
                    "diagnostics": {
                        "delivery_enabled": False,
                        "email_send_attempted": False,
                        "email_sent": False,
                        "warnings": ["full-email-debug is available only for selected_mode=v4 with v4 run_result"],
                    },
                }
                return result

            injected = _inject_full_email_debug_payload(
                result=run_result,
                mode="daily",
                output_dir=output_dir,
                production_diagnostics=production_diag if isinstance(production_diag, dict) else None,
            )
            if not injected:
                raise RuntimeError("failed to build full-email-debug payload from v4 run_result")

            diagnostics_path = _persist_diagnostics_artifact(
                result=run_result,
                output_dir=output_dir,
                production_diagnostics=production_diag if isinstance(production_diag, dict) else None,
            )
            extra_attachments = [diagnostics_path] if diagnostics_path else []

            if dry_run:
                result["delivery"] = {
                    "pdf_path": None,
                    "email_preview_path": None,
                    "email_send": None,
                    "diagnostics": {
                        "mode": "daily",
                        "delivery_enabled": False,
                        "rendered_pdf": False,
                        "email_preview_built": False,
                        "email_send_attempted": False,
                        "email_sent": False,
                        "dry_run": True,
                        "warnings": ["dry-run: full-email-debug SMTP send skipped"],
                    },
                }
                return result

            delivery = run_delivery_stage(
                outputs=run_result.get("outputs", {}),
                output_dir=output_dir,
                enable_pdf_render=True,
                enable_email_preview=True,
                enable_email_send=bool(force_email),
                extra_attachments=extra_attachments,
            )
            if force_email:
                _ensure_force_email_sent(delivery)
            result["delivery"] = delivery
        return result

    run_context = {
        "seller_id": seller_id,
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "cabinet_id": data.get("cabinet_id"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": dry_run,
        "feature_flags": _enrich_feature_flags(
            data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else {},
            force_email=force_email,
            full_email_debug=full_email_debug,
        ),
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

    if full_email_debug:
        injected = _inject_full_email_debug_payload(
            result=result,
            mode="daily",
            output_dir=output_dir,
        )
        if not injected:
            raise RuntimeError("failed to build full-email-debug payload")

    diagnostics_path = _persist_diagnostics_artifact(result=result, output_dir=output_dir)
    extra_attachments = [diagnostics_path] if diagnostics_path else []

    enable_pdf_render = bool(data.get("render_pdf", False) or full_email_debug or force_email)
    enable_email_preview = bool(data.get("email_preview", False) or full_email_debug or force_email)
    enable_email_send = bool(force_email and not dry_run)

    if force_email and not (enable_pdf_render and enable_email_preview):
        raise RuntimeError("Delivery is required in force-email mode")

    if enable_pdf_render or enable_email_preview or enable_email_send:
        if dry_run:
            enriched = dict(result)
            enriched["delivery"] = {
                "pdf_path": None,
                "email_preview_path": None,
                "email_send": None,
                "diagnostics": {
                    "mode": "daily",
                    "delivery_enabled": False,
                    "rendered_pdf": False,
                    "email_preview_built": False,
                    "email_send_attempted": False,
                    "email_sent": False,
                    "dry_run": True,
                    "output_dir": str(Path(output_dir).resolve()) if output_dir else None,
                    "output_paths": {"pdf_path": None, "email_preview_path": None},
                    "warnings": ["dry-run: delivery side effects skipped"],
                },
            }
            return enriched

        delivery = run_delivery_stage(
            outputs=result.get("outputs", {}),
            output_dir=output_dir,
            enable_pdf_render=enable_pdf_render,
            enable_email_preview=enable_email_preview,
            enable_email_send=enable_email_send,
            extra_attachments=extra_attachments,
        )
        if force_email:
            _ensure_force_email_sent(delivery)
        enriched = dict(result)
        enriched["delivery"] = delivery
        return enriched

    return result
