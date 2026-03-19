"""Operator preflight checks for safe local/scheduled runs.

Preflight validates runtime readiness and path safety.
It does not execute KPI/business stages.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..cabinets.paths import (
    build_artifact_subpaths,
    ensure_within_root,
    get_audit_output_dir,
    get_daily_output_dir,
    get_temp_dir,
    path_label,
)
from ..cabinets.registry import get_cabinet_by_seller, get_enabled_cabinets
from ..config.features import resolve_feature_flags
from ..config.settings import get_settings
from ..production.switch import resolve_production_mode


def _normalize_mode(value: object) -> str:
    text = str(value or "daily").strip().lower()
    if text == "audit":
        return "audit"
    return "daily"


def _parse_seller_ids(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [chunk for chunk in [part.strip() for part in text.split(",")] if chunk]


def _resolve_single_seller_id(payload: dict[str, Any]) -> str:
    seller_id = str(payload.get("seller_id") or payload.get("seller") or "").strip()
    if seller_id:
        return seller_id

    sellers_csv = payload.get("seller_ids") or payload.get("sellers")
    seller_ids = _parse_seller_ids(sellers_csv)
    if seller_ids:
        return seller_ids[0]

    enabled = get_enabled_cabinets()
    if len(enabled) == 1:
        return enabled[0].seller_id
    if len(enabled) == 0:
        raise ValueError("Нет включенных seller в registry; укажите --seller явно.")
    raise ValueError("Найдено несколько seller; укажите --seller явно для детерминированного запуска.")


def _resolve_output_dir(
    *,
    mode: str,
    seller_id: str,
    run_date: str | None,
    explicit_output_dir: object,
) -> Path:
    settings = get_settings()
    seller = get_cabinet_by_seller(seller_id)
    output_subdir = seller.output_subdir if seller is not None else None
    cabinet_id = seller.cabinet_id if seller is not None else None

    if explicit_output_dir is not None and str(explicit_output_dir).strip():
        output_dir = Path(str(explicit_output_dir)).resolve()
        allowed_root = Path(settings.output_root).resolve()
        try:
            ensure_within_root(allowed_root, output_dir)
        except ValueError as exc:
            raise ValueError(
                "output_dir is outside the allowed root. "
                f"allowed_root={allowed_root}; "
                "use a path inside ./.tmp/v4_outputs, for example "
                "'./.tmp/v4_outputs/scheduled_daily'"
            ) from exc
        return output_dir

    if mode == "audit":
        return get_audit_output_dir(
            seller_id=seller_id,
            cabinet_id=cabinet_id,
            run_date=run_date,
            output_root=settings.output_root,
            output_subdir=output_subdir,
        ).resolve()
    return get_daily_output_dir(
        seller_id=seller_id,
        cabinet_id=cabinet_id,
        run_date=run_date,
        output_root=settings.output_root,
        output_subdir=output_subdir,
    ).resolve()


def _check_write_access(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    probe = target_dir / ".preflight_write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    mode = _normalize_mode(data.get("mode"))
    dry_run = bool(data.get("dry_run", False))
    full_email_debug = bool(data.get("full_email_debug", False))
    run_date = str(data.get("run_date") or data.get("date") or "").strip() or None

    checks: list[dict[str, str]] = []
    warnings: list[str] = []
    errors: list[str] = []

    settings = get_settings()
    checks.append({"name": "settings", "status": "ok", "detail": "settings loaded"})

    seller_id = _resolve_single_seller_id(data)
    seller = get_cabinet_by_seller(seller_id)
    if seller is None:
        raise ValueError(f"Unknown seller_id: {seller_id}")
    if not seller.is_enabled:
        raise ValueError(f"Seller is disabled: {seller_id}")
    checks.append({"name": "seller_registry", "status": "ok", "detail": f"seller={seller_id}"})

    run_context_mode = "audit_file_mode" if mode == "audit" else "daily_api_mode"
    feature_flags = resolve_feature_flags(
        run_context={"mode": run_context_mode},
        seller_config=seller,
        run_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
    )
    checks.append({"name": "feature_flags", "status": "ok", "detail": f"flags={len(feature_flags)}"})

    token_env_name = settings.wb_api_token_env
    token_present = bool(str(os.getenv(token_env_name, "")).strip())
    requested_mode = str(data.get("production_mode") or "").strip() or None
    production_preview: dict[str, Any] | None = None
    if mode == "daily":
        decision = resolve_production_mode(
            seller_id=seller_id,
            cli_mode=requested_mode,
            run_overrides=data.get("feature_flags") if isinstance(data.get("feature_flags"), dict) else None,
        )
        production_preview = {
            "selected_mode": decision.selected_mode.value,
            "reason": decision.reason,
            "source_of_decision": decision.source_of_decision,
            "rollback_allowed": bool(decision.rollback_allowed),
            "notes": list(decision.notes),
        }
        checks.append(
            {
                "name": "production_mode_resolution",
                "status": "ok",
                "detail": f"selected={decision.selected_mode.value}; source={decision.source_of_decision}",
            }
        )
        if requested_mode and decision.selected_mode.value != requested_mode:
            warnings.append(
                "Запрошенный production-mode отличается от effective mode; проверьте feature flags и overrides."
            )

    if mode == "daily" and not token_present and not dry_run:
        errors.append(f"Отсутствует обязательный env var: {token_env_name}")
        checks.append(
            {
                "name": "env_required",
                "status": "failed",
                "detail": f"{token_env_name}=missing",
            }
        )
    else:
        detail = f"{token_env_name}={'present' if token_present else 'missing'}"
        checks.append({"name": "env_required", "status": "ok", "detail": detail})
        if not token_present:
            warnings.append(f"{token_env_name} не задан; в dry-run это допустимо.")

    if full_email_debug:
        checks.append({"name": "full_email_debug", "status": "ok", "detail": "enabled"})
        required_email_env = ("YANDEX_SMTP_USER", "YANDEX_SMTP_APP_PASS", "EMAIL_TO")
        missing_email_env = [name for name in required_email_env if not str(os.getenv(name, "")).strip()]
        if not dry_run and missing_email_env:
            errors.append(f"Для full-email-debug отсутствуют env vars: {', '.join(missing_email_env)}")
            checks.append(
                {
                    "name": "email_env_required",
                    "status": "failed",
                    "detail": f"missing={missing_email_env}",
                }
            )
        else:
            checks.append(
                {
                    "name": "email_env_required",
                    "status": "ok",
                    "detail": f"missing={missing_email_env}",
                }
            )
            if missing_email_env:
                warnings.append("full-email-debug в dry-run: SMTP env vars не обязательны.")

    output_dir: Path | None = None
    try:
        output_dir = _resolve_output_dir(
            mode=mode,
            seller_id=seller_id,
            run_date=run_date,
            explicit_output_dir=data.get("output_dir"),
        )
    except Exception as exc:
        errors.append(f"Output path validation failed: {exc}")
        checks.append({"name": "output_dir_access", "status": "failed", "detail": str(exc)})

    if output_dir is None:
        ok = not errors
        return {
            "ok": ok,
            "status": "SUCCESS" if ok else "FAILED",
            "mode": mode,
            "seller_id": seller_id,
            "run_date": run_date,
            "dry_run": dry_run,
            "resolved_output_dir": None,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "feature_flags": feature_flags,
            "production_preview": production_preview,
        }
    try:
        _check_write_access(output_dir)
        checks.append(
            {
                "name": "output_dir_access",
                "status": "ok",
                "detail": str(path_label(output_dir) or output_dir),
            }
        )
    except Exception as exc:
        errors.append(f"Не удалось подготовить output_dir: {exc}")
        checks.append({"name": "output_dir_access", "status": "failed", "detail": str(exc)})

    try:
        artifact_paths = build_artifact_subpaths(output_dir)
        outside = []
        for name, value in artifact_paths.items():
            try:
                ensure_within_root(output_dir, Path(value))
            except Exception:
                outside.append(name)
        if outside:
            raise ValueError(f"artifact paths escape output_dir: {outside}")
        checks.append({"name": "artifact_path_safety", "status": "ok", "detail": "all inside output_dir"})
    except Exception as exc:
        errors.append(f"Небезопасные artifact paths: {exc}")
        checks.append({"name": "artifact_path_safety", "status": "failed", "detail": str(exc)})

    try:
        temp_dir = get_temp_dir(
            seller_id=seller_id,
            cabinet_id=seller.cabinet_id,
            mode=mode,
            temp_root=settings.temp_root,
        )
        temp_dir.mkdir(parents=True, exist_ok=True)
        checks.append(
            {
                "name": "temp_dir_access",
                "status": "ok",
                "detail": str(path_label(temp_dir) or temp_dir),
            }
        )
    except Exception as exc:
        errors.append(f"Не удалось подготовить temp_dir: {exc}")
        checks.append({"name": "temp_dir_access", "status": "failed", "detail": str(exc)})

    ok = not errors
    return {
        "ok": ok,
        "status": "SUCCESS" if ok else "FAILED",
        "mode": mode,
        "seller_id": seller_id,
        "run_date": run_date,
        "dry_run": dry_run,
        "resolved_output_dir": str(output_dir),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "feature_flags": feature_flags,
        "production_preview": production_preview,
    }


__all__ = ["run"]
