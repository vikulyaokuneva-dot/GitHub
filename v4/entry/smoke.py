"""Operator smoke flow for safe local validation.

Smoke executes preflight + dry-run pipeline and returns deterministic status.
"""

from __future__ import annotations

from typing import Any

from . import audit as audit_entry
from . import daily as daily_entry
from .preflight import run as run_preflight


def _normalize_mode(value: object) -> str:
    text = str(value or "daily").strip().lower()
    if text == "audit":
        return "audit"
    return "daily"


def _warnings_count(result: dict[str, Any]) -> int:
    warnings = result.get("warnings", [])
    if isinstance(warnings, list):
        return len(warnings)
    return 0


def run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    mode = _normalize_mode(data.get("mode"))
    steps: list[dict[str, str]] = []

    preflight_payload = dict(data)
    preflight_payload["mode"] = mode
    preflight_payload["dry_run"] = True
    preflight = run_preflight(preflight_payload)
    if not preflight.get("ok", False):
        steps.append({"name": "preflight", "status": "failed"})
        return {
            "status": "FAILED",
            "mode": mode,
            "dry_run": True,
            "steps": steps,
            "preflight": preflight,
            "run_result": None,
            "error": "preflight failed",
        }
    steps.append({"name": "preflight", "status": "ok"})

    run_payload = dict(data)
    run_payload["dry_run"] = True
    run_payload["output_dir"] = preflight.get("resolved_output_dir")
    run_payload["mode"] = mode

    try:
        if mode == "audit":
            result = audit_entry.run(run_payload)
        else:
            result = daily_entry.run(run_payload)
    except Exception as exc:
        steps.append({"name": "pipeline", "status": "failed"})
        return {
            "status": "FAILED",
            "mode": mode,
            "dry_run": True,
            "steps": steps,
            "preflight": preflight,
            "run_result": None,
            "error": str(exc),
        }

    steps.append({"name": "pipeline", "status": "ok"})
    diagnostics = result.get("diagnostics", {}) if isinstance(result, dict) else {}
    summary = diagnostics.get("summary", {}) if isinstance(diagnostics, dict) else {}

    return {
        "status": "SUCCESS",
        "mode": mode,
        "dry_run": True,
        "steps": steps,
        "preflight": preflight,
        "run_result": result,
        "summary": {
            "partial_flag": bool(summary.get("partial_flag", False)),
            "warnings_count": _warnings_count(result),
            "output_dir_label": summary.get("output_dir_label"),
        },
    }


__all__ = ["run"]

