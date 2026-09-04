"""Pure reconciliation for the initial canonical operational sales slice."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from decimal import Decimal

from packages.data.canonical import CanonicalCurrency, CanonicalSalesFunnelProduct

from .contracts import (
    CanonicalCohortMetricFact,
    CanonicalSalesConfirmationFact,
    ReconciliationDiagnostic,
    ReconciliationDiagnosticCode,
    ReconciliationIdentity,
    ReconciliationLagState,
    ReconciliationResult,
    ReconciliationRule,
    ReconciliationStatus,
)

OperationalFact = CanonicalSalesFunnelProduct | CanonicalSalesConfirmationFact
AnyFact = OperationalFact | CanonicalCohortMetricFact


def _source_key(fact: AnyFact) -> tuple[str, int]:
    return fact.source_metadata.source_object_id, fact.source_metadata.source_record_index


def _scope_key(fact: AnyFact) -> tuple[str, str]:
    scope = fact.source_metadata.scope
    return str(scope.tenant_id), str(scope.account_id)


def _strong_source_record_id(fact: OperationalFact) -> str:
    metadata = fact.source_metadata
    return f"{metadata.source_object_id}:{metadata.source_record_index}"


def _composite_identity_value(fact: OperationalFact) -> str | None:
    product_identifier = fact.nm_id or fact.seller_sku
    if product_identifier is None:
        return None
    return f"{fact.operational_date.isoformat()}:{product_identifier}"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")


def _result_id(
    *,
    identity: ReconciliationIdentity,
    sales_facts: tuple[CanonicalSalesFunnelProduct, ...],
    confirmation_facts: tuple[CanonicalSalesConfirmationFact, ...],
    cohort_facts: tuple[CanonicalCohortMetricFact, ...],
) -> str:
    value = {
        "identity": identity.model_dump(mode="json"),
        "sales_facts": [fact.model_dump(mode="json") for fact in sales_facts],
        "confirmation_facts": [fact.model_dump(mode="json") for fact in confirmation_facts],
        "cohort_facts": [fact.model_dump(mode="json") for fact in cohort_facts],
    }
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_single_scope(facts: tuple[AnyFact, ...]) -> None:
    scopes = {_scope_key(fact) for fact in facts}
    if len(scopes) > 1:
        raise ValueError("reconciliation inputs must belong to exactly one tenant/account scope")


def _same_product(left: OperationalFact, right: OperationalFact | CanonicalCohortMetricFact) -> bool:
    if left.nm_id is not None and right.nm_id is not None:
        return left.nm_id == right.nm_id
    if left.seller_sku is not None and right.seller_sku is not None:
        return left.seller_sku == right.seller_sku
    return False


def _matching_confirmations(
    sales_fact: CanonicalSalesFunnelProduct,
    confirmations: tuple[CanonicalSalesConfirmationFact, ...],
) -> tuple[ReconciliationRule, tuple[CanonicalSalesConfirmationFact, ...]]:
    strong_matches = tuple(
        fact for fact in confirmations if fact.source_event_id == _strong_source_record_id(sales_fact)
    )
    if strong_matches:
        return ReconciliationRule.STRONG_SOURCE_RECORD_ID, strong_matches
    composite_matches = tuple(
        fact
        for fact in confirmations
        if fact.operational_date == sales_fact.operational_date
        and _scope_key(fact) == _scope_key(sales_fact)
        and _same_product(sales_fact, fact)
    )
    if composite_matches:
        return ReconciliationRule.COMPOSITE_OPERATIONAL_DATE_AND_PRODUCT, composite_matches
    return ReconciliationRule.STRONG_SOURCE_RECORD_ID, ()


def _matching_cohort_facts(
    anchor: OperationalFact, cohort_facts: tuple[CanonicalCohortMetricFact, ...]
) -> tuple[CanonicalCohortMetricFact, ...]:
    return tuple(
        fact
        for fact in cohort_facts
        if fact.operational_date == anchor.operational_date
        and _scope_key(fact) == _scope_key(anchor)
        and _same_product(anchor, fact)
    )


def _values[T](facts: tuple[OperationalFact, ...], field_name: str) -> set[T]:
    return {getattr(fact, field_name) for fact in facts if getattr(fact, field_name) is not None}


def _diagnostics(
    *,
    rule: ReconciliationRule,
    sales_facts: tuple[CanonicalSalesFunnelProduct, ...],
    confirmation_facts: tuple[CanonicalSalesConfirmationFact, ...],
    cohort_facts: tuple[CanonicalCohortMetricFact, ...],
    status: ReconciliationStatus,
) -> tuple[ReconciliationDiagnostic, ...]:
    operational_facts: tuple[OperationalFact, ...] = (*sales_facts, *confirmation_facts)
    source_ids = tuple(
        sorted({fact.source_metadata.source_object_id for fact in (*operational_facts, *cohort_facts)})
    )
    diagnostics: list[ReconciliationDiagnostic] = []
    if sales_facts and confirmation_facts:
        diagnostics.append(
            ReconciliationDiagnostic(
                code=(
                    ReconciliationDiagnosticCode.STRONG_IDENTITY_MATCH
                    if rule == ReconciliationRule.STRONG_SOURCE_RECORD_ID
                    else ReconciliationDiagnosticCode.COMPOSITE_IDENTITY_MATCH
                ),
                rule=rule,
                source_object_ids=source_ids,
            )
        )
    if status == ReconciliationStatus.UNMATCHED:
        diagnostics.append(
            ReconciliationDiagnostic(
                code=ReconciliationDiagnosticCode.SINGLE_SOURCE_FACT,
                rule=rule,
                source_object_ids=source_ids,
            )
        )
    if any(fact.quantity is None for fact in operational_facts):
        diagnostics.append(
            ReconciliationDiagnostic(
                code=ReconciliationDiagnosticCode.MISSING_QUANTITY,
                field_name="quantity",
                source_object_ids=source_ids,
            )
        )
    if any(fact.source_amount is None for fact in operational_facts):
        diagnostics.append(
            ReconciliationDiagnostic(
                code=ReconciliationDiagnosticCode.MISSING_AMOUNT,
                field_name="source_amount",
                source_object_ids=source_ids,
            )
        )
    for field_name, code in (
        ("quantity", ReconciliationDiagnosticCode.QUANTITY_CONFLICT),
        ("source_amount", ReconciliationDiagnosticCode.AMOUNT_CONFLICT),
        ("currency", ReconciliationDiagnosticCode.CURRENCY_CONFLICT),
    ):
        if len(_values(operational_facts, field_name)) > 1:
            diagnostics.append(
                ReconciliationDiagnostic(code=code, field_name=field_name, source_object_ids=source_ids)
            )
    if cohort_facts:
        diagnostics.append(
            ReconciliationDiagnostic(
                code=ReconciliationDiagnosticCode.COHORT_METRIC_RETAINED,
                source_object_ids=source_ids,
            )
        )
    diagnostics.append(
        ReconciliationDiagnostic(
            code=ReconciliationDiagnosticCode.FINANCIAL_CONFIRMATION_PENDING,
            source_object_ids=source_ids,
        )
    )
    return tuple(diagnostics)


def _status(
    sales_facts: tuple[CanonicalSalesFunnelProduct, ...],
    confirmation_facts: tuple[CanonicalSalesConfirmationFact, ...],
) -> ReconciliationStatus:
    if not sales_facts or not confirmation_facts:
        return ReconciliationStatus.UNMATCHED
    operational_facts: tuple[OperationalFact, ...] = (*sales_facts, *confirmation_facts)
    if any(len(_values(operational_facts, field_name)) > 1 for field_name in ("quantity", "source_amount", "currency")):
        return ReconciliationStatus.CONFLICT
    if any(fact.quantity is None or fact.source_amount is None for fact in operational_facts):
        return ReconciliationStatus.PARTIAL
    return ReconciliationStatus.MATCHED


def _identity(*, rule: ReconciliationRule, anchor: OperationalFact) -> ReconciliationIdentity:
    value = (
        _strong_source_record_id(anchor)
        if rule == ReconciliationRule.STRONG_SOURCE_RECORD_ID
        else _composite_identity_value(anchor)
    )
    if value is None:
        raise ValueError("composite reconciliation identity requires nm_id or seller_sku")
    return ReconciliationIdentity(
        scope=anchor.source_metadata.scope,
        rule=rule,
        value=value,
        operational_date=anchor.operational_date,
        nm_id=anchor.nm_id,
        seller_sku=anchor.seller_sku,
    )


def _build_result(
    *,
    rule: ReconciliationRule,
    sales_facts: tuple[CanonicalSalesFunnelProduct, ...],
    confirmation_facts: tuple[CanonicalSalesConfirmationFact, ...],
    cohort_facts: tuple[CanonicalCohortMetricFact, ...],
) -> ReconciliationResult:
    anchor: OperationalFact = sales_facts[0] if sales_facts else confirmation_facts[0]
    identity = _identity(rule=rule, anchor=anchor)
    status = _status(sales_facts, confirmation_facts)
    return ReconciliationResult(
        reconciliation_id=_result_id(
            identity=identity,
            sales_facts=sales_facts,
            confirmation_facts=confirmation_facts,
            cohort_facts=cohort_facts,
        ),
        identity=identity,
        sales_funnel_facts=sales_facts,
        confirmation_facts=confirmation_facts,
        cohort_metric_facts=cohort_facts,
        status=status,
        diagnostics=_diagnostics(
            rule=rule,
            sales_facts=sales_facts,
            confirmation_facts=confirmation_facts,
            cohort_facts=cohort_facts,
            status=status,
        ),
        operational_dates=tuple(
            sorted(
                {fact.operational_date for fact in sales_facts}
                | {fact.operational_date for fact in confirmation_facts}
            )
        ),
        financial_dates=(),
        lag_state=ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION,
    )


def reconcile_sales_funnel_products(
    sales_funnel_facts: Iterable[CanonicalSalesFunnelProduct],
    confirmation_facts: Iterable[CanonicalSalesConfirmationFact] = (),
    cohort_metric_facts: Iterable[CanonicalCohortMetricFact] = (),
) -> tuple[ReconciliationResult, ...]:
    """Reconcile operational source facts by explicit identity, without finance interpretation."""

    sales_facts = tuple(sorted(sales_funnel_facts, key=_source_key))
    confirmations = tuple(sorted(confirmation_facts, key=_source_key))
    cohort_facts = tuple(sorted(cohort_metric_facts, key=_source_key))
    all_facts: tuple[AnyFact, ...] = (*sales_facts, *confirmations, *cohort_facts)
    if not all_facts:
        return ()
    _require_single_scope(all_facts)

    results: list[ReconciliationResult] = []
    used_confirmation_keys: set[tuple[str, int]] = set()
    for sales_fact in sales_facts:
        rule, matches = _matching_confirmations(sales_fact, confirmations)
        matches = tuple(fact for fact in matches if _source_key(fact) not in used_confirmation_keys)
        used_confirmation_keys.update(_source_key(fact) for fact in matches)
        results.append(
            _build_result(
                rule=rule,
                sales_facts=(sales_fact,),
                confirmation_facts=matches,
                cohort_facts=_matching_cohort_facts(sales_fact, cohort_facts),
            )
        )
    for confirmation in confirmations:
        if _source_key(confirmation) in used_confirmation_keys:
            continue
        rule = (
            ReconciliationRule.STRONG_SOURCE_RECORD_ID
            if confirmation.source_event_id is not None
            else ReconciliationRule.COMPOSITE_OPERATIONAL_DATE_AND_PRODUCT
        )
        results.append(
            _build_result(
                rule=rule,
                sales_facts=(),
                confirmation_facts=(confirmation,),
                cohort_facts=_matching_cohort_facts(confirmation, cohort_facts),
            )
        )
    return tuple(sorted(results, key=lambda result: result.reconciliation_id))
