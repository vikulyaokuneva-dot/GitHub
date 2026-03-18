"""Audit file-ingestion bundle builder.

Input: input path and RunContext.
Output: IngestionResult with raw FILE sources for normalize stage.
Does not compute KPI.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from ...core.contracts import (
    IngestionResult,
    RawBundle,
    RawSourcePayload,
    RunContext,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from ...pipeline.modes.audit_file_mode import get_audit_mode_flags
from .ads_report import parse as parse_ads_report
from .daily_report import parse as parse_daily_report
from .funnel_report import parse as parse_funnel_report
from .registry import classify_input_files, get_optional_file_inputs, get_required_file_inputs
from .zip_loader import extract as extract_zip


RAW_SOURCES: tuple[str, ...] = ("orders", "sales", "realization", "stocks", "funnel", "ads")
REQUIRED_RAW_SOURCES: tuple[str, ...] = ("realization",)


def _status(
    *,
    source_name: str,
    status: SourceStatusCode,
    is_required: bool,
    run_context: RunContext,
    warnings: list[str] | None = None,
    debug: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    rows_loaded: int | None = None,
) -> SourceStatus:
    return SourceStatus(
        source_name=source_name,
        kind=SourceKind.FILE,
        status=status,
        is_required=is_required,
        rows_loaded=rows_loaded,
        requested_date=run_context.requested_date_iso,
        resolved_date=run_context.resolved_date_iso,
        warnings=list(warnings or []),
        debug=dict(debug or {}),
        error_code=error_code,
        error_message=error_message,
    )


def _payload(source_name: str, payload: Any, status: SourceStatus) -> RawSourcePayload:
    return RawSourcePayload(source_name=source_name, payload=payload, status=status)


def _discover_files(input_path: Path, extraction_root: Path) -> tuple[list[Path], list[str]]:
    if not input_path.exists():
        return [], [f"input path does not exist: {input_path}"]

    errors: list[str] = []
    files: list[Path] = []

    if input_path.is_file():
        if input_path.suffix.lower() == ".zip":
            extraction = extract_zip(str(input_path), str(extraction_root / input_path.stem))
            errors.extend(list(extraction.get("errors", [])))
            files.extend([Path(path) for path in extraction.get("files", [])])
        else:
            files.append(input_path)
    else:
        for path in input_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".zip":
                extraction = extract_zip(str(path), str(extraction_root / path.stem))
                errors.extend(list(extraction.get("errors", [])))
                files.extend([Path(item) for item in extraction.get("files", [])])
            else:
                files.append(path)

    out: list[Path] = []
    for file in files:
        try:
            resolved = file.resolve()
        except Exception:
            continue
        if resolved.exists():
            out.append(resolved)
    return out, errors


def build_file_raw_bundle(input_path: str | Path, run_context: RunContext) -> IngestionResult:
    path = Path(input_path)

    with tempfile.TemporaryDirectory(prefix="v4_audit_ingestion_") as temp_dir:
        discovered_files, file_errors = _discover_files(path, Path(temp_dir))
        selected_files = classify_input_files(discovered_files)

        warnings: list[str] = list(file_errors)
        sources: dict[str, RawSourcePayload] = {}

        for source_name in RAW_SOURCES:
            is_required = source_name in REQUIRED_RAW_SOURCES
            sources[source_name] = _payload(
                source_name,
                {"rows": []}
                if source_name != "ads"
                else {"campaigns": {"raw": []}, "stats": {"rows": []}, "campaign_ids": []},
                _status(
                    source_name=source_name,
                    status=SourceStatusCode.MISSING,
                    is_required=is_required,
                    run_context=run_context,
                    warnings=["source missing in audit file inputs"],
                ),
            )

        file_source_flags: dict[str, str] = {}
        detected_files: dict[str, str] = {}

        daily_file = selected_files.get("daily_report")
        if daily_file is not None:
            payload, daily_status = parse_daily_report(str(daily_file))
            file_source_flags["daily_report"] = daily_status.status.value
            detected_files["daily_report"] = str(daily_file)

            realization_rows = payload.get("rows", []) if isinstance(payload, dict) else []
            sales_rows = payload.get("sales_rows", []) if isinstance(payload, dict) else []
            orders_rows = payload.get("orders_rows", []) if isinstance(payload, dict) else []
            stocks_rows = payload.get("stocks_rows", []) if isinstance(payload, dict) else []

            status_realization = SourceStatusCode.OK if realization_rows else SourceStatusCode.MISSING
            if daily_status.status == SourceStatusCode.PARTIAL:
                status_realization = SourceStatusCode.PARTIAL
            sources["realization"] = _payload(
                "realization",
                {"rows": realization_rows},
                _status(
                    source_name="realization",
                    status=status_realization,
                    is_required=True,
                    run_context=run_context,
                    rows_loaded=len(realization_rows) if realization_rows else None,
                    warnings=list(daily_status.warnings),
                    debug=dict(daily_status.debug),
                ),
            )

            status_sales = SourceStatusCode.OK if sales_rows else SourceStatusCode.MISSING
            if sales_rows and daily_status.status == SourceStatusCode.PARTIAL:
                status_sales = SourceStatusCode.PARTIAL
            sources["sales"] = _payload(
                "sales",
                {"rows": sales_rows},
                _status(
                    source_name="sales",
                    status=status_sales,
                    is_required=False,
                    run_context=run_context,
                    rows_loaded=len(sales_rows) if sales_rows else None,
                    warnings=[] if sales_rows else ["no derived sales rows from daily report"],
                    debug={"source_file": str(daily_file)},
                ),
            )

            status_orders = SourceStatusCode.OK if orders_rows else SourceStatusCode.MISSING
            if orders_rows and daily_status.status == SourceStatusCode.PARTIAL:
                status_orders = SourceStatusCode.PARTIAL
            sources["orders"] = _payload(
                "orders",
                {"rows": orders_rows},
                _status(
                    source_name="orders",
                    status=status_orders,
                    is_required=False,
                    run_context=run_context,
                    rows_loaded=len(orders_rows) if orders_rows else None,
                    warnings=[] if orders_rows else ["no derived orders rows from daily report"],
                    debug={"source_file": str(daily_file)},
                ),
            )

            if stocks_rows:
                sources["stocks"] = _payload(
                    "stocks",
                    {"rows": stocks_rows},
                    _status(
                        source_name="stocks",
                        status=SourceStatusCode.PARTIAL if daily_status.status == SourceStatusCode.PARTIAL else SourceStatusCode.OK,
                        is_required=False,
                        run_context=run_context,
                        rows_loaded=len(stocks_rows),
                        warnings=[],
                        debug={"source_file": str(daily_file)},
                    ),
                )
        else:
            file_source_flags["daily_report"] = SourceStatusCode.MISSING.value
            warnings.append("daily_report file is missing in audit inputs")

        funnel_file = selected_files.get("funnel_report")
        if funnel_file is not None:
            payload, funnel_status = parse_funnel_report(str(funnel_file))
            file_source_flags["funnel_report"] = funnel_status.status.value
            detected_files["funnel_report"] = str(funnel_file)
            rows = payload.get("rows", []) if isinstance(payload, dict) else []
            sources["funnel"] = _payload(
                "funnel",
                {"rows": rows},
                _status(
                    source_name="funnel",
                    status=funnel_status.status if rows else SourceStatusCode.MISSING,
                    is_required=False,
                    run_context=run_context,
                    rows_loaded=len(rows) if rows else None,
                    warnings=list(funnel_status.warnings),
                    debug=dict(funnel_status.debug),
                ),
            )
        else:
            file_source_flags["funnel_report"] = SourceStatusCode.MISSING.value

        ads_file = selected_files.get("ads_report")
        if ads_file is not None:
            payload, ads_status = parse_ads_report(str(ads_file))
            file_source_flags["ads_report"] = ads_status.status.value
            detected_files["ads_report"] = str(ads_file)
            sources["ads"] = _payload(
                "ads",
                payload,
                _status(
                    source_name="ads",
                    status=ads_status.status,
                    is_required=False,
                    run_context=run_context,
                    rows_loaded=ads_status.rows_loaded,
                    warnings=list(ads_status.warnings),
                    debug=dict(ads_status.debug),
                ),
            )
        else:
            file_source_flags["ads_report"] = SourceStatusCode.MISSING.value

        required_files = set(get_required_file_inputs())
        optional_files = set(get_optional_file_inputs())
        missing_expected_files = [
            name
            for name in [*sorted(required_files), *sorted(optional_files)]
            if file_source_flags.get(name) not in {SourceStatusCode.OK.value, SourceStatusCode.PARTIAL.value}
        ]

        source_flags = {source_name: payload.status.status for source_name, payload in sources.items()}
        diagnostics = {
            "mode": run_context.mode.value,
            "input_path": str(path),
            "scanned_files": [str(file) for file in discovered_files],
            "detected_files": detected_files,
            "file_source_flags": file_source_flags,
            "missing_expected_files": missing_expected_files,
            "audit_mode_flags": get_audit_mode_flags(),
            "warnings_count": len(warnings),
        }

        raw_bundle = RawBundle(run_context=run_context, sources=sources, diagnostics=diagnostics)
        ingestion_warnings = list(warnings)
        for source in sources.values():
            ingestion_warnings.extend([f"{source.source_name}: {warning}" for warning in source.status.warnings])

        seen: set[str] = set()
        deduped: list[str] = []
        for warning in ingestion_warnings:
            text = str(warning)
            if text in seen:
                continue
            seen.add(text)
            deduped.append(text)

        return IngestionResult(raw_bundle=raw_bundle, source_flags=source_flags, warnings=deduped)
