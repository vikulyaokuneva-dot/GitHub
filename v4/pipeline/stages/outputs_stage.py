"""Outputs stage for v4 pipeline.

Input: FactsBundle + DecisionsBundle.
Output: artifacts/email/pdf payloads.
Does not send email and does not render final PDF binary.
"""

from __future__ import annotations

from ...core.contracts import DecisionsBundle, FactsBundle
from ...outputs.artifacts.writer import build_artifact_payloads, save_artifact_payloads
from ...outputs.email.builder import build_email_payload
from ...outputs.email.contracts import EmailPayload
from ...outputs.pdf.builder import build_pdf_payload
from ...outputs.pdf.contracts import PdfPayload


def run(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
    output_dir: str | None = None,
) -> dict:
    artifacts_payloads = build_artifact_payloads(facts_bundle, decisions_bundle)
    saved_files: dict[str, str] = {}
    if output_dir:
        saved_files = save_artifact_payloads(artifacts_payloads, output_dir)

    email_payload: EmailPayload = build_email_payload(
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        mode=mode,
    )
    pdf_payload: PdfPayload = build_pdf_payload(
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        mode=mode,
    )

    diagnostics = {
        "mode": mode,
        "artifact_keys": list(artifacts_payloads.keys()),
        "artifacts_saved": bool(saved_files),
        "saved_files_count": len(saved_files),
        "email_sections_count": len(email_payload.sections),
        "pdf_pages_count": len(pdf_payload.pages),
    }

    return {
        "artifacts": {
            "payloads": artifacts_payloads,
            "saved_files": saved_files,
        },
        "email": email_payload,
        "pdf": pdf_payload,
        "diagnostics": diagnostics,
    }

