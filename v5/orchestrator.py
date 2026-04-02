"""Orchestrator: main v5 execution pipeline."""

from __future__ import annotations

import json
import os
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .config import Config
from .domain import (
    CabinetContext,
    Cabinet,
    CabinetConfig,
    ProcessingResult,
    ProcessingStatus,
)
from .infrastructure.config import ensure_cabinet_paths
from .infrastructure.sources import WBAPILoader, FileReportLoader
from .infrastructure.storage import CabinetStorage
from .analytics.normalization import Normalizer
from .analytics.metrics_engine import MetricsEngine
from .analytics.facts_builder import FactsBuilder
from .analytics.decisions_engine import DecisionsEngine
from .outputs.report_generator import ReportGenerator
from .outputs.json_exporter import JsonExporter
from .memory import StateManager


class Orchestrator:
    """Main execution orchestrator for v5."""

    def __init__(self, config: Config):
        self.config = config
        self.normalizer = Normalizer()
        self.metrics_engine = MetricsEngine()

    def _build_context(self, cabinet_id: str) -> CabinetContext:
        cabinet_root = Path(self.config.cabinet_root)
        seller_root = cabinet_root / cabinet_id
        v5_root = seller_root / self.config.v5_namespace
        v5_root.mkdir(parents=True, exist_ok=True)

        api_key = str(os.getenv("WB_API_TOKEN", "")).strip()
        cabinet = Cabinet(
            id=cabinet_id,
            name=f"Cabinet {cabinet_id}",
            api_key=api_key,
            wb_seller_id=cabinet_id,
        )
        ctx = CabinetContext(cabinet=cabinet, config=CabinetConfig(), cabinet_root=v5_root)
        ensure_cabinet_paths(ctx)
        return ctx

    @staticmethod
    def _load_cogs_map(ctx: CabinetContext) -> dict[str, float]:
        """
        Load COGS mapping from seller config (v5-local read, no v3 execution).

        Expected file:
          cabinets/<seller>/config/cogs.json
        """
        cogs_path = ctx.seller_root / "config" / "cogs.json"
        if not cogs_path.exists():
            return {}
        try:
            payload = json.loads(cogs_path.read_text(encoding="utf-8"))
            values = payload.get("values") if isinstance(payload, dict) else {}
            if not isinstance(values, dict):
                return {}
            out: dict[str, float] = {}
            for sku, value in values.items():
                try:
                    val = float(value)
                except Exception:
                    continue
                if val > 0:
                    out[str(sku)] = val
            return out
        except Exception:
            return {}

    @staticmethod
    def _build_warnings(metrics_financial: dict[str, Any], raw_debug: dict[str, Any]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        finality = str(metrics_financial.get("financial_finality_status") or "unavailable")
        if finality in {"partial", "unavailable"}:
            warnings.append(
                {
                    "code": "financial_finality_not_final",
                    "severity": "high" if finality == "unavailable" else "medium",
                    "message": f"Financial finality status is '{finality}'.",
                }
            )

        rows_dropped = int((metrics_financial.get("rows_dropped") or 0))
        if rows_dropped > 0:
            warnings.append(
                {
                    "code": "finance_rows_dropped",
                    "severity": "medium",
                    "message": f"{rows_dropped} finance rows were dropped during parsing.",
                    "details": metrics_financial.get("diagnostics", {}).get("dropped_reasons", {}),
                }
            )

        input_dir = str(raw_debug.get("input_dir") or "").strip()
        if input_dir:
            warnings.append(
                {
                    "code": "audit_input_source",
                    "severity": "info",
                    "message": f"Audit input was resolved from '{input_dir}'.",
                }
            )
        return warnings

    async def _run_pipeline(
        self,
        *,
        cabinet_id: str,
        target_date: date,
        mode: Literal["daily", "audit"],
    ) -> ProcessingResult:
        ctx = self._build_context(cabinet_id)
        cogs_map = self._load_cogs_map(ctx)

        loader = WBAPILoader() if mode == "daily" else FileReportLoader(
            shared_input_dir=self.config.shared_audit_input_root
        )

        state_mgr = StateManager(ctx)
        state = state_mgr.load_state()

        try:
            raw_bundle = await loader.load_data(ctx, target_date)
            normalized = self.normalizer.normalize(raw_bundle)
            metrics = self.metrics_engine.calculate(
                normalized,
                raw_bundle=raw_bundle,
                cogs_by_sku=cogs_map,
            )

            facts_builder = FactsBuilder(ctx.config)
            facts = facts_builder.build(normalized, metrics)
            decisions_engine = DecisionsEngine(ctx.config)
            _ = decisions_engine.generate_recommendations(facts)

            report_gen = ReportGenerator(ctx)
            report_pdf_path = report_gen.generate_pdf(
                metrics=metrics,
                facts=facts,
                target_date=target_date,
                mode=mode,
            )

            json_exporter = JsonExporter(ctx)
            json_exporter.export_metrics(metrics, target_date)
            json_exporter.export_facts(facts, target_date)

            warnings = self._build_warnings(
                metrics_financial=metrics.financial_summary or {},
                raw_debug=raw_bundle.debug if isinstance(raw_bundle.debug, dict) else {},
            )
            json_exporter.export_required_artifacts(
                target_date=target_date,
                mode=mode,
                metrics=metrics,
                facts=facts,
                warnings=warnings,
                report_pdf_path=report_pdf_path,
                raw_bundle=raw_bundle,
                normalized_bundle=normalized,
            )

            storage = CabinetStorage(ctx)
            storage.save_raw(raw_bundle)
            storage.save_normalized(normalized)
            storage.save_metrics(metrics)
            storage.save_facts(facts)

            finality = str((metrics.financial_summary or {}).get("financial_finality_status") or "unavailable")
            run_status = ProcessingStatus.SUCCESS if finality == "final" else ProcessingStatus.PARTIAL

            state.runs_count += 1
            now = datetime.now()
            if mode == "daily":
                state.last_successful_daily_run = now
            else:
                state.last_successful_audit_run = now
            state.last_error = None
            state.last_error_time = None
            state_mgr.save_state(state)

            return ProcessingResult(
                status=run_status,
                cabinet_id=cabinet_id,
                run_date=target_date,
                mode=mode,
                message=(
                    f"v5 pipeline completed ({mode}) with financial_finality_status={finality}. "
                    f"Output root: {ctx.cabinet_root}"
                ),
            )
        except Exception as exc:
            state.runs_count += 1
            state.errors_count += 1
            state.last_error = str(exc)
            state.last_error_time = datetime.now()
            state_mgr.save_state(state)
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                cabinet_id=cabinet_id,
                run_date=target_date,
                mode=mode,
                message=f"Error processing {cabinet_id} in {mode}: {exc}",
                errors=[str(exc)],
            )

    async def run_daily(self, cabinet_id: str) -> ProcessingResult:
        """Run daily API mode."""
        return await self._run_pipeline(
            cabinet_id=cabinet_id,
            target_date=date.today(),
            mode="daily",
        )

    async def run_audit(self, cabinet_id: str, target_date: date) -> ProcessingResult:
        """Run audit (file) mode."""
        return await self._run_pipeline(
            cabinet_id=cabinet_id,
            target_date=target_date,
            mode="audit",
        )

    async def show_analytics(self, cabinet_id: str) -> None:
        """Display analytics summary for a cabinet."""
        raise NotImplementedError("Orchestrator.show_analytics() not yet implemented")
