"""Sign-policy tests: every WB charge field has one declared canonical treatment.

The matrix each component must satisfy is identical and deliberately strict:

* a documented non-negative magnitude becomes a negative component;
* a zero stays a zero (it is a source-declared zero, not a defaulted one);
* a value that contradicts the convention is retained unresolved with its
  original sign — the case that ``abs()`` would silently destroy;
* provenance travels with the amount, never beside it.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from packages.data.canonical import CanonicalInputState, CanonicalSourceMoney, CanonicalValueKind
from packages.data.normalization import normalize_finance_detail
from packages.finance.contracts import FinancialComponent, FinancialInputState
from packages.finance.marketplace_policy import (
    MARKETPLACE_SIGN_POLICIES,
    NON_NEGATIVE_RAW,
    MarketplaceEvidence,
    MarketplaceSignPolicy,
    marketplace_component_input,
    unresolved_reason,
)
from packages.wb_core.contracts import FINANCE_DETAIL_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import synthetic_scope

OPERATIONAL_DATE = date(2026, 9, 2)
RETRIEVED_AT = datetime(2026, 9, 3, 6, 0, tzinfo=UTC)
OBJECT_ID = "b" * 64

CONFIRMED_FIELDS = sorted(
    policy.source_field
    for policy in MARKETPLACE_SIGN_POLICIES.values()
    if policy.evidence is MarketplaceEvidence.CONFIRMED
)


def _raw_object(rows: list[dict[str, object]]) -> RawObject:
    return RawObject(
        object_id=OBJECT_ID,
        scope=synthetic_scope(),
        endpoint=FINANCE_DETAIL_ENDPOINT,
        object_type=FINANCE_DETAIL_ENDPOINT.object_type,
        source=FINANCE_DETAIL_ENDPOINT.source,
        retrieved_at=RETRIEVED_AT,
        operational_date=OPERATIONAL_DATE,
        request_scope={"dateFrom": OPERATIONAL_DATE.isoformat(), "dateTo": OPERATIONAL_DATE.isoformat()},
        payload={"data": rows},
        schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
    )


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "rrdId": "777",
        "rrDate": "2026-09-02",
        "saleDt": "2026-09-02",
        "nmId": 1001,
        "quantity": "1",
        "retailAmount": "1000.00",
        "currency": "RUB",
        "sellerOperName": "Продажа",
        "docTypeName": "Продажа",
    }
    row.update(overrides)
    return row


def _charge(source_field: str, value: object) -> tuple[object, CanonicalSourceMoney]:
    """Normalize one row and return its record plus the charge for ``source_field``."""

    record = normalize_finance_detail(_raw_object([_row(**{source_field: value})]))[0]
    charge = next(item for item in record.marketplace_charges if item.source_field == source_field)
    return record, charge


@pytest.mark.parametrize("source_field", CONFIRMED_FIELDS)
def test_documented_positive_magnitude_becomes_negative_component(source_field: str) -> None:
    record, charge = _charge(source_field, "198.00")
    component = marketplace_component_input(charge, record)
    policy = MARKETPLACE_SIGN_POLICIES[source_field]

    assert component is not None
    assert component.component is policy.component
    assert component.state is FinancialInputState.PROVIDED
    assert component.amount == Decimal("-198.00")
    assert isinstance(component.amount, Decimal)


@pytest.mark.parametrize("source_field", CONFIRMED_FIELDS)
def test_source_declared_zero_stays_zero(source_field: str) -> None:
    record, charge = _charge(source_field, "0")
    component = marketplace_component_input(charge, record)

    assert component is not None
    assert component.state is FinancialInputState.PROVIDED
    assert component.amount == Decimal("0")


@pytest.mark.parametrize("source_field", CONFIRMED_FIELDS)
def test_contradicting_sign_is_retained_not_repaired(source_field: str) -> None:
    """A negative magnitude is the one case ``abs()`` would hide: it must stay visible."""

    record, charge = _charge(source_field, "-20.00")
    component = marketplace_component_input(charge, record)

    assert component is not None
    assert component.state is FinancialInputState.UNRESOLVED
    assert component.amount == Decimal("-20.00")
    assert "negative" in unresolved_reason(component.component, component.amount)


@pytest.mark.parametrize("source_field", CONFIRMED_FIELDS)
def test_component_carries_source_provenance(source_field: str) -> None:
    record, charge = _charge(source_field, "10.05")
    component = marketplace_component_input(charge, record)

    assert component is not None
    assert component.source == record.source_metadata.source
    assert component.source_endpoint == record.source_metadata.endpoint_name
    assert component.source_record_id == "777"
    assert component.operational_date == OPERATIONAL_DATE
    assert component.financial_date == date(2026, 9, 2)


def test_decimal_precision_survives_the_sign_rule() -> None:
    record, charge = _charge("ppvzSalesCommission", "0.10")
    first = marketplace_component_input(charge, record)
    record, charge = _charge("acquiringFee", "0.20")
    second = marketplace_component_input(charge, record)

    assert first is not None and second is not None
    assert first.amount + second.amount == Decimal("-0.30")


def test_rebill_logistics_is_admitted_as_a_seller_charge() -> None:
    """The source books it as negative revenue: ``vw = -rebillLogisticCost / 1.22`` on every real row."""

    record, charge = _charge("rebillLogisticCost", "75.60")
    component = marketplace_component_input(charge, record)
    policy = MARKETPLACE_SIGN_POLICIES["rebillLogisticCost"]

    assert policy.participates_in_pnl is True
    assert policy.evidence is MarketplaceEvidence.CONFIRMED
    assert "vw = -rebillLogisticCost/1.22" in policy.reason
    assert component is not None
    assert component.component is FinancialComponent.REBILL_LOGISTICS
    assert component.state is FinancialInputState.PROVIDED
    assert component.amount == Decimal("-75.60")


def test_immaterial_zero_of_an_unresolved_component_does_not_block_the_period() -> None:
    """A future unproven charge must not hold a period partial over a zero amount."""

    synthetic = MarketplaceSignPolicy(
        source_field="someUnprovenCharge",
        component=FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS,
        participates_in_pnl=False,
        evidence=MarketplaceEvidence.UNRESOLVED,
        expected_raw_sign=NON_NEGATIVE_RAW,
        canonical_sign="not admitted into the authoritative P&L",
        reason="direction not proven",
    )
    record, charge = _charge("deduction", "0")
    charge = charge.model_copy(update={"source_field": "someUnprovenCharge"})

    with patch.dict(MARKETPLACE_SIGN_POLICIES, {"someUnprovenCharge": synthetic}):
        assert marketplace_component_input(charge, record) is None
        nonzero = charge.model_copy(update={"value": Decimal("4.00")})
        admitted = marketplace_component_input(nonzero, record)
        assert admitted is not None
        assert admitted.state is FinancialInputState.UNRESOLVED
        assert admitted.amount == Decimal("4.00")


def test_field_without_policy_produces_no_component() -> None:
    record = normalize_finance_detail(_raw_object([_row()]))[0]
    charge = CanonicalSourceMoney(
        source_field="someFutureWbField",
        raw_path="someFutureWbField",
        state=CanonicalInputState.VALUE,
        value_kind=CanonicalValueKind.STRING,
        value=Decimal("55.00"),
    )

    assert marketplace_component_input(charge, record) is None


def test_policy_table_covers_only_marketplace_components() -> None:
    admitted = {
        FinancialComponent.MARKETPLACE_COMMISSION,
        FinancialComponent.LOGISTICS,
        FinancialComponent.STORAGE,
        FinancialComponent.ACCEPTANCE,
        FinancialComponent.ACQUIRING,
        FinancialComponent.PENALTIES,
        FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS,
        FinancialComponent.REBILL_LOGISTICS,
    }

    assert len(MARKETPLACE_SIGN_POLICIES) == 11
    assert {policy.component for policy in MARKETPLACE_SIGN_POLICIES.values()} == admitted
    assert all(policy.canonical_sign == "negative or zero" for policy in MARKETPLACE_SIGN_POLICIES.values())
    assert all(policy.expected_raw_sign == "non-negative magnitude" for policy in MARKETPLACE_SIGN_POLICIES.values())
    assert all(policy.participates_in_pnl for policy in MARKETPLACE_SIGN_POLICIES.values())
    assert [
        policy.source_field
        for policy in MARKETPLACE_SIGN_POLICIES.values()
        if policy.evidence is not MarketplaceEvidence.CONFIRMED
    ] == []


def _abs_calls(module: str) -> list[int]:
    """Line numbers of real ``abs()`` calls, so prose about ``abs()`` never trips the guard."""

    root = pathlib.Path(__file__).resolve().parents[2]
    tree = ast.parse((root / module).read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "abs"
    ]


@pytest.mark.parametrize(
    "module",
    [
        "packages/finance/marketplace_policy.py",
        "packages/finance/finance_detail_adapter.py",
        "packages/finance/kernel.py",
        "packages/finance/flow.py",
        "packages/finance/contracts.py",
        "packages/data/normalization.py",
        "packages/data/canonical.py",
    ],
)
def test_marketplace_financial_normalization_never_uses_abs(module: str) -> None:
    """``abs()`` cannot appear in the code path that decides a financial sign.

    A sign repaired by taking an absolute value is indistinguishable from a
    sign that was always correct, which is exactly the failure this slice
    exists to prevent: contradictions must surface as unresolved components.

    The list covers every module that stores, validates or propagates a signed
    amount, not only the modules that currently interpret one: ``contracts.py``
    enforces the negative-expense rule and ``canonical.py`` stores the raw sign
    WB sent, so an ``abs()`` introduced in either would erase the sign upstream
    of the policy that exists to preserve it. Legacy report code is deliberately
    outside this guard: it normalizes charges with ``abs()`` and is not a target
    for repair.
    """

    assert _abs_calls(module) == []


def test_sign_policy_stays_out_of_the_kernel() -> None:
    """The kernel consumes signed components; normalization is not its job."""

    root = pathlib.Path(__file__).resolve().parents[2]
    kernel = (root / "packages" / "finance" / "kernel.py").read_text(encoding="utf-8")

    assert "marketplace_policy" not in kernel
