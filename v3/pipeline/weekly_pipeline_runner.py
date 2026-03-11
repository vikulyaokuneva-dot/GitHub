from __future__ import annotations

from typing import Any, Dict

_IMPORTED_FROM_ENTRY = False


def _sync_from_entry() -> None:
    global _IMPORTED_FROM_ENTRY
    if _IMPORTED_FROM_ENTRY:
        return
    from .. import entry as E

    for key, value in E.__dict__.items():
        if key.startswith("__"):
            continue
        if key in globals():
            continue
        globals()[key] = value
    _IMPORTED_FROM_ENTRY = True


def _run_weekly_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    cabinet_root(repo_root, seller_id, create=True)
    out_dir = artifacts_dir(repo_root, seller_id, create=True)
    history_dir = Path(repo_root) / "cabinets" / seller_id / "history"

    started_at = _utc_now_iso()
    weekly_data = build_weekly_intelligence(
        seller_id=seller_id,
        history_dir=history_dir,
        run_date=run_date,
    )
    weekly_path = save_weekly_intelligence(
        seller_id=seller_id,
        artifacts_dir=Path(out_dir),
        data=weekly_data,
    )
    trend_data = build_trend_anomalies(
        seller_id=seller_id,
        run_date=run_date,
        history_dir=history_dir,
    )
    trend_path = save_trend_anomalies(
        artifacts_dir=Path(out_dir),
        data=trend_data,
    )

    snapshots_used = int(weekly_data.get("snapshots_used", 0) or 0)
    anomaly_snapshots_used = int(trend_data.get("snapshots_used", 0) or 0)
    warnings_collector = WarningsCollector()
    warnings_collector.add_warning(
        "weekly_intelligence_built",
        f"Weekly intelligence built from {snapshots_used} snapshots",
    )
    warnings_collector.add_warning(
        "trend_anomalies_built",
        f"Trend anomalies built from {anomaly_snapshots_used} snapshots",
    )
    if snapshots_used < 7:
        warnings_collector.add_warning(
            "insufficient_history_for_full_weekly",
            f"Only {snapshots_used} snapshots available; full 7-day analysis is limited",
        )
    if anomaly_snapshots_used < 3:
        warnings_collector.add_warning(
            "insufficient_history_for_anomaly_detection",
            f"Only {anomaly_snapshots_used} snapshots available; anomaly detection is limited",
        )

    kpi_trends = weekly_data.get("kpi_trends", {}) if isinstance(weekly_data, dict) else {}
    if not isinstance(kpi_trends, dict):
        kpi_trends = {}
    anomaly_summary = trend_data.get("summary", {}) if isinstance(trend_data, dict) else {}
    if not isinstance(anomaly_summary, dict):
        anomaly_summary = {}

    weekly_facts = {
        "seller_id": seller_id,
        "run_date": run_date,
        "window_days": int(weekly_data.get("window_days", 7) or 7),
        "snapshots_used": snapshots_used,
        "weekly_summary": {
            "revenue_delta_pct": (kpi_trends.get("revenue") or {}).get("delta_pct"),
            "profit_delta_pct": (kpi_trends.get("profit") or {}).get("delta_pct"),
            "buyouts_delta_pct": (kpi_trends.get("buyouts") or {}).get("delta_pct"),
        },
        "anomaly_summary": {
            "total_anomalies": int(anomaly_summary.get("total_anomalies", 0) or 0),
            "high": int(anomaly_summary.get("high", 0) or 0),
            "medium": int(anomaly_summary.get("medium", 0) or 0),
            "low": int(anomaly_summary.get("low", 0) or 0),
        },
    }

    write_weekly_facts_and_warnings(
        out_dir=out_dir,
        weekly_facts=weekly_facts,
        warnings=warnings_collector.export_warnings(),
    )

    sku_trends = weekly_data.get("sku_trends", {}) if isinstance(weekly_data, dict) else {}
    if not isinstance(sku_trends, dict):
        sku_trends = {}
    growing = sku_trends.get("growing", [])
    declining = sku_trends.get("declining", [])
    if not isinstance(growing, list):
        growing = []
    if not isinstance(declining, list):
        declining = []

    weekly_pdf_lines: List[str] = [
        "# НЕДЕЛЬНЫЙ ОТЧЕТ",
        f"### Кабинет: {seller_id}",
        f"### Дата: {run_date}",
        f"### Период анализа: {weekly_data.get('window_days', 7)} дней",
        f"### Использовано snapshot: {snapshots_used}",
        "",
        "## ТЕНДЕНЦИИ KPI",
        "KPI | Начало | Текущее | Изменение | Изменение %",
    ]

    weekly_kpi_labels = {
        "revenue": "Выручка",
        "profit": "Прибыль",
        "buyouts": "Выкупы",
        "ads_spend": "Реклама",
        "sku_count": "SKU",
    }
    for key in ("revenue", "profit", "buyouts", "ads_spend", "sku_count"):
        row = kpi_trends.get(key, {})
        if not isinstance(row, dict):
            row = {}
        weekly_pdf_lines.append(
            f"{weekly_kpi_labels.get(key, key)} | {row.get('start', 0)} | {row.get('current', 0)} | {row.get('delta', 0)} | {row.get('delta_pct', None)}"
        )

    weekly_pdf_lines.extend(["", "## РАСТУЩИЕ SKU"])
    if growing:
        for item in growing[:10]:
            if not isinstance(item, dict):
                continue
            weekly_pdf_lines.append(
                f"- SKU {item.get('sku', 'н/д')} | изменение прибыли {item.get('profit_delta', 0)}"
            )
    else:
        weekly_pdf_lines.append("- нет")

    weekly_pdf_lines.extend(["", "## СНИЖАЮЩИЕСЯ SKU"])
    if declining:
        for item in declining[:10]:
            if not isinstance(item, dict):
                continue
            weekly_pdf_lines.append(
                f"- SKU {item.get('sku', 'н/д')} | изменение прибыли {item.get('profit_delta', 0)}"
            )
    else:
        weekly_pdf_lines.append("- нет")

    weekly_pdf_lines.extend(["", "## НЕДЕЛЬНЫЕ ВЫВОДЫ AI"])
    insights = weekly_data.get("insights", []) if isinstance(weekly_data, dict) else []
    if isinstance(insights, list) and insights:
        for insight in insights[:8]:
            weekly_pdf_lines.append(f"- {insight}")
    else:
        weekly_pdf_lines.append("- Недостаточно данных для недельных выводов.")

    kpi_anomalies = trend_data.get("kpi_anomalies", []) if isinstance(trend_data, dict) else []
    sku_anomalies = trend_data.get("sku_anomalies", []) if isinstance(trend_data, dict) else []
    if not isinstance(kpi_anomalies, list):
        kpi_anomalies = []
    if not isinstance(sku_anomalies, list):
        sku_anomalies = []
    combined_anomalies = [x for x in (kpi_anomalies + sku_anomalies) if isinstance(x, dict)]
    severity_order = {"high": 0, "medium": 1, "low": 2}
    combined_anomalies.sort(
        key=lambda x: (
            severity_order.get(str(x.get("severity") or "").lower(), 3),
            str(x.get("metric") or x.get("sku") or ""),
            str(x.get("type") or ""),
        )
    )

    weekly_pdf_lines.extend(["", "## АНОМАЛИИ И РИСКИ"])
    if not combined_anomalies:
        weekly_pdf_lines.append("- Значимых аномалий не обнаружено")
    else:
        for severity in ("high", "medium", "low"):
            rows = [x for x in combined_anomalies if str(x.get("severity") or "").lower() == severity]
            if not rows:
                continue
            for row in rows:
                level = severity.upper()
                message = str(row.get("message") or "Обнаружена аномалия.")
                sku = str(row.get("sku") or "").strip()
                if sku:
                    weekly_pdf_lines.append(f"- [{level}] SKU {sku}: {message}")
                else:
                    weekly_pdf_lines.append(f"- [{level}] {message}")

    write_text_pdf(os.path.join(out_dir, "weekly_report.pdf"), weekly_pdf_lines)

    job = build_weekly_job(
        seller_id=seller_id,
        run_date=run_date,
        started_at=started_at,
        finished_at=_utc_now_iso(),
        out_dir=out_dir,
        weekly_path=str(weekly_path),
        trend_path=str(trend_path),
        snapshots_used=int(snapshots_used),
    )
    write_job(out_dir=out_dir, job=job)
    return job




def run_weekly_pipeline_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    _sync_from_entry()
    return _run_weekly_for_seller(repo_root, seller_id, run_date)
