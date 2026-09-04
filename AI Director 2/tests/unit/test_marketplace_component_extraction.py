"""Marketplace component extraction and the authoritative P&L formula.

The rows below reproduce the shape Wildberries actually returns from
``/api/finance/v1/sales-reports/detailed``: money arrives as strings, charges
live on their own operation rows, and every charge magnitude is non-negative.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.advertising.service import build_advertising_read_model
from packages.data.canonical import FinancialRecordClassification
from packages.data.normalization import (
    normalize_advertising_performance,
    normalize_finance_detail,
    normalize_orders,
)
from packages.finance.contracts import (
    FinancialComponent,
    FinancialComponentInput,
    FinancialComponentStatus,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInput,
    FinancialInputState,
    FinancialStatus,
)
from packages.finance.finance_detail_adapter import build_financial_input_from_finance_detail
from packages.finance.flow import calculate_integrated_financial_flow
from packages.finance.kernel import calculate_financial_result
from packages.operational.service import build_operational_daily_read_model
from packages.products.contracts import DirectPeriodCogsInput
from packages.reports.renderers import render_email_text
from packages.reports.service import build_report_payload
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    FINANCE_DETAIL_ENDPOINT,
    ORDERS_ENDPOINT,
    RawObject,
)
from packages.wb_core.synthetic_scenario import synthetic_scope

DAY = date(2026, 9, 2)
RETRIEVED_AT = datetime(2026, 9, 3, 6, 0, tzinfo=UTC)


def _finance_raw(rows: list[dict[str, object]]) -> RawObject:
    return RawObject(
        object_id="c" * 64,
        scope=synthetic_scope(),
        endpoint=FINANCE_DETAIL_ENDPOINT,
        object_type=FINANCE_DETAIL_ENDPOINT.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat(), "dateTo": DAY.isoformat()},
        payload={"data": rows},
        schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
    )


def _sale(rrd_id: str, retail: str, commission: str, acquiring: str) -> dict[str, object]:
    return {
        "rrdId": rrd_id,
        "rrDate": DAY.isoformat(),
        "nmId": 1001,
        "supplierArticle": "ART-1001",
        "sellerOperName": "Продажа",
        "docTypeName": "Продажа",
        "quantity": "1",
        "retailAmount": retail,
        "retailPriceWithDiscRub": retail,
        "forPay": "517.04",
        "ppvzSalesCommission": commission,
        "acquiringFee": acquiring,
        "deliveryService": "0",
        "paidStorage": "0",
        "paidAcceptance": "0",
        "penalty": "0",
        "deduction": "0",
        "rebillLogisticCost": "0",
        "currency": "RUB",
    }


def _charge_row(rrd_id: str, operation: str, **charges: str) -> dict[str, object]:
    row: dict[str, object] = {
        "rrdId": rrd_id,
        "rrDate": DAY.isoformat(),
        "nmId": 1001,
        "sellerOperName": operation,
        "quantity": "0",
        "retailAmount": "0",
        "currency": "RUB",
    }
    row.update(charges)
    return row


def _real_day_rows(*, include_rebill: bool = True) -> list[dict[str, object]]:
    """Amounts are the observed 2026-09-02 report values; record IDs are synthetic."""

    rows: list[dict[str, object]] = [
        _sale("parity-1", "834", "232.46", "33.36"),
        _sale("parity-2", "605", "93.11", "24.2"),
        _charge_row("parity-3", "Доставка", deliveryService="31.2"),
        _charge_row("parity-4", "Доставка", deliveryService="44.2"),
        _charge_row("parity-5", "Хранение", paidStorage="5.89"),
        _charge_row("parity-6", "Обработка товара", paidAcceptance="10"),
    ]
    if include_rebill:
        rows.append(_charge_row("parity-7", "Возмещение издержек по перевозке", rebillLogisticCost="76.92"))
    return rows


def _operational() -> object:
    """Minimal operational read model so the report projection can be exercised."""

    raw = RawObject(
        object_id="9" * 64,
        scope=synthetic_scope(),
        endpoint=ORDERS_ENDPOINT,
        object_type=ORDERS_ENDPOINT.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()},
        schema_version=ORDERS_ENDPOINT.schema_version,
        payload={
            "data": [
                {"srid": "order-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "834",
                 "isCancel": False, "date": DAY.isoformat()}
            ]
        },
    )
    return build_operational_daily_read_model(orders=normalize_orders(raw))


def _advertising(amount: str) -> object:
    raw = RawObject(
        object_id="e" * 64,
        scope=synthetic_scope(),
        endpoint=ADVERTISING_PERFORMANCE_ENDPOINT,
        object_type=ADVERTISING_PERFORMANCE_ENDPOINT.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()},
        schema_version=ADVERTISING_PERFORMANCE_ENDPOINT.schema_version,
        payload={"data": [{"advertId": 1, "attributionScope": "period", "sum": amount}]},
    )
    return build_advertising_read_model(normalize_advertising_performance(raw))


def _finality() -> tuple[FinancialFinalityInput, ...]:
    return (
        FinancialFinalityInput(
            source="wildberries",
            source_record_id="parity-1",
            operational_date=DAY,
            financial_date=DAY,
            finality=FinancialFinality.FINAL,
            evidence_code="statement_closed",
        ),
    )


def _amount_for(build: object, component: FinancialComponent) -> Decimal | None:
    financial_input = build.financial_input  # type: ignore[attr-defined]
    amounts = [
        item.amount
        for item in financial_input.components
        if item.component is component and item.state is FinancialInputState.PROVIDED
    ]
    if not amounts:
        return None
    return sum(amounts, Decimal("0"))


# ---------------------------------------------------------------- extraction


def test_charges_are_extracted_from_their_own_operation_rows() -> None:
    """The adapter no longer stops at realized_revenue: logistics lives on its own rows."""

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw(_real_day_rows())))

    assert _amount_for(build, FinancialComponent.REALIZED_REVENUE) == Decimal("1439")
    assert _amount_for(build, FinancialComponent.MARKETPLACE_COMMISSION) == Decimal("-325.57")
    assert _amount_for(build, FinancialComponent.ACQUIRING) == Decimal("-57.56")
    assert _amount_for(build, FinancialComponent.LOGISTICS) == Decimal("-75.4")
    assert _amount_for(build, FinancialComponent.STORAGE) == Decimal("-5.89")
    assert _amount_for(build, FinancialComponent.ACCEPTANCE) == Decimal("-10")


def test_absent_charge_field_yields_no_component_rather_than_zero() -> None:
    """A field WB never sent is unknown, not a zero charge."""

    rows = [_sale("1", "100.00", "10.00", "1.00")]
    for row in rows:
        row.pop("paidStorage")  # type: ignore[union-attr]
    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw(rows)))

    financial_input = build.financial_input
    assert financial_input is not None
    assert not [item for item in financial_input.components if item.component is FinancialComponent.STORAGE]


def test_source_declared_zero_is_reported_as_zero() -> None:
    """The opposite case: WB says the charge was zero, so the component is a zero."""

    build = build_financial_input_from_finance_detail(
        normalize_finance_detail(_finance_raw([_sale("1", "100.00", "10.00", "1.00")]))
    )

    assert _amount_for(build, FinancialComponent.PENALTIES) == Decimal("0")


def test_revenue_stays_gated_on_classified_sales_while_charges_are_not() -> None:
    returned = _charge_row("9", "Возврат товара", ppvzSalesCommission="-25.65")
    returned["retailAmount"] = "451.00"

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw([returned])))

    assert build.financial_input is None
    assert any("excluded from realized revenue" in line for line in build.diagnostics)


def test_negative_charge_surfaces_as_unresolved_with_a_reason() -> None:
    """A credit-shaped commission must not be silently turned into an expense."""

    build = build_financial_input_from_finance_detail(
        normalize_finance_detail(_finance_raw([_sale("1", "100.00", "-25.65", "1.00")]))
    )

    financial_input = build.financial_input
    assert financial_input is not None
    commission = [
        item for item in financial_input.components if item.component is FinancialComponent.MARKETPLACE_COMMISSION
    ]
    assert [item.state for item in commission] == [FinancialInputState.UNRESOLVED]
    assert commission[0].amount == Decimal("-25.65")
    assert any("marketplace_commission is excluded from the authoritative P&L" in line for line in build.diagnostics)


def test_money_fields_without_an_approved_policy_are_reported_not_dropped() -> None:
    row = _sale("1", "100.00", "10.00", "1.00")
    row["cashbackAmount"] = "86"

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw([row])))

    reported = [line for line in build.diagnostics if "cashbackAmount" in line]
    assert len(reported) == 1
    assert "86" in reported[0] and "excluded, not zeroed" in reported[0]


def test_operation_name_is_read_from_the_field_wb_sends() -> None:
    """WB sends ``sellerOperName``; reading only the legacy alias hid every charge."""

    records = normalize_finance_detail(_finance_raw([_sale("1", "100.00", "10.00", "1.00")]))

    assert records[0].operation_name == "Продажа"
    assert records[0].classification is FinancialRecordClassification.FINANCIAL_SALE


def test_source_declared_zero_retail_is_not_reported_as_an_exclusion() -> None:
    """A non-sale row with retailAmount 0 excluded nothing; the report must not claim it did."""

    rows = [
        _sale("parity-1", "834.00", "232.46", "33.36"),
        _charge_row("parity-2", "Доставка", deliveryService="75.40"),
    ]

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw(rows)))

    assert [line for line in build.diagnostics if "retailAmount excluded" in line] == []


def test_nonzero_retail_on_a_non_sale_row_is_reported_as_an_exclusion() -> None:
    """The opposite case still has to be visible: real money left the revenue view."""

    rows = [
        _sale("parity-1", "834.00", "232.46", "33.36"),
        _charge_row("parity-3", "Доставка", retailAmount="150.00", deliveryService="75.40"),
    ]

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw(rows)))

    assert [line for line in build.diagnostics if "retailAmount excluded" in line] == [
        "retailAmount excluded from realized revenue for non-sale record parity-3"
    ]


def test_rebill_evidence_stays_inspectable_in_the_canonical_record() -> None:
    """The VAT columns that proved the direction are retained, not discarded."""

    row = _charge_row("parity-vat", "Возмещение издержек по перемещению", rebillLogisticCost="2.65")
    row["vw"] = "-2.1721311475409836"
    row["vwNds"] = "-0.48"

    record = normalize_finance_detail(_finance_raw([row]))[0]
    charges = {charge.source_field: charge.value for charge in record.unapproved_money_fields}

    assert charges["vw"] == Decimal("-2.1721311475409836")
    assert charges["vwNds"] == Decimal("-0.48")
    assert (Decimal("2.65") / Decimal("1.22")).quantize(Decimal("0.01")) == Decimal("2.17")


def test_legacy_operation_name_alias_still_normalizes() -> None:
    row = _sale("1", "100.00", "10.00", "1.00")
    row.pop("sellerOperName")
    row["supplierOperName"] = "Продажа"

    records = normalize_finance_detail(_finance_raw([row]))

    assert records[0].classification is FinancialRecordClassification.FINANCIAL_SALE


# ------------------------------------------------------------------ formula


def test_kernel_formula_subtracts_every_confirmed_component() -> None:
    """revenue − commission − logistics − storage − acquiring − deductions − advertising − COGS − tax."""

    signed = {
        FinancialComponent.REALIZED_REVENUE: "1000.00",
        FinancialComponent.MARKETPLACE_COMMISSION: "-200.00",
        FinancialComponent.LOGISTICS: "-60.00",
        FinancialComponent.STORAGE: "-12.00",
        FinancialComponent.ACQUIRING: "-18.00",
        FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS: "-7.00",
        FinancialComponent.ACCEPTANCE: "-5.00",
        FinancialComponent.PENALTIES: "-3.00",
        FinancialComponent.ADVERTISING: "-90.00",
        FinancialComponent.COGS: "-240.00",
        FinancialComponent.TAX: "-41.50",
    }
    components = tuple(
        FinancialComponentInput(
            component=kind,
            state=FinancialInputState.PROVIDED,
            amount=Decimal(amount),
            source="test",
            source_endpoint="test",
            source_record_id=f"r{index}",
            operational_date=DAY,
            financial_date=DAY,
        )
        for index, (kind, amount) in enumerate(signed.items(), start=1)
    )
    financial_input = FinancialInput(
        scope=synthetic_scope(),
        operational_date=DAY,
        currency="RUB",
        reconciled_facts=(),
        components=components,
        revenue_views=(),
        finality=(
            FinancialFinalityInput(
                source="test",
                source_record_id="r1",
                operational_date=DAY,
                financial_date=DAY,
                finality=FinancialFinality.FINAL,
                evidence_code="statement_closed",
            ),
        ),
    )

    result = calculate_financial_result(financial_input)

    expected = sum((Decimal(amount) for amount in signed.values()), Decimal("0"))
    assert expected == Decimal("323.50")
    assert result.status is FinancialStatus.COMPLETE
    assert result.net_profit == expected
    assert len(result.component_traces) == len(signed)


def _flow_with_settings(rows: list[dict[str, object]]) -> object:
    """Run the real flow with the seller's own COGS, tax and finality declarations."""

    return calculate_integrated_financial_flow(
        finance_records=normalize_finance_detail(_finance_raw(rows)),
        finality=_finality(),
        advertising=_advertising("77.04"),
        period_cogs=DirectPeriodCogsInput(
            scope=synthetic_scope(),
            operational_date=DAY,
            state=FinancialInputState.PROVIDED,
            amount=Decimal("-550.00"),
            source="ledger",
            source_record_id="cogs-1",
            source_endpoint="ledger",
        ),
        tax=SourcedTaxInput(
            scope=synthetic_scope(),
            operational_date=DAY,
            financial_date=DAY,
            state=FinancialInputState.PROVIDED,
            amount=Decimal("-86.34"),
            source="tax_statement",
            source_record_id="tax-1",
            source_endpoint="tax",
        ),
    )


def test_day_without_rebill_rows_is_complete() -> None:
    flow = _flow_with_settings(_real_day_rows(include_rebill=False))

    result = flow.financial_result
    assert result is not None
    assert result.status is FinancialStatus.COMPLETE
    assert result.net_profit == Decimal("251.20")


def test_rebill_logistics_is_subtracted_from_the_full_day() -> None:
    """The proven charge reduces profit by exactly its source magnitude."""

    flow = _flow_with_settings(_real_day_rows())

    result = flow.financial_result
    assert result is not None
    assert result.status is FinancialStatus.COMPLETE
    rebill = next(trace for trace in result.component_traces if trace.component is FinancialComponent.REBILL_LOGISTICS)
    assert rebill.status is FinancialComponentStatus.AVAILABLE
    assert rebill.included is True
    assert rebill.amount == Decimal("-76.92")
    assert result.net_profit == Decimal("174.28")
    assert result.net_profit == Decimal("251.20") - Decimal("76.92")


def test_unresolved_rows_produce_one_aggregated_diagnostic() -> None:
    """Three contradicted rows of one component are one fact, not three lines."""

    rows = [_sale("parity-1", "100.00", "10.00", "1.00")] + [
        _charge_row(f"parity-r{i}", "Корректировка реализации", ppvzSalesCommission="-5.00") for i in range(3)
    ]

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_finance_raw(rows)))

    lines = [line for line in build.diagnostics if line.startswith("marketplace_commission is excluded")]
    assert len(lines) == 1
    assert "3 source rows" in lines[0]
    assert "-15.00 total" in lines[0]


def test_excluded_component_is_not_projected_as_a_pnl_amount() -> None:
    """A report line the kernel never summed must not print as a summable number."""

    flow = calculate_integrated_financial_flow(
        finance_records=normalize_finance_detail(
            _finance_raw([_sale("parity-1", "100.00", "-25.65", "1.00")])
        ),
        finality=_finality(),
    )
    payload = build_report_payload(operational=_operational(), financial=flow.financial_result)
    metrics = {metric.key: metric for metric in payload.metrics}
    rendered = render_email_text(payload)

    assert metrics["marketplace_commission"].value is None
    assert metrics["marketplace_commission"].status == "unresolved"
    assert "marketplace_commission: -25.65" not in rendered
    assert "realized_revenue: 100.00" in rendered
