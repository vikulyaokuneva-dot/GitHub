"""Application use case for a persisted daily V2 analysis."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.accounts.contracts import AccountRegistrationRepository
from packages.data.canonical import FinancialRecordClassification
from packages.finance.contracts import (
    FinancialComponentInput,
    FinancialFinalityInput,
    FinancialStatus,
)
from packages.products.contracts import DirectPeriodCogsInput
from packages.reports.renderers import render_email_html, render_email_text, render_pdf
from packages.settings.contracts import FinancialSettings
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import RawObjectRepository, TenantAccountScope

from .service import PipelineResult, run_stored_daily_pipeline


_DATA_ORIGINS = frozenset({"real_wb_data", "test_fixture"})


class DailyIngestion(Protocol):
    """Application boundary for obtaining and persisting one WB daily bundle."""

    def ingest(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: object | None = None,
    ) -> None:
        ...


class FinanceDetailIngestion(Protocol):
    """Application boundary for idempotent finance-detail raw ingestion."""

    def ingest(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: Any | None = None,
    ) -> object:
        ...


class AnalysisArtifact(BaseModel):
    """References to immutable report projections written by the application boundary."""

    model_config = ConfigDict(frozen=True)

    text_path: Path
    html_path: Path
    pdf_path: Path


class DailyAnalysisResult(BaseModel):
    """One analysis result with an explicit fixture-versus-live provenance label."""

    model_config = ConfigDict(frozen=True)

    account_id: UUID
    operational_date: date
    data_origin: str = Field(pattern=r"^(real_wb_data|test_fixture)$")
    pipeline: PipelineResult
    products: tuple["ProductAnalysisRow", ...] = ()
    artifact: AnalysisArtifact
    status: FinancialStatus | None = None
    diagnostics: tuple[str, ...] = ()


class ProductAnalysisRow(BaseModel):
    """Evidence-bound product projection; period expenses are never allocated here."""

    model_config = ConfigDict(frozen=True)

    nm_id: str = Field(min_length=1, max_length=30)
    seller_sku: str | None = None
    sales_quantity: Decimal | None = None
    sales_amount: Decimal | None = None
    realized_revenue: Decimal | None = None
    direct_advertising: Decimal | None = None
    cogs: Decimal | None = None
    profit: Decimal | None = None
    margin: Decimal | None = None
    source_object_ids: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


class DailyAnalysisService:
    """
    Coordinates the V2 daily ingestion, persisted facts and pure renderers.

    Live flow:

        WB API
          -> DailyIngestion
          -> immutable RawObjects
          -> run_stored_daily_pipeline()
          -> report

    The analysis service itself does not call WB API directly.
    """

    def __init__(
        self,
        *,
        accounts: AccountRegistrationRepository,
        raw_repository: RawObjectRepository,
        reports_root: Path,
        daily_ingestion: DailyIngestion | None = None,
        finance_detail_ingestion: FinanceDetailIngestion | None = None,
    ) -> None:
        self._accounts = accounts
        self._raw_repository = raw_repository
        self._reports_root = reports_root
        self._daily_ingestion = daily_ingestion
        self._finance_detail_ingestion = finance_detail_ingestion

    def run_analysis(
        self,
        *,
        account_id: UUID,
        date_from: date,
        date_to: date,
        data_origin: str,
        finality: tuple[FinancialFinalityInput, ...] = (),
        period_cogs: DirectPeriodCogsInput | None = None,
        tax: SourcedTaxInput | None = None,
        unresolved_marketplace_components: tuple[
            FinancialComponentInput, ...
        ] = (),
        financial_lag: bool = False,
        financial_settings: FinancialSettings | None = None,
    ) -> DailyAnalysisResult:
        """
        Run one persisted daily analysis.

        For real WB data, ingestion happens before the pipeline reads
        RawObjects. Test fixtures never trigger external ingestion.
        """

        if date_from != date_to:
            raise ValueError(
                "MVP daily analysis requires date_from to equal date_to"
            )

        if data_origin not in _DATA_ORIGINS:
            raise ValueError(
                "data_origin must be real_wb_data or test_fixture"
            )

        registration = self._accounts.get_by_account_id(account_id)

        if registration is None:
            raise LookupError(
                f"registered account not found: {account_id}"
            )

        if not registration.active:
            raise ValueError("registered account is inactive")

        # A seller confirmation is one of the declared inputs, so the bundle can
        # carry it end to end.  An explicit ``finality`` argument still wins: the
        # caller who knows better than the stored declaration stays in charge.
        if (
            not finality
            and financial_settings is not None
            and financial_settings.finality_confirmation is not None
        ):
            finality = (financial_settings.finality_confirmation.to_financial_finality_input(),)

        # ------------------------------------------------------------
        # LIVE INGESTION
        # ------------------------------------------------------------
        #
        # One application-level ingestion boundary obtains the complete
        # daily WB bundle:
        #
        #   orders
        #   sales
        #   stocks
        #   funnel
        #   advertising
        #   finance_detail
        #
        # The ingestion service persists immutable RawObjects.
        #
        # We deliberately do NOT swallow ingestion errors here.
        # A live report must not silently continue with missing data.
        # ------------------------------------------------------------
        if data_origin == "real_wb_data":
            if self._daily_ingestion is None and self._finance_detail_ingestion is None:
                raise RuntimeError(
                    "real_wb_data analysis requires daily_ingestion or finance_detail_ingestion"
                )

            if self._daily_ingestion is not None:
                self._daily_ingestion.ingest(
                    scope=registration.scope,
                    operational_date=date_from,
                )

            if self._finance_detail_ingestion is not None:
                self._finance_detail_ingestion.ingest(
                    scope=registration.scope,
                    operational_date=date_from,
                )

        # ------------------------------------------------------------
        # PURE PERSISTED PIPELINE
        # ------------------------------------------------------------
        #
        # From this point onward there are no WB API calls.
        # The pipeline reads only persisted RawObjects.
        # ------------------------------------------------------------
        pipeline = run_stored_daily_pipeline(
            repository=self._raw_repository,
            scope=registration.scope,
            operational_date=date_from,
            finality=finality,
            period_cogs=period_cogs,
            tax=tax,
            unresolved_marketplace_components=(
                unresolved_marketplace_components
            ),
            financial_lag=financial_lag,
            financial_settings=financial_settings,
        )

        artifact = self._write_artifact(
            account_id=account_id,
            operational_date=date_from,
            pipeline=pipeline,
        )

        financial = pipeline.financial_flow.financial_result

        diagnostics = tuple(pipeline.report_payload.diagnostics)

        if not pipeline.finance_records:
            diagnostics += (
                "finance detail is absent; no authoritative P&L is available",
            )

        return DailyAnalysisResult(
            account_id=account_id,
            operational_date=date_from,
            data_origin=data_origin,
            pipeline=pipeline,
            products=_product_rows(pipeline),
            artifact=artifact,
            status=None if financial is None else financial.status,
            diagnostics=diagnostics,
        )

    def _write_artifact(
        self,
        *,
        account_id: UUID,
        operational_date: date,
        pipeline: PipelineResult,
    ) -> AnalysisArtifact:
        directory = (
            self._reports_root
            / str(account_id)
            / operational_date.isoformat()
        )
        directory.mkdir(parents=True, exist_ok=True)

        text_path = directory / "report.txt"
        html_path = directory / "report.html"
        pdf_path = directory / "report.pdf"

        text_path.write_text(
            render_email_text(pipeline.report_payload),
            encoding="utf-8",
        )

        html_path.write_text(
            render_email_html(pipeline.report_payload),
            encoding="utf-8",
        )

        pdf_path.write_bytes(
            render_pdf(pipeline.report_payload)
        )

        return AnalysisArtifact(
            text_path=text_path,
            html_path=html_path,
            pdf_path=pdf_path,
        )


def _product_rows(
    pipeline: PipelineResult,
) -> tuple[ProductAnalysisRow, ...]:
    """
    Expose only source-evidenced SKU values.

    Important financial rule:
    period-level expenses are NOT allocated to SKU.
    COGS is NOT invented when authoritative per-SKU COGS is absent.
    """

    sales_by_nm: dict[
        str,
        tuple[
            list[Decimal | None],
            list[Decimal | None],
            str | None,
            set[str],
        ],
    ] = {}

    for fact in pipeline.operational.sales:
        if fact.nm_id is None:
            continue

        (
            raw_quantities,
            raw_amounts,
            seller_sku,
            source_object_ids,
        ) = sales_by_nm.get(
            fact.nm_id,
            (
                [],
                [],
                fact.seller_sku,
                set(),
            ),
        )

        raw_quantities.append(fact.quantity)
        raw_amounts.append(fact.amount)

        sales_by_nm[fact.nm_id] = (
            raw_quantities,
            raw_amounts,
            seller_sku or fact.seller_sku,
            source_object_ids
            | {fact.source_metadata.source_object_id},
        )

    # ------------------------------------------------------------
    # Authoritative realized revenue from finance detail.
    #
    # Only FINANCIAL_SALE records with a real nm_id and retail_amount
    # are allowed into the SKU-level realized revenue projection.
    # ------------------------------------------------------------
    revenue_by_nm: dict[str, tuple[Decimal, set[str]]] = {}

    for record in pipeline.finance_records:
        if (
            record.nm_id is not None
            and record.classification
            == FinancialRecordClassification.FINANCIAL_SALE
            and record.retail_amount is not None
        ):
            amount, source_ids = revenue_by_nm.get(
                record.nm_id,
                (Decimal("0"), set()),
            )

            revenue_by_nm[record.nm_id] = (
                amount + record.retail_amount,
                source_ids
                | {record.source_metadata.source_object_id},
            )

    # ------------------------------------------------------------
    # Advertising:
    #
    # build_advertising_read_model() already distinguishes direct
    # SKU attribution from period-level advertising.
    #
    # We use ONLY direct_sku_spend here.
    # ------------------------------------------------------------
    direct_advertising = (
        {}
        if pipeline.report_payload.advertising is None
        else pipeline.report_payload.advertising.direct_sku_spend
    )

    identifiers = sorted(
        set(sales_by_nm)
        | set(revenue_by_nm)
        | set(direct_advertising)
    )

    rows: list[ProductAnalysisRow] = []

    for nm_id in identifiers:
        sales_values = sales_by_nm.get(
            nm_id,
            (
                [],
                [],
                None,
                set(),
            ),
        )

        quantity_values: tuple[Decimal | None, ...] = tuple(
            sales_values[0]
        )

        amount_values: tuple[Decimal | None, ...] = tuple(
            sales_values[1]
        )

        # Quantity is exposed only when every contributing source event
        # has an authoritative quantity.
        sales_quantity = (
            sum(
                (
                    value
                    for value in quantity_values
                    if value is not None
                ),
                Decimal("0"),
            )
            if quantity_values
            and all(
                value is not None
                for value in quantity_values
            )
            else None
        )

        # Sales amount follows the same evidence rule.
        sales_amount = (
            sum(
                (
                    value
                    for value in amount_values
                    if value is not None
                ),
                Decimal("0"),
            )
            if amount_values
            and all(
                value is not None
                for value in amount_values
            )
            else None
        )

        seller_sku = sales_values[2]

        source_object_ids = set(sales_values[3])

        revenue = revenue_by_nm.get(nm_id)

        if revenue is not None:
            source_object_ids.update(revenue[1])

        diagnostics = [
            "period-level advertising is not allocated to SKU",
            "COGS is unavailable per SKU",
        ]

        if revenue is None:
            diagnostics.append(
                "authoritative realized revenue is unavailable per SKU"
            )

        if quantity_values and sales_quantity is None:
            diagnostics.append(
                "sales quantity is missing for at least one source event"
            )

        if amount_values and sales_amount is None:
            diagnostics.append(
                "sales amount is missing for at least one source event"
            )

        rows.append(
            ProductAnalysisRow(
                nm_id=nm_id,
                seller_sku=seller_sku,
                sales_quantity=sales_quantity,
                sales_amount=sales_amount,
                realized_revenue=(
                    None
                    if revenue is None
                    else revenue[0]
                ),
                direct_advertising=direct_advertising.get(nm_id),
                source_object_ids=tuple(
                    sorted(source_object_ids)
                ),
                diagnostics=tuple(diagnostics),
            )
        )

    return tuple(rows)