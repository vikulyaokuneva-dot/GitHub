"""Input stage for v4 pipeline.

Input: RunContext.
Output: IngestionResult (raw layer only).
Does not normalize and does not compute metrics.
"""

from __future__ import annotations

from ..modes.audit_file_mode import MODE_DESCRIPTOR as AUDIT_MODE
from ..modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE
from ...core.contracts import (
    IngestionResult,
    RawBundle,
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from ...ingestion.bundle import build_api_raw_bundle


def _audit_not_implemented(run_context: RunContext) -> IngestionResult:
    status = SourceStatus(
        source_name="audit_files",
        kind=SourceKind.FILE,
        status=SourceStatusCode.NOT_IMPLEMENTED,
        is_required=True,
        rows_loaded=None,
        requested_date=run_context.requested_date_iso,
        resolved_date=run_context.resolved_date_iso,
        warnings=["audit_file_mode ingestion is not implemented yet"],
        debug={"mode": run_context.mode.value},
    )
    payload = RawSourcePayload(source_name="audit_files", payload=None, status=status)
    raw_bundle = RawBundle(
        run_context=run_context,
        sources={"audit_files": payload},
        diagnostics={
            "mode": run_context.mode.value,
            "required_file_inputs": list(AUDIT_MODE.required_file_inputs),
            "optional_file_inputs": list(AUDIT_MODE.optional_file_inputs),
            "required_raw_sources": list(AUDIT_MODE.required_raw_sources),
            "optional_raw_sources": list(AUDIT_MODE.optional_raw_sources),
            "status": SourceStatusCode.NOT_IMPLEMENTED.value,
        },
    )
    return IngestionResult(
        raw_bundle=raw_bundle,
        source_flags={"audit_files": SourceStatusCode.NOT_IMPLEMENTED},
        warnings=["audit_file_mode is currently controlled TODO"],
    )


def run(run_context: RunContext) -> IngestionResult:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be RunContext")

    if run_context.mode == RunMode.DAILY_API:
        return build_api_raw_bundle(run_context)

    if run_context.mode == RunMode.AUDIT_FILE:
        return _audit_not_implemented(run_context)

    raise ValueError(
        f"Unsupported run mode: {run_context.mode}. "
        f"Expected one of {[DAILY_MODE.mode.value, AUDIT_MODE.mode.value]}"
    )
