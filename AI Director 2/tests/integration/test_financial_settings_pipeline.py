"""Seller financial parameters must travel the real pipeline into the Finance Kernel."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.finance.contracts import (
    FinancialComponent,
    FinancialComponentStatus,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialStatus,
    FinancialInputState,
)
from packages.pipeline import DailyAnalysisService
from packages.products.contracts import ProductCostProfile
from packages.settings.contracts import FinancialSettings
from packages.settings.sqlite_repository import SQLiteFinancialSettingsRepository
from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    FINANCE_DETAIL_ENDPOINT,
    ORDERS_ENDPOINT,
    SALES_ENDPOINT,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    STOCKS_ENDPOINT,
    EndpointMetadata,
    RawObject,
    RawPayload,
    TenantAccountScope,
)
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
SOLD_NM_ID = "1001"
UNSOLD_NM_ID = "999999999"


def _raw(*, scope: TenantAccountScope, endpoint: EndpointMetadata, suffix: str, payload: RawPayload) -> RawObject:
    return RawObject(
        object_id=(suffix * 64)[:64],
        scope=scope,
        endpoint=endpoint,
        object_type=endpoint.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()},
        payload=payload,
        schema_version=endpoint.schema_version,
    )


def _raw_objects(scope: TenantAccountScope) -> tuple[RawObject, ...]:
    return (
        _raw(scope=scope, endpoint=ORDERS_ENDPOINT, suffix="1", payload=[{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": DAY.isoformat()}]),
        _raw(scope=scope, endpoint=SALES_ENDPOINT, suffix="2", payload=[{"srid": "sale-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "50.00", "date": DAY.isoformat()}]),
        _raw(scope=scope, endpoint=STOCKS_ENDPOINT, suffix="3", payload={"data": [{"nmId": 1001, "quantity": "10", "inWayToClient": "1", "inWayFromClient": "2"}]}),
        _raw(scope=scope, endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT, suffix="4", payload={"data": {"products": [{"product": {"nmId": 1001, "vendorCode": "ART-1001"}, "statistic": {"selected": {"openCount": 20, "cartCount": 4, "orderCount": 2, "buyoutCount": 1, "buyoutSum": "40.00", "currency": "RUB"}}}]}}),
        _raw(scope=scope, endpoint=FINANCE_DETAIL_ENDPOINT, suffix="5", payload=[{"rrdId": "rrd-1", "rrDate": "2026-08-21", "saleDt": DAY.isoformat(), "nmId": 1001, "supplierArticle": "ART-1001", "supplierOperName": "Продажа", "docTypeName": "Продажа", "quantity": "2", "retailAmount": "1000.00", "retailPriceWithDiscRub": "600.00", "ppvzForPay": "700.00", "currency": "RUB"}]),
        _raw(scope=scope, endpoint=ADVERTISING_PERFORMANCE_ENDPOINT, suffix="6", payload={"data": [{"advertId": 1, "nmId": 1001, "sum": "100.00"}, {"advertId": 1, "attributionScope": "period", "sum": "50.00"}]}),
    )


class _Harness:
    """One durable day of WB facts plus the seller settings storage."""

    def __init__(self, tmp_path: Path) -> None:
        database_path = tmp_path / "pipeline.sqlite3"
        accounts = SQLiteAccountRegistrationRepository(database_path)
        self.registration = AccountRegistrationService(accounts).register_wildberries_seller(
            seller_id="settings_pipeline", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
        )
        self.scope = self.registration.scope
        repository = SQLiteRawObjectRepository(database_path)
        for raw_object in _raw_objects(self.scope):
            repository.save(raw_object)
        self.store = SQLiteFinancialSettingsRepository(database_path)
        self._analysis = DailyAnalysisService(
            accounts=accounts,
            raw_repository=repository,
            reports_root=tmp_path / "reports",
        )

    def declare(
        self,
        *,
        unit_cogs: str | None = None,
        for_nm_id: str = SOLD_NM_ID,
        tax_rate: str | None = None,
        confirmed: bool = False,
    ) -> FinancialSettings:
        """Persist declarations through the repository, then read them back."""

        if unit_cogs is not None:
            self.store.save_product_cost(self.scope, for_nm_id, Decimal(unit_cogs))
        if tax_rate is not None:
            self.store.save_tax_rate(self.scope, Decimal(tax_rate))
        if confirmed:
            self.store.save_confirmation(self.scope, DAY)
        return self.store.get_settings(self.scope, DAY)

    def run(self, settings: FinancialSettings | None = None, finality: tuple[FinancialFinalityInput, ...] = ()):
        return self._analysis.run_analysis(
            account_id=self.registration.account_id,
            date_from=DAY,
            date_to=DAY,
            data_origin="test_fixture",
            finality=finality,
            financial_settings=settings,
        )


def _trace(result, component: FinancialComponent):
    financial = result.pipeline.financial_flow.financial_result
    assert financial is not None
    return next(trace for trace in financial.component_traces if trace.component == component)


def test_without_seller_parameters_nothing_is_invented(tmp_path: Path) -> None:
    result = _Harness(tmp_path).run()

    financial = result.pipeline.financial_flow.financial_result
    assert financial is not None
    assert _trace(result, FinancialComponent.COGS).status is FinancialComponentStatus.MISSING
    assert _trace(result, FinancialComponent.TAX).status is FinancialComponentStatus.MISSING
    assert financial.net_profit is None
    assert financial.status is not FinancialStatus.COMPLETE


def test_declared_unit_cost_becomes_available_cogs_without_touching_tax(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    result = harness.run(harness.declare(unit_cogs="300.00"))

    cogs = _trace(result, FinancialComponent.COGS)
    assert cogs.status is FinancialComponentStatus.AVAILABLE
    assert cogs.amount == Decimal("-300.00")
    assert cogs.included is True
    assert cogs.reason == "explicit unit COGS multiplied by caller-authoritative realized quantity"
    assert cogs.source_cogs_allocations[0].quantity == 1
    assert cogs.source_cogs_allocations[0].source == "seller_financial_setting"

    financial = result.pipeline.financial_flow.financial_result
    assert _trace(result, FinancialComponent.TAX).status is FinancialComponentStatus.MISSING
    assert financial.net_profit is None


def test_tax_rate_is_applied_to_realized_revenue_and_never_hardcoded(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)

    six_percent = harness.run(harness.declare(tax_rate="6"))
    tax = _trace(six_percent, FinancialComponent.TAX)
    assert tax.status is FinancialComponentStatus.AVAILABLE
    # realized revenue for the day is 1000.00, so a declared 6 percent is 60.00
    assert tax.amount == Decimal("-60.00")
    assert tax.source_components[0].source_endpoint == "financial_settings"

    twenty_percent = harness.run(harness.declare(tax_rate="20"))
    assert _trace(twenty_percent, FinancialComponent.TAX).amount == Decimal("-200.00")


def test_available_components_stay_partial_until_the_seller_confirms_finality(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    unconfirmed = harness.run(harness.declare(unit_cogs="300.00", tax_rate="6"))

    assert _trace(unconfirmed, FinancialComponent.COGS).status is FinancialComponentStatus.AVAILABLE
    assert _trace(unconfirmed, FinancialComponent.TAX).status is FinancialComponentStatus.AVAILABLE
    assert unconfirmed.status is FinancialStatus.PARTIAL
    assert unconfirmed.pipeline.financial_flow.financial_result.net_profit is None

    confirmed = harness.run(harness.declare(unit_cogs="300.00", tax_rate="6", confirmed=True))
    financial = confirmed.pipeline.financial_flow.financial_result
    assert confirmed.status is FinancialStatus.COMPLETE
    assert financial.net_profit == Decimal("490.00")
    assert financial.profit_margin == Decimal("49")


def test_unit_cost_for_an_item_that_did_not_sell_never_produces_cogs(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    profile = ProductCostProfile(
        scope=harness.scope,
        nm_id=UNSOLD_NM_ID,
        state=FinancialInputState.PROVIDED,
        unit_cogs=Decimal("300.00"),
        effective_from=date(2000, 1, 1),
        source="seller_financial_setting",
        source_record_id=f"cogs:{harness.scope.account_id}:{UNSOLD_NM_ID}",
    )
    result = harness.run(FinancialSettings(product_costs=(profile,)))

    cogs = _trace(result, FinancialComponent.COGS)
    assert cogs.status is FinancialComponentStatus.MISSING
    assert cogs.amount is None
    assert result.pipeline.financial_flow.financial_result.net_profit is None


def test_sold_item_without_a_declared_cost_is_reported_as_a_gap(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    result = harness.run(harness.declare(unit_cogs="300.00", for_nm_id=UNSOLD_NM_ID, tax_rate="6"))

    diagnostics = result.pipeline.report_payload.diagnostics
    assert f"unit cost is not declared for sold nm_id {SOLD_NM_ID}" in diagnostics


def test_confirmation_alone_never_publishes_a_profit(tmp_path: Path) -> None:
    """A finality claim is not financial evidence: missing components stay missing."""

    harness = _Harness(tmp_path)
    result = harness.run(harness.declare(confirmed=True))

    financial = result.pipeline.financial_flow.financial_result
    assert _trace(result, FinancialComponent.COGS).status is FinancialComponentStatus.MISSING
    assert _trace(result, FinancialComponent.TAX).status is FinancialComponentStatus.MISSING
    assert result.status is FinancialStatus.PARTIAL
    assert financial.net_profit is None


def test_explicit_finality_argument_overrides_the_stored_confirmation(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    settings = harness.declare(unit_cogs="300.00", tax_rate="6", confirmed=True)
    open_statement = FinancialFinalityInput(
        source="wildberries",
        source_record_id="rrd-1",
        operational_date=DAY,
        financial_date=DAY,
        finality=FinancialFinality.UNKNOWN,
        evidence_code="explicit_open_statement",
    )

    result = harness.run(settings, finality=(open_statement,))

    assert result.status is FinancialStatus.PARTIAL
    assert result.pipeline.financial_flow.financial_result.net_profit is None
