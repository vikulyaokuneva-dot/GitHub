"""Pure Stage 8 mapping from canonical finance detail to Finance Kernel input."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from packages.data.canonical import (
    CanonicalCurrency,
    CanonicalFinanceDetailRecord,
    CanonicalInputState,
    FinancialRecordClassification,
)

from .contracts import (
    FinancialComponent,
    FinancialComponentInput,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInput,
    FinancialInputState,
    RevenueBasis,
    RevenueBasisInput,
)
from .marketplace_policy import (
    MARKETPLACE_SIGN_POLICIES,
    marketplace_component_input,
    unresolved_reason,
)


class FinanceDetailInputBuildResult(BaseModel):
    """Explicitly records whether canonical finance records can form a kernel input."""

    model_config = ConfigDict(frozen=True)

    financial_input: FinancialInput | None = None
    diagnostics: tuple[str, ...] = ()


def _record_has_durable_id(record: CanonicalFinanceDetailRecord) -> bool:
    return record.source_record_id_input.state == CanonicalInputState.VALUE


def build_financial_input_from_finance_detail(
    records: tuple[CanonicalFinanceDetailRecord, ...],
) -> FinanceDetailInputBuildResult:
    """Build a period Finance Kernel input from confirmed finance-sale records only."""

    if not records:
        return FinanceDetailInputBuildResult(diagnostics=("finance detail records are absent",))

    first = records[0]
    diagnostics: list[str] = []
    if any(record.source_metadata.scope != first.source_metadata.scope for record in records):
        return FinanceDetailInputBuildResult(diagnostics=("finance detail records have mixed tenant/account scope",))
    if any(record.operational_date != first.operational_date for record in records):
        return FinanceDetailInputBuildResult(diagnostics=("finance detail records have mixed operational dates",))
    if any(record.currency != CanonicalCurrency.RUB for record in records):
        return FinanceDetailInputBuildResult(
            diagnostics=("finance detail currency is missing or not an explicit RUB source value",)
        )

    charge_components: list[FinancialComponentInput] = []
    revenue_components: list[FinancialComponentInput] = []
    revenue_views: list[RevenueBasisInput] = []
    finality: list[FinancialFinalityInput] = []
    unapproved_totals: dict[str, Decimal] = {}
    unresolved_facts: dict[FinancialComponent, list[object]] = {}
    for record in records:
        # Marketplace charges are reported on their own rows ("Логистика",
        # "Хранение", "Обработка товара"), so they are read from every record;
        # only revenue stays gated on a classified financial sale.
        for charge in record.marketplace_charges:
            if charge.source_field not in MARKETPLACE_SIGN_POLICIES:
                diagnostics.append(f"{charge.source_field} has no approved marketplace sign policy")
                continue
            component = marketplace_component_input(charge, record)
            if component is None:
                continue
            charge_components.append(component)
            if component.state is FinancialInputState.UNRESOLVED:
                fact = unresolved_facts.setdefault(component.component, [0, Decimal("0")])
                fact[0] += 1
                fact[1] += component.amount or Decimal("0")
        for charge in record.unapproved_money_fields:
            if charge.value is None:
                continue
            unapproved_totals[charge.source_field] = unapproved_totals.get(
                charge.source_field, Decimal("0")
            ) + charge.value
        if record.classification != FinancialRecordClassification.FINANCIAL_SALE:
            if record.retail_amount is not None and record.retail_amount != 0:
                diagnostics.append(
                    f"retailAmount excluded from realized revenue for non-sale record {record.source_record_id}"
                )
            continue
        if not _record_has_durable_id(record):
            diagnostics.append(
                f"financial sale {record.source_record_id} lacks rrdId and is excluded from authoritative revenue"
            )
            continue
        if record.retail_amount_input.state != CanonicalInputState.VALUE or record.retail_amount is None:
            diagnostics.append(f"financial sale {record.source_record_id} has missing retailAmount")
            continue

        revenue_components.append(
            FinancialComponentInput(
                component=FinancialComponent.REALIZED_REVENUE,
                state=FinancialInputState.PROVIDED,
                amount=record.retail_amount,
                source_endpoint=record.source_metadata.endpoint_name,
                source=record.source_metadata.source,
                source_record_id=record.source_record_id,
                operational_date=record.operational_date,
                financial_date=record.financial_date,
            )
        )
        quantity = record.quantity
        if quantity is not None and quantity < 0:
            diagnostics.append(
                f"financial sale {record.source_record_id} has a negative quantity; "
                "revenue views are not derived from a contradicted source value"
            )
        if quantity is not None and quantity > 0:
            revenue_views.append(
                RevenueBasisInput(
                    basis=RevenueBasis.REALIZED_GROSS,
                    amount=record.retail_amount,
                    quantity=int(quantity),
                    source_field="retailAmount",
                    source=record.source_metadata.source,
                    source_record_id=record.source_record_id,
                    operational_date=record.operational_date,
                    financial_date=record.financial_date,
                )
            )
            if record.buyer_discounted_price is not None:
                revenue_views.append(
                    RevenueBasisInput(
                        basis=RevenueBasis.BUYER_DISCOUNTED,
                        amount=record.buyer_discounted_price * quantity,
                        quantity=int(quantity),
                        source_field="retailPriceWithDiscRub",
                        source=record.source_metadata.source,
                        source_record_id=record.source_record_id,
                        operational_date=record.operational_date,
                        financial_date=record.financial_date,
                    )
                )
            if record.seller_payout is not None:
                revenue_views.append(
                    RevenueBasisInput(
                        basis=RevenueBasis.SELLER_PAYOUT,
                        amount=record.seller_payout,
                        quantity=int(quantity),
                        source_field="ppvzForPay",
                        source=record.source_metadata.source,
                        source_record_id=record.source_record_id,
                        operational_date=record.operational_date,
                        financial_date=record.financial_date,
                    )
                )
        else:
            diagnostics.append(f"financial sale {record.source_record_id} has no positive quantity for revenue views")
        finality.append(
            FinancialFinalityInput(
                finality=FinancialFinality.UNKNOWN,
                evidence_code="finance_detail_has_no_explicit_finality_signal",
                source=record.source_metadata.source,
                source_record_id=record.source_record_id,
                operational_date=record.operational_date,
                financial_date=record.financial_date,
            )
        )

    for component, (rows, total) in sorted(
        unresolved_facts.items(), key=lambda item: item[0].value
    ):
        diagnostics.append(
            f"{component.value} is excluded from the authoritative P&L ({rows} source rows, {total} total): "
            f"{unresolved_reason(component, total)}"
        )
    for source_field, total in sorted(unapproved_totals.items()):
        diagnostics.append(
            f"{source_field} is reported by WB with amount {total} but has no approved P&L "
            "policy; it is excluded, not zeroed"
        )
    if not revenue_components:
        return FinanceDetailInputBuildResult(diagnostics=tuple(diagnostics or ["no classified financial sales available"]))
    return FinanceDetailInputBuildResult(
        financial_input=FinancialInput(
            scope=first.source_metadata.scope,
            operational_date=first.operational_date,
            currency=CanonicalCurrency.RUB,
            reconciled_facts=(),
            components=tuple(revenue_components) + tuple(charge_components),
            revenue_views=tuple(revenue_views),
            finality=tuple(finality),
        ),
        diagnostics=tuple(diagnostics),
    )
