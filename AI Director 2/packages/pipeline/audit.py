"""MVP orchestrator: one cabinet audit for one operational day.

The auditor coordinates existing application boundaries only:

    operational date (D-1, Europe/Moscow)
      -> account registration lookup
      -> daily ingestion (orders/sales/stocks/funnel/advertising)
      -> finance-detail ingestion
      -> DailyAnalysisService (persisted raw pipeline + report artifacts)
      -> audit result with raw provenance

It performs no WB requests itself, calculates no financial values, and
allocates no expenses. COGS and tax are explicit caller inputs; when a source
is absent the finance kernel keeps the period PARTIAL/UNRESOLVED and never
treats missing as zero.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.accounts.contracts import AccountRegistrationRepository
from packages.finance.contracts import (
    FinancialComponentInput,
    FinancialFinalityInput,
    FinancialStatus,
)
from packages.products.contracts import DirectPeriodCogsInput
from packages.settings.contracts import FinancialSettings
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import RawObjectType, TenantAccountScope

from .analysis import (
    AnalysisArtifact,
    DailyAnalysisResult,
    DailyAnalysisService,
    DailyIngestion,
    FinanceDetailIngestion,
    ProductAnalysisRow,
)

_MOSCOW_TIMEZONE_NAME = "Europe/Moscow"


def resolve_operational_date(now: datetime | None = None) -> date:
    """Return D-1 in Europe/Moscow: the last closed WB business day.

    A naive ``now`` is treated as Europe/Moscow wall time; an aware ``now``
    is converted to Europe/Moscow before D-1 is taken.
    """

    from zoneinfo import ZoneInfo

    moment = now if now is not None else datetime.now(ZoneInfo(_MOSCOW_TIMEZONE_NAME))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(_MOSCOW_TIMEZONE_NAME))
    else:
        moment = moment.astimezone(ZoneInfo(_MOSCOW_TIMEZONE_NAME))
    return moment.date() - timedelta(days=1)


class RawObjectReference(BaseModel):
    """Provenance of one immutable raw object behind the audit day."""

    model_config = ConfigDict(frozen=True)

    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AuditRawReferences(BaseModel):
    """Immutable raw-object provenance backing one audit run."""

    model_config = ConfigDict(frozen=True)

    objects: tuple[RawObjectReference, ...] = ()

    @classmethod
    def from_scope(
        cls,
        repository: Any,
        *,
        scope: TenantAccountScope,
        operational_date: date,
    ) -> "AuditRawReferences":
        references: list[RawObjectReference] = []
        for raw_object in repository.list(scope=scope):
            if raw_object.operational_date != operational_date:
                continue
            references.append(
                RawObjectReference(
                    object_type=raw_object.object_type.value,
                    object_id=raw_object.object_id,
                    payload_sha256=raw_object.payload_sha256,
                )
            )
        return cls(
            objects=tuple(
                sorted(
                    references,
                    key=lambda item: (item.object_type, item.object_id),
                )
            )
        )

    def object_ids(self, object_type: RawObjectType) -> tuple[str, ...]:
        return tuple(
            item.object_id for item in self.objects if item.object_type == object_type.value
        )


class AuditReportArtifact(BaseModel):
    """References to immutable report projections written by the analysis boundary."""

    model_config = ConfigDict(frozen=True)

    text_path: Path
    html_path: Path
    pdf_path: Path

    @classmethod
    def from_artifact(cls, artifact: AnalysisArtifact) -> "AuditReportArtifact":
        return cls(
            text_path=artifact.text_path,
            html_path=artifact.html_path,
            pdf_path=artifact.pdf_path,
        )


class CabinetAuditResult(BaseModel):
    """One persisted cabinet audit day with explicit statuses and provenance."""

    model_config = ConfigDict(frozen=True)

    operational_date: date
    account_id: UUID
    seller_id: str
    data_origin: str = Field(pattern=r"^(real_wb_data|test_fixture)$")
    ingestion_status: str
    finance_status: FinancialStatus | None
    audit_status: str
    analysis: DailyAnalysisResult
    raw_references: AuditRawReferences
    report_artifact: AuditReportArtifact
    diagnostics: tuple[str, ...] = ()


class CabinetAuditor:
    """Coordinate one persisted cabinet audit day from existing boundaries."""

    def __init__(
        self,
        *,
        accounts: AccountRegistrationRepository,
        raw_repository: Any,
        analysis_service: DailyAnalysisService,
        daily_ingestion: DailyIngestion | None = None,
        finance_detail_ingestion: FinanceDetailIngestion | None = None,
    ) -> None:
        self._accounts = accounts
        self._raw_repository = raw_repository
        self._analysis_service = analysis_service
        self._daily_ingestion = daily_ingestion
        self._finance_detail_ingestion = finance_detail_ingestion

    def audit(
        self,
        *,
        account_id: UUID,
        operational_date: date | None = None,
        data_origin: str = "real_wb_data",
        finality: tuple[FinancialFinalityInput, ...] = (),
        period_cogs: DirectPeriodCogsInput | None = None,
        tax: SourcedTaxInput | None = None,
        unresolved_marketplace_components: tuple[FinancialComponentInput, ...] = (),
        financial_lag: bool = False,
        financial_settings: FinancialSettings | None = None,
        now: datetime | None = None,
    ) -> CabinetAuditResult:
        """Run one cabinet audit day; delegates all work to existing boundaries."""

        resolved_date = operational_date or resolve_operational_date(now)
        if data_origin not in {"real_wb_data", "test_fixture"}:
            raise ValueError("data_origin must be real_wb_data or test_fixture")

        registration = self._accounts.get_by_account_id(account_id)
        if registration is None:
            raise LookupError(f"registered account not found: {account_id}")
        if not registration.active:
            raise ValueError("registered account is inactive")

        ingestion_status = self._run_ingestion(
            scope=registration.scope,
            operational_date=resolved_date,
            data_origin=data_origin,
        )

        analysis = self._analysis_service.run_analysis(
            account_id=account_id,
            date_from=resolved_date,
            date_to=resolved_date,
            data_origin=data_origin,
            finality=finality,
            period_cogs=period_cogs,
            tax=tax,
            unresolved_marketplace_components=unresolved_marketplace_components,
            financial_lag=financial_lag,
            financial_settings=financial_settings,
        )

        return CabinetAuditResult(
            operational_date=resolved_date,
            account_id=registration.account_id,
            seller_id=registration.seller_id,
            data_origin=data_origin,
            ingestion_status=ingestion_status,
            finance_status=analysis.status,
            audit_status=_audit_status(analysis.status),
            analysis=analysis,
            raw_references=AuditRawReferences.from_scope(
                self._raw_repository,
                scope=registration.scope,
                operational_date=resolved_date,
            ),
            report_artifact=AuditReportArtifact.from_artifact(analysis.artifact),
            diagnostics=analysis.diagnostics,
        )

    def _run_ingestion(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        data_origin: str,
    ) -> str:
        """Ingest through existing boundaries; every service is idempotent by raw identity."""

        if data_origin != "real_wb_data":
            return "skipped_fixture_origin"

        if self._daily_ingestion is None and self._finance_detail_ingestion is None:
            raise RuntimeError(
                "real_wb_data audit requires daily_ingestion or finance_detail_ingestion"
            )

        ingested: list[str] = []
        if self._daily_ingestion is not None:
            self._daily_ingestion.ingest(scope=scope, operational_date=operational_date)
            ingested.append("daily")
        if self._finance_detail_ingestion is not None:
            self._finance_detail_ingestion.ingest(scope=scope, operational_date=operational_date)
            ingested.append("finance_detail")

        return "ingested:" + "+".join(ingested)


def _audit_status(finance_status: FinancialStatus | None) -> str:
    """Deterministic mapping: kernel status -> audit day status.

    COMPLETE stays complete; every partial/unresolved/insufficient kernel state
    stays partial; a day without any finance raw stays no_data. Missing is
    never converted to zero and never silently upgraded.
    """

    if finance_status is None:
        return "no_data"
    if finance_status == FinancialStatus.COMPLETE:
        return "complete"
    if finance_status == FinancialStatus.CONFLICT:
        return "conflict"
    return "partial"


def product_rows(analysis: DailyAnalysisResult) -> tuple[ProductAnalysisRow, ...]:
    """Expose the analysis product projection unchanged (no re-allocation)."""

    return analysis.products
