from __future__ import annotations

from typing import Any, Dict

from ..outputs.daily_artifacts_stage import prepare_daily_output_payload
from ..outputs.daily_email_stage import run_daily_email_stage
from ..outputs.daily_history_stage import run_daily_history_stage
from ..outputs.daily_report_stage import run_daily_report_stage


def run_daily_output_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    context_payload: Dict[str, Any] = dict(context or {})
    event_date_model = context_payload.get("event_date_model", {})
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    print(
        "[daily_output_stage] before_prepare "
        f"caller=run_daily_output_stage "
        f"seller_id={str(context_payload.get('seller_id') or '<empty>')} "
        f"run_date={str(context_payload.get('run_date') or '<empty>')} "
        f"operational_date={str(event_date_model.get('operational_date') or context_payload.get('run_date') or '<empty>')} "
        f"source_mode={str(context_payload.get('source_mode') or '<empty>')} "
        f"pdf_source_mode={str(context_payload.get('pdf_source_mode') or '<empty>')}"
    )
    payload = prepare_daily_output_payload(context_payload)
    print(
        "[daily_output_stage] after_prepare "
        f"source_mode={str(payload.get('source_mode') or '<empty>')} "
        f"pdf_source_mode={str(payload.get('pdf_source_mode') or '<empty>')} "
        f"core_report_payload_available={str(isinstance(payload.get('core_report_payload'), dict)).lower()}"
    )
    payload = run_daily_email_stage(payload)
    print(
        "[daily_output_stage] after_email "
        f"source_mode={str(payload.get('source_mode') or '<empty>')} "
        f"pdf_source_mode={str(payload.get('pdf_source_mode') or '<empty>')} "
        f"core_report_payload_available={str(isinstance(payload.get('core_report_payload'), dict)).lower()}"
    )
    payload = run_daily_report_stage(payload)
    report_meta = payload.get("report_meta", {})
    if not isinstance(report_meta, dict):
        report_meta = {}
    print(
        "[daily_output_stage] after_report "
        f"source_mode={str(payload.get('source_mode') or '<empty>')} "
        f"pdf_source_mode={str(payload.get('pdf_source_mode') or '<empty>')} "
        f"core_report_payload_available={str(isinstance(payload.get('core_report_payload'), dict)).lower()} "
        f"report_meta_source_mode={str(report_meta.get('source_mode') or '<empty>')} "
        f"report_meta_pdf_source_mode={str(report_meta.get('pdf_source_mode') or '<empty>')} "
        f"report_meta_core_report_payload_available={str(bool(report_meta.get('core_report_payload_available', False))).lower()}"
    )
    return run_daily_history_stage(payload)
