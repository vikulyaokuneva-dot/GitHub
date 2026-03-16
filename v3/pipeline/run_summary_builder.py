from __future__ import annotations

from typing import Any, Dict, List


def build_run_summary(
    *,
    seller_id: str,
    mode: str,
    run_date: str,
    started_at: str,
    finished_at: str,
    source_mode: str | None = None,
    artifacts_dir: str = "",
    financial_data_missing_flag: bool = False,
    facts_financial_status: str = "",
    status: str | None = None,
    error: str | None = None,
    financial_partial: bool | None = None,
    data_quality: str | None = None,
    artifacts: List[str] | None = None,
    email_attempted: bool | None = None,
    email_sent: bool | None = None,
    email_to: str | None = None,
    email_error: str | None = None,
    email_stage: str | None = None,
    email_transport_status: str | None = None,
    email_failure_reason_normalized: str | None = None,
) -> Dict[str, Any]:
    resolved_status = str(status or "").strip()
    if not resolved_status:
        resolved_status = "partial_success" if (financial_data_missing_flag or facts_financial_status == "partial") else "success"

    resolved_error: str | None = error
    if resolved_error is None and not str(status or "").strip():
        resolved_error = (
            "данные о продажах не получены"
            if financial_data_missing_flag
            else ("финансовая атрибуция частичная" if facts_financial_status == "partial" else None)
        )

    summary: Dict[str, Any] = {
        "seller_id": seller_id,
        "mode": mode,
        "run_date": run_date,
        "status": resolved_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "error": resolved_error,
        "artifacts_dir": artifacts_dir,
    }
    if source_mode is not None:
        summary["source_mode"] = str(source_mode)
    if financial_partial is not None:
        summary["financial_partial"] = bool(financial_partial)
    if data_quality is not None:
        summary["data_quality"] = str(data_quality)
    if isinstance(artifacts, list):
        summary["artifacts"] = [str(item) for item in artifacts]
    if email_attempted is not None:
        summary["email_attempted"] = bool(email_attempted)
        summary["email_sent"] = bool(email_sent)
        summary["email_to"] = str(email_to or "")
        summary["email_error"] = email_error
        summary["email_stage"] = str(email_stage or "unknown")
        summary["email_transport_status"] = str(
            email_transport_status or ("success" if bool(email_sent) else ("failed" if bool(email_attempted) else "skipped"))
        )
        summary["email_failure_reason_normalized"] = str(email_failure_reason_normalized or "")

    return summary
