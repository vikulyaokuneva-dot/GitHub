"""JSON exporter for v5 output and artifact contracts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..domain import (
    MetricsBundle,
    FactsBundle,
    RawDataBundle,
    NormalizedDataBundle,
    CabinetContext,
)


class JsonExporter:
    """Exports v5 runtime bundles to isolated cabinet-scoped JSON files."""

    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx

    @staticmethod
    def _write_json(path: Path, payload: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return path

    def export_metrics(self, metrics: MetricsBundle, target_date: date) -> Path:
        """Write dated metrics snapshot into v5 outputs."""
        json_path = self.cabinet_ctx.outputs_dir / f"metrics_analysis_{target_date}.json"
        return self._write_json(json_path, asdict(metrics))

    def export_facts(self, facts: FactsBundle, target_date: date) -> Path:
        """Write dated facts snapshot into v5 outputs."""
        json_path = self.cabinet_ctx.outputs_dir / f"decisions_{target_date}.json"
        return self._write_json(json_path, asdict(facts))

    def export_required_artifacts(
        self,
        *,
        run_date: date,
        report_date: date,
        date_shift_applied: bool,
        date_shift_reason: str,
        mode: str,
        metrics: MetricsBundle,
        facts: FactsBundle,
        warnings: list[dict[str, Any]],
        report_pdf_path: Path,
        raw_bundle: RawDataBundle,
        normalized_bundle: NormalizedDataBundle,
    ) -> dict[str, Path]:
        """
        Emit required v5 delivery contract files into artifacts directory:
          - metrics.json
          - report_meta.json
          - financial_debug.json
          - report.pdf (copied/normalized target)
          - warnings.json
        """
        metrics_payload = asdict(metrics)
        facts_payload = asdict(facts)
        raw_payload = asdict(raw_bundle)
        normalized_payload = asdict(normalized_bundle)
        financial_summary = metrics_payload.get("financial_summary") or {}
        financial_debug = financial_summary.get("debug") if isinstance(financial_summary, dict) else {}
        debug_dir = self.cabinet_ctx.debug_artifacts_dir

        metrics_json = self._write_json(self.cabinet_ctx.metrics_json_path, metrics_payload)
        warnings_json = self._write_json(self.cabinet_ctx.warnings_path, warnings)
        financial_debug_json = self._write_json(
            self.cabinet_ctx.financial_debug_path,
            financial_debug if isinstance(financial_debug, dict) else {},
        )

        # Normalize report location to canonical artifact path.
        canonical_report_path = self.cabinet_ctx.report_pdf_path
        if report_pdf_path.resolve() != canonical_report_path.resolve():
            canonical_report_path.parent.mkdir(parents=True, exist_ok=True)
            canonical_report_path.write_bytes(report_pdf_path.read_bytes())

        source_counts_comparison_json: Path | None = None
        if isinstance(raw_bundle.debug, dict):
            source_counts = raw_bundle.debug.get("source_counts_comparison")
            if isinstance(source_counts, dict):
                source_counts_comparison_json = self._write_json(
                    debug_dir / "source_counts_comparison.json",
                    source_counts,
                )

        report_meta = {
            "schema_version": "v5",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "cabinet_id": metrics.cabinet_id,
            "mode": mode,
            "run_date": run_date.isoformat(),
            "report_date": report_date.isoformat(),
            "date_shift_applied": bool(date_shift_applied),
            "date_shift_reason": str(date_shift_reason or ""),
            "paths": {
                "artifacts_dir": str(self.cabinet_ctx.artifacts_dir),
                "outputs_dir": str(self.cabinet_ctx.outputs_dir),
                "memory_dir": str(self.cabinet_ctx.memory_dir),
                "report_pdf": str(canonical_report_path),
                "metrics_json": str(metrics_json),
                "warnings_json": str(warnings_json),
                "financial_debug_json": str(financial_debug_json),
                "source_counts_comparison_json": (
                    str(source_counts_comparison_json) if source_counts_comparison_json else ""
                ),
            },
            "counts": {
                "ads": len(raw_bundle.ads),
                "orders": len(raw_bundle.orders),
                "margins": len(raw_bundle.margins),
                "returns": len(raw_bundle.returns),
                "ratings": len(raw_bundle.ratings),
                "facts": len(facts.facts),
                "recommendations": len(facts.recommendations),
            },
            "financial_finality_status": str(
                (metrics.financial_summary or {}).get("financial_finality_status") or "unavailable"
            ),
            "legacy_markers": {
                "v3_title_detected": False,
                "legacy_fallback_detected": False,
                "legacy_mode_flag_detected": False,
            },
        }
        report_meta_json = self._write_json(self.cabinet_ctx.report_meta_path, report_meta)

        raw_debug = self._write_json(debug_dir / "raw_bundle.json", raw_payload)
        normalized_debug = self._write_json(debug_dir / "normalized_bundle.json", normalized_payload)
        facts_debug = self._write_json(debug_dir / "facts_bundle.json", facts_payload)

        exported_paths: dict[str, Path] = {
            "metrics_json": metrics_json,
            "warnings_json": warnings_json,
            "financial_debug_json": financial_debug_json,
            "report_meta_json": report_meta_json,
            "report_pdf": canonical_report_path,
            "debug_raw": raw_debug,
            "debug_normalized": normalized_debug,
            "debug_facts": facts_debug,
        }
        if source_counts_comparison_json:
            exported_paths["debug_source_counts_comparison"] = source_counts_comparison_json
        return exported_paths
