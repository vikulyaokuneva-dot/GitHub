"""FastAPI application shell.

No domain service or legacy module is imported here. The API may expose only
process-level health until tenant-scoped persistence and authorization exist.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api.financial_settings import (
    FinancialSettingsInputError,
    parse_cogs,
    parse_nm_id,
    parse_optional_sku,
    parse_tax_rate,
    settings_payload,
)
from packages.common.health import HealthPayload, HealthState, ReadinessProbe, StaticReadinessProbe
from packages.common.settings import Settings
from packages.accounts.contracts import AccountRegistrationRepository
from packages.accounts.sqlite_repository import SQLiteAccountRegistrationRepository
from packages.pipeline.analysis import DailyAnalysisService
from packages.pipeline.audit import CabinetAuditor, resolve_operational_date
from packages.settings.sqlite_repository import SQLiteFinancialSettingsRepository
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    analysis_service: DailyAnalysisService | None = None,
    audit_service: CabinetAuditor | None = None,
    account_repository: AccountRegistrationRepository | None = None,
    financial_settings_repository: SQLiteFinancialSettingsRepository | None = None,
) -> FastAPI:
    """Create the API without eagerly connecting to infrastructure.

    Dependency probing is injected so a process can start before workers and
    storage do, while `/readyz` remains truthful about unavailable services.
    """

    resolved_settings = settings or Settings.from_environment()
    probe = readiness_probe or StaticReadinessProbe.not_configured()
    analysis = analysis_service
    auditor = audit_service
    accounts = account_repository
    financial_settings = financial_settings_repository

    app = FastAPI(
        title="WB Autopilot API",
        version=resolved_settings.version,
        docs_url=None if resolved_settings.is_production else "/docs",
        redoc_url=None,
    )

    @app.get("/healthz", response_model=HealthPayload, tags=["operations"])
    def healthz() -> HealthPayload:
        return HealthPayload(
            service=resolved_settings.service_name,
            environment=resolved_settings.environment,
            state=HealthState.OK,
            components=[],
        )

    @app.get("/readyz", response_model=None, tags=["operations"])
    def readyz() -> HealthPayload | JSONResponse:
        payload = probe()
        if payload.is_ready:
            return payload
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(mode="json"),
        )

    @app.get("/api/accounts", response_model=None, tags=["analysis"])
    def list_accounts() -> dict[str, object] | JSONResponse:
        if accounts is None:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "account repository is not configured"})
        return {
            "accounts": [
                {
                    "account_id": str(account.account_id),
                    "seller_id": account.seller_id,
                    "provider": account.provider.value,
                    "active": account.active,
                    "created_at": account.created_at.isoformat(),
                }
                for account in accounts.list_wildberries()
            ]
        }

    @app.get("/analysis/{account_id}", response_model=None, tags=["analysis"])
    def run_analysis(account_id: UUID, date_from: date, date_to: date, data_origin: str = "real_wb_data") -> dict[str, object]:
        if analysis is None:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "analysis service is not configured"})
        try:
            result = analysis.run_analysis(
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                data_origin=data_origin,
            )
        except (LookupError, ValueError) as error:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(error)})
        return result.model_dump(mode="json")

    def _settings_scope(account_id: UUID) -> object:
        """Resolve the trusted server-side scope; never trust a client-supplied one."""

        if accounts is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Хранилище аккаунтов недоступно")
        registration = accounts.get_by_account_id(account_id)
        if registration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Аккаунт не найден")
        return registration.scope

    def _settings_store() -> SQLiteFinancialSettingsRepository:
        if financial_settings is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Хранилище финансовых параметров недоступно",
            )
        return financial_settings

    def _settings_response(scope: object, operational_date: date) -> dict[str, object]:
        store = _settings_store()
        return settings_payload(
            operational_date=operational_date,
            tax_rate=store.get_tax_rate(scope),  # type: ignore[arg-type]
            product_costs=store.list_product_costs(scope),  # type: ignore[arg-type]
            confirmation=store.get_confirmation(scope, operational_date),  # type: ignore[arg-type]
        )

    @app.get("/api/accounts/{account_id}/financial-settings", response_model=None, tags=["settings"])
    def read_financial_settings(account_id: UUID, date: date | None = None) -> dict[str, object]:
        """Seller-declared financial parameters currently stored for this account."""

        scope = _settings_scope(account_id)
        return _settings_response(scope, date or resolve_operational_date())  # type: ignore[arg-type]

    @app.put("/api/accounts/{account_id}/financial-settings/tax", response_model=None, tags=["settings"])
    def save_tax_rate(account_id: UUID, body: dict[str, Any]) -> dict[str, object]:
        """Store one tax rate; the amount it produces stays the kernel's business."""

        scope = _settings_scope(account_id)
        try:
            rate = parse_tax_rate(body.get("tax_rate"))
        except FinancialSettingsInputError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
        _settings_store().save_tax_rate(scope, rate)  # type: ignore[arg-type]
        return _settings_response(scope, resolve_operational_date())  # type: ignore[arg-type]

    @app.put("/api/accounts/{account_id}/financial-settings/cogs", response_model=None, tags=["settings"])
    def save_product_cost(account_id: UUID, body: dict[str, Any]) -> dict[str, object]:
        """Store or replace the unit cost declared for one product."""

        scope = _settings_scope(account_id)
        try:
            nm_id = parse_nm_id(body.get("sku"))
            cogs_per_unit = parse_cogs(body.get("cogs_per_unit"))
            seller_sku = parse_optional_sku(body.get("seller_sku"))
        except FinancialSettingsInputError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
        _settings_store().save_product_cost(scope, nm_id, cogs_per_unit, seller_sku=seller_sku)  # type: ignore[arg-type]
        return _settings_response(scope, resolve_operational_date())  # type: ignore[arg-type]

    @app.put("/api/accounts/{account_id}/financial-settings/finality", response_model=None, tags=["settings"])
    def save_finality_confirmation(account_id: UUID, body: dict[str, Any]) -> dict[str, object]:
        """Record or withdraw the seller's claim that one day is financially final."""

        scope = _settings_scope(account_id)
        raw_date = body.get("operational_date")
        if raw_date is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите дату аудита")
        try:
            moment = date.fromisoformat(str(raw_date))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Дата аудита должна быть в формате ГГГГ-ММ-ДД",
            ) from None
        confirmed = bool(body.get("confirmed"))
        store = _settings_store()
        if confirmed:
            store.save_confirmation(scope, moment)  # type: ignore[arg-type]
        else:
            store.delete_confirmation(scope, moment)  # type: ignore[arg-type]
        return _settings_response(scope, moment)  # type: ignore[arg-type]

    @app.get("/audit/{account_id}", response_model=None, tags=["analysis"])
    def run_audit(account_id: UUID, date: date | None = None, data_origin: str = "real_wb_data") -> dict[str, object]:
        """One cabinet audit day: D-1 Europe/Moscow by default, ingestion + persisted analysis.

        Seller-declared financial parameters are loaded server-side and handed to
        the existing audit inputs; the Finance Kernel remains the only calculator.
        """
        if auditor is None:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "audit service is not configured"})
        resolved_date = date or resolve_operational_date()
        settings_bundle = None
        if financial_settings is not None and accounts is not None:
            registration = accounts.get_by_account_id(account_id)
            if registration is not None:
                settings_bundle = financial_settings.get_settings(registration.scope, resolved_date)
        try:
            result = auditor.audit(
                account_id=account_id,
                operational_date=resolved_date,
                data_origin=data_origin,
                financial_settings=settings_bundle,
            )
        except (LookupError, ValueError) as error:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(error)})
        return result.model_dump(mode="json")

    @app.get("/api/reports/{account_id}/{operational_date}/report.pdf", response_model=None, tags=["analysis"])
    def download_pdf(account_id: UUID, operational_date: date) -> FileResponse | JSONResponse:
        reports_root = Path("runtime") / "reports"
        pdf_path = reports_root / str(account_id) / operational_date.isoformat() / "report.pdf"
        if not pdf_path.exists():
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "report PDF not found"})
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"wb-autopilot-{operational_date.isoformat()}.pdf")

    static_root = Path(__file__).resolve().parents[1] / "web" / "static"
    if static_root.exists():
        app.mount("/", StaticFiles(directory=static_root, html=True), name="mvp-ui")

    return app


def _default_analysis_service() -> DailyAnalysisService | None:
    database_path = Path("runtime") / "wb_autopilot.sqlite3"
    raw_repository = SQLiteRawObjectRepository(database_path)

    from packages.compat.wb_sales_funnel_transport import LegacyWBApiLoadersTransport
    from wb_api_core.client import WBApiClient

    daily_ingestion = WBDailyIngestionService(
        repository=raw_repository,
        loaders=LegacyWBApiLoadersTransport(WBApiClient()),
    )

    return DailyAnalysisService(
        accounts=SQLiteAccountRegistrationRepository(database_path),
        raw_repository=raw_repository,
        reports_root=Path("runtime") / "reports",
        daily_ingestion=daily_ingestion,
        finance_detail_ingestion=_default_finance_detail_ingestion(raw_repository),
    )


def _default_finance_detail_ingestion(repository: SQLiteRawObjectRepository) -> WBFinanceDetailIngestionService | None:
    from packages.compat.wb_sales_funnel_transport import LegacyWBApiFinanceDetailTransport
    from wb_api_core.client import WBApiClient

    return WBFinanceDetailIngestionService(
        repository=repository,
        transport=LegacyWBApiFinanceDetailTransport(WBApiClient()),
    )


def _default_account_repository() -> AccountRegistrationRepository:
    return SQLiteAccountRegistrationRepository(Path("runtime") / "wb_autopilot.sqlite3")


def _default_financial_settings_repository() -> SQLiteFinancialSettingsRepository:
    return SQLiteFinancialSettingsRepository(Path("runtime") / "wb_autopilot.sqlite3")


def _default_audit_service() -> CabinetAuditor:
    database_path = Path("runtime") / "wb_autopilot.sqlite3"
    raw_repository = SQLiteRawObjectRepository(database_path)
    analysis = _default_analysis_service()
    if analysis is None:
        raise RuntimeError("daily analysis service is required for the audit orchestrator")
    from packages.compat.wb_sales_funnel_transport import LegacyWBApiLoadersTransport
    from wb_api_core.client import WBApiClient

    return CabinetAuditor(
        accounts=SQLiteAccountRegistrationRepository(database_path),
        raw_repository=raw_repository,
        analysis_service=analysis,
        daily_ingestion=WBDailyIngestionService(
            repository=raw_repository,
            loaders=LegacyWBApiLoadersTransport(WBApiClient()),
        ),
        finance_detail_ingestion=_default_finance_detail_ingestion(raw_repository),
    )


app = create_app(
    analysis_service=_default_analysis_service(),
    audit_service=_default_audit_service(),
    account_repository=_default_account_repository(),
    financial_settings_repository=_default_financial_settings_repository(),
)
