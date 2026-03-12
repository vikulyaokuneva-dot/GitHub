from __future__ import annotations

from typing import Any, Dict, List

from .job_payload_builder import build_daily_job_payload
from .run_summary_builder import build_run_summary


def _daily_artifacts(run_date: str) -> List[str]:
    return [
        "job.json",
        "facts.json",
        "metrics.json",
        "cabinet_funnel.json",
        "sku_daily_dynamics.json",
        "sku_alerts.json",
        "sku_watchlists.json",
        "event_ledger.json",
        "api_debug.json",
        "financial_debug.json",
        "warnings.json",
        "abc_analysis.json",
        "profit_contribution.json",
        "territorial_distribution.json",
        "logistics_ktr.json",
        "health_score.json",
        "decisions.json",
        "growth_simulation.json",
        "opportunity_scores.json",
        "director_strategy.json",
        "memory/decision_memory.jsonl",
        f"memory/outcomes/{run_date}_outcomes.json",
        f"history/daily/{run_date}/",
        "history/history_index.json",
        "report_meta.json",
        "report.pdf",
    ]


def build_daily_job(
    *,
    seller_id: str,
    run_date: str,
    started_at: str,
    finished_at: str,
    source_mode: str,
    out_dir: str,
    financial_data_missing_flag: bool,
    facts_financial_status: str,
    financial_kpi: Dict[str, Any],
    input_debug: Dict[str, Any],
    api_debug: Dict[str, Any],
    daily_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    ads_rows_count: int,
    ads_loaded_from_file: bool,
    ads_source_file: str,
    ads_attribution_quality: str,
    data_source_orders_count: str,
    data_source_buyouts_count: str,
    data_source_orders_amount: str,
    data_source_buyouts_amount: str,
    data_source_revenue: str,
    data_source_wb_commission: str,
    data_source_logistics: str,
    data_source_storage: str,
    data_source_ads_spend: str,
    source_flags: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        **build_run_summary(
            seller_id=seller_id,
            mode="daily",
            run_date=run_date,
            started_at=started_at,
            finished_at=finished_at,
            source_mode=source_mode,
            artifacts_dir=out_dir,
            financial_data_missing_flag=bool(financial_data_missing_flag),
            facts_financial_status=str(facts_financial_status or ""),
            financial_partial=bool((financial_kpi if isinstance(financial_kpi, dict) else {}).get("is_partial", False)),
            data_quality=str(facts_financial_status or ""),
            artifacts=_daily_artifacts(run_date),
        ),
        **build_daily_job_payload(
            input_debug=input_debug if isinstance(input_debug, dict) else {},
            api_debug=api_debug if isinstance(api_debug, dict) else {},
            daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
            ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
            ads_rows_count=int(ads_rows_count),
            financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
            ads_loaded_from_file=bool(ads_loaded_from_file),
            ads_source_file=str(ads_source_file or ""),
            ads_attribution_quality=str(ads_attribution_quality or "unknown"),
            data_source_orders_count=str(data_source_orders_count),
            data_source_buyouts_count=str(data_source_buyouts_count),
            data_source_orders_amount=str(data_source_orders_amount),
            data_source_buyouts_amount=str(data_source_buyouts_amount),
            data_source_revenue=str(data_source_revenue),
            data_source_wb_commission=str(data_source_wb_commission),
            data_source_logistics=str(data_source_logistics),
            data_source_storage=str(data_source_storage),
            data_source_ads_spend=str(data_source_ads_spend),
            source_flags=source_flags if isinstance(source_flags, dict) else {},
            facts_financial_status=str(facts_financial_status or ""),
            metrics=metrics if isinstance(metrics, dict) else {},
        ),
    }


def apply_job_email_result(
    *,
    job: Dict[str, Any],
    attempted: bool,
    sent: bool,
    email_to: str,
    error: str | None,
) -> Dict[str, Any]:
    safe_job = dict(job if isinstance(job, dict) else {})
    summary_patch = build_run_summary(
        seller_id=str(safe_job.get("seller_id") or ""),
        mode=str(safe_job.get("mode") or ""),
        run_date=str(safe_job.get("run_date") or ""),
        started_at=str(safe_job.get("started_at") or ""),
        finished_at=str(safe_job.get("finished_at") or ""),
        source_mode=str(safe_job.get("source_mode") or "") if "source_mode" in safe_job else None,
        artifacts_dir=str(safe_job.get("artifacts_dir") or ""),
        status=str(safe_job.get("status") or ""),
        error=safe_job.get("error") if isinstance(safe_job.get("error"), str) or safe_job.get("error") is None else str(safe_job.get("error")),
        financial_partial=bool(safe_job.get("financial_partial", False)) if "financial_partial" in safe_job else None,
        data_quality=str(safe_job.get("data_quality")) if safe_job.get("data_quality") is not None else None,
        artifacts=safe_job.get("artifacts") if isinstance(safe_job.get("artifacts"), list) else None,
        email_attempted=bool(attempted),
        email_sent=bool(sent),
        email_to=str(email_to or ""),
        email_error=error,
    )
    safe_job.update(summary_patch)
    return safe_job


def attach_daily_job_decision_outcomes(
    job: Dict[str, Any],
    *,
    decision_rows_added: int,
    outcomes_evaluated: int,
    outcomes_file: str,
) -> Dict[str, Any]:
    out = dict(job if isinstance(job, dict) else {})
    out["decision_memory_added"] = int(decision_rows_added)
    out["decision_outcomes_evaluated"] = int(outcomes_evaluated)
    out["decision_outcomes_file"] = str(outcomes_file or "")
    return out


def attach_daily_job_history(
    job: Dict[str, Any],
    *,
    run_date: str,
    history_snapshot_final: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(job if isinstance(job, dict) else {})
    safe_snapshot = history_snapshot_final if isinstance(history_snapshot_final, dict) else {}
    out["history_snapshot"] = {
        "date": run_date,
        "path": str(safe_snapshot.get("snapshot_path", "")),
        "files": safe_snapshot.get("files", []),
    }
    return out


def attach_job_warnings(job: Dict[str, Any], warnings: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(job if isinstance(job, dict) else {})
    out["warnings"] = [item for item in warnings if isinstance(item, dict)]
    return out


def build_weekly_job(
    *,
    seller_id: str,
    run_date: str,
    started_at: str,
    finished_at: str,
    out_dir: str,
    weekly_path: str,
    trend_path: str,
    snapshots_used: int,
) -> Dict[str, Any]:
    return {
        **build_run_summary(
            seller_id=seller_id,
            mode="weekly",
            run_date=run_date,
            started_at=started_at,
            finished_at=finished_at,
            artifacts_dir=out_dir,
            status="success",
            error=None,
            artifacts=[
                "job.json",
                "weekly_intelligence.json",
                "trend_anomalies.json",
                "weekly_facts.json",
                "warnings.json",
                "weekly_report.pdf",
            ],
        ),
        "weekly_intelligence_path": str(weekly_path or ""),
        "trend_anomalies_path": str(trend_path or ""),
        "snapshots_used": int(snapshots_used),
    }
