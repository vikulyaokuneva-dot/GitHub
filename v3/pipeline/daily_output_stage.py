from __future__ import annotations

from typing import Any, Dict

from ..outputs.daily_artifacts_stage import prepare_daily_output_payload
from ..outputs.daily_email_stage import run_daily_email_stage
from ..outputs.daily_history_stage import run_daily_history_stage
from ..outputs.daily_report_stage import run_daily_report_stage


def run_daily_output_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    payload = prepare_daily_output_payload(context)
    payload = run_daily_email_stage(payload)
    payload = run_daily_report_stage(payload)
    return run_daily_history_stage(payload)
