"""Delivery stage for v4 pipeline.

Input: outputs payload dictionary from outputs stage.
Output: delivery artifact paths + delivery diagnostics.
Does not access metrics/facts/decisions directly and does not recompute KPI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...delivery.email.sender import save_email_preview, send_email_via_smtp
from ...delivery.pdf.renderer import render_pdf
from ...outputs.email.contracts import EmailPayload
from ...outputs.pdf.contracts import PdfPayload


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _normalize_mode(outputs: dict[str, Any]) -> str | None:
    pdf_payload = outputs.get("pdf")
    if isinstance(pdf_payload, PdfPayload):
        return "audit" if str(pdf_payload.mode).strip().lower() == "audit" else "daily"
    email_payload = outputs.get("email")
    if isinstance(email_payload, EmailPayload):
        return "audit" if str(email_payload.mode).strip().lower() == "audit" else "daily"
    return None


def run_delivery_stage(
    outputs: dict,
    output_dir: str | None = None,
    enable_pdf_render: bool = True,
    enable_email_preview: bool = True,
    enable_email_send: bool = False,
) -> dict:
    if not isinstance(outputs, dict):
        raise TypeError("run_delivery_stage expects outputs dict")

    pdf_path: str | None = None
    email_preview_path: str | None = None
    email_send: dict[str, Any] | None = None
    email_sent = False
    email_send_attempted = False
    warnings: list[str] = []

    artifacts = outputs.get("artifacts", {}) if isinstance(outputs.get("artifacts"), dict) else {}
    artifact_saved_files = artifacts.get("saved_files", {}) if isinstance(artifacts, dict) else {}

    root: Path | None = None
    if output_dir is not None:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)

    pdf_payload = outputs.get("pdf")
    if enable_pdf_render:
        if not isinstance(pdf_payload, PdfPayload):
            warnings.append("pdf payload is missing or invalid; PDF rendering skipped")
        elif root is None:
            warnings.append("output_dir is not set; PDF rendering skipped")
        else:
            target = root / "report.pdf"
            rendered = Path(render_pdf(pdf_payload, target))
            if not _is_within(root, rendered):
                warnings.append(f"rendered PDF path is outside output_dir: {rendered}")
            elif not rendered.exists():
                warnings.append(f"rendered PDF path does not exist: {rendered}")
            else:
                pdf_path = str(rendered)

    email_payload = outputs.get("email")
    if enable_email_preview:
        if not isinstance(email_payload, EmailPayload):
            warnings.append("email payload is missing or invalid; email preview skipped")
        elif root is None:
            warnings.append("output_dir is not set; email preview skipped")
        else:
            attachments: list[str] = []
            if pdf_path:
                attachments.append(pdf_path)
            preview = Path(save_email_preview(email_payload, root, attachments=attachments))
            if not _is_within(root, preview):
                warnings.append(f"email preview path is outside output_dir: {preview}")
            elif not preview.exists():
                warnings.append(f"email preview path does not exist: {preview}")
            else:
                email_preview_path = str(preview)

    if enable_email_send:
        email_send_attempted = True
        if not isinstance(email_payload, EmailPayload):
            warnings.append("email payload is missing or invalid; SMTP send skipped")
        elif pdf_path is None:
            warnings.append("rendered PDF is missing; SMTP send skipped")
        else:
            try:
                email_send = send_email_via_smtp(
                    email_payload,
                    pdf_path=pdf_path,
                )
                email_sent = True
            except Exception as exc:
                warnings.append(f"email send failed: {exc}")
                email_send = {
                    "email_transport_status": "failed",
                    "email_failure_reason_normalized": str(exc),
                }

    diagnostics = {
        "mode": _normalize_mode(outputs),
        "delivery_enabled": bool(enable_pdf_render or enable_email_preview),
        "rendered_pdf": bool(pdf_path),
        "email_preview_built": bool(email_preview_path),
        "email_send_attempted": bool(email_send_attempted),
        "email_sent": bool(email_sent),
        "email_send": dict(email_send) if isinstance(email_send, dict) else None,
        "output_dir": str(root) if root is not None else None,
        "output_paths": {
            "pdf_path": pdf_path,
            "email_preview_path": email_preview_path,
        },
        "artifacts_available": sorted(str(key) for key in artifact_saved_files.keys()),
        "warnings": warnings,
    }

    return {
        "pdf_path": pdf_path,
        "email_preview_path": email_preview_path,
        "email_send": email_send,
        "diagnostics": diagnostics,
    }


__all__ = ["run_delivery_stage"]
