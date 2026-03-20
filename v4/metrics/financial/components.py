"""Realization component classification for expanded financial contour.

Input: NormalizedBundle (realization records only).
Output: FinancialComponentTotals with separated cost buckets.
Does not compute KPI rollups or render outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.contracts import MetricStatus, NormalizedBundle, NormalizedRealizationRecord


COMMISSION_KEYWORDS = ("комисс", "commission", "вознаграждени")
ACQUIRING_KEYWORDS = ("эквайр", "acquiring", "платеж", "платёж")
PVZ_KEYWORDS = ("пвз", "pvz", "выдач", "pickup")
PENALTY_KEYWORDS = ("штраф", "penalty", "fine")
LOGISTICS_KEYWORDS = ("логист", "достав", "перевоз", "transport")
STORAGE_KEYWORDS = ("хранен", "storage")
ACCEPTANCE_KEYWORDS = ("приемк", "приёмк", "acceptance")
PAID_ACCEPTANCE_KEYWORDS = ("платная приемк", "платная приёмк", "paid acceptance")
DEDUCTION_KEYWORDS = ("удерж", "deduct", "лояль", "bonus", "балл")


# Keep both readable RU aliases and legacy mojibake aliases for robustness
# across different payload encodings.
COMMISSION_KEYWORDS = COMMISSION_KEYWORDS + ("комисс", "вознаграждени")
ACQUIRING_KEYWORDS = ACQUIRING_KEYWORDS + ("эквайр", "платеж", "платёж")
PVZ_KEYWORDS = PVZ_KEYWORDS + ("пвз", "выдач")
PENALTY_KEYWORDS = PENALTY_KEYWORDS + ("штраф",)
LOGISTICS_KEYWORDS = LOGISTICS_KEYWORDS + ("логист", "достав", "перевоз")
STORAGE_KEYWORDS = STORAGE_KEYWORDS + ("хранен",)
ACCEPTANCE_KEYWORDS = ACCEPTANCE_KEYWORDS + ("приемк", "приёмк")
PAID_ACCEPTANCE_KEYWORDS = PAID_ACCEPTANCE_KEYWORDS + ("платная приемк", "платная приёмк")
DEDUCTION_KEYWORDS = DEDUCTION_KEYWORDS + ("удерж", "лояль", "балл")


@dataclass(frozen=True)
class FinancialComponentTotals:
    """Classified realization totals used by financial assembler."""

    sales_amount: float | None
    seller_payout: float | None
    logistics_cost: float | None
    storage_cost: float | None
    deductions_amount: float | None
    commission_amount: float | None
    acquiring_amount: float | None
    pvz_amount: float | None
    penalties_amount: float | None
    acceptance_amount: float | None
    paid_acceptance_amount: float | None
    other_costs_amount: float | None
    revenue_gross: float | None
    warnings: list[str] = field(default_factory=list)
    component_quality: dict[str, str] = field(default_factory=dict)


def _source_state(bundle: NormalizedBundle, source_name: str) -> str:
    status = bundle.source_statuses.get(source_name)
    if status is None:
        return "missing"
    state = getattr(status, "status", None)
    if hasattr(state, "value"):
        return str(state.value)
    return str(state or "missing").strip().lower() or "missing"


def _source_usable(state: str) -> bool:
    return state in {"ok", "partial"}


def _label(record: NormalizedRealizationRecord) -> str:
    return str(record.operation_label or "").strip().lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _filter_by_date(records: list[NormalizedRealizationRecord], actual_date: str | None) -> list[NormalizedRealizationRecord]:
    if not actual_date:
        return []
    return [record for record in records if record.event_date == actual_date]


def _finalize_component(
    *,
    values: list[float],
    missing_amount_count: int,
    source_state: str,
    ambiguous_count: int,
    allow_zero: bool,
    labels_required: bool,
    labels_available: bool,
) -> tuple[float | None, str]:
    if not _source_usable(source_state):
        return None, MetricStatus.UNAVAILABLE.value

    if values:
        total = sum(values)
        status = MetricStatus.CONFIRMED.value
        if source_state == "partial" or missing_amount_count > 0 or ambiguous_count > 0:
            status = MetricStatus.PARTIAL.value
        return total, status

    if missing_amount_count > 0:
        return None, MetricStatus.PARTIAL.value

    if labels_required and not labels_available:
        return None, MetricStatus.PARTIAL.value

    if allow_zero:
        status = MetricStatus.CONFIRMED.value
        if source_state == "partial" or ambiguous_count > 0:
            status = MetricStatus.PARTIAL.value
        return 0.0, status

    return None, MetricStatus.UNAVAILABLE.value


def _normalize_cost(value: float | None) -> float | None:
    if value is None:
        return None
    return abs(float(value))


def _classify_cost_bucket(record: NormalizedRealizationRecord) -> tuple[str | None, bool]:
    """Classify one realization record into one fallback cost bucket."""

    event_type = str(record.event_type or "other").strip().lower()
    text = _label(record)

    if event_type in {"sale", "return"}:
        return None, False

    if event_type == "logistics" or _contains_any(text, LOGISTICS_KEYWORDS):
        return "logistics", False
    if event_type == "storage" or _contains_any(text, STORAGE_KEYWORDS):
        return "storage", False
    if _contains_any(text, COMMISSION_KEYWORDS):
        return "commission", False
    if _contains_any(text, ACQUIRING_KEYWORDS):
        return "acquiring", False
    if _contains_any(text, PVZ_KEYWORDS):
        return "pvz", False
    if _contains_any(text, PENALTY_KEYWORDS):
        return "penalties", False
    if _contains_any(text, PAID_ACCEPTANCE_KEYWORDS):
        return "paid_acceptance", False
    if _contains_any(text, ACCEPTANCE_KEYWORDS):
        return "acceptance", False

    if event_type == "deduction":
        # WB deduction events are a valid deductions bucket even without
        # operation_label granularity.
        return "deductions", False

    if event_type == "other":
        if _contains_any(text, DEDUCTION_KEYWORDS):
            return "deductions", False
        return "other_costs", False

    return "other_costs", True


def _record_component_value(record: NormalizedRealizationRecord, bucket: str) -> float | None:
    mapping: dict[str, float | None] = {
        "commission": record.commission_amount,
        "acquiring": record.acquiring_amount,
        "logistics": record.logistics_amount,
        "storage": record.storage_amount,
        "deductions": record.deductions_component_amount,
        "pvz": None,  # PVZ is label-driven in current payload contract.
        "penalties": record.penalties_amount,
        "acceptance": record.acceptance_amount,
        "paid_acceptance": record.paid_acceptance_amount,
        "other_costs": record.other_costs_amount,
    }
    return _normalize_cost(mapping.get(bucket))


def classify_realization_components(
    normalized_bundle: NormalizedBundle,
    *,
    actual_date: str | None = None,
) -> FinancialComponentTotals:
    """Classify realization events into financial component totals.

    Rules:
    - prefer explicit normalized component fields from normalization,
    - fallback to event_type + operation_label + amount only when needed,
    - each fallback record is counted in exactly one bucket.
    """

    source_state = _source_state(normalized_bundle, "realization")
    warnings: list[str] = []

    keys = [
        "revenue",
        "payout",
        "commission",
        "acquiring",
        "logistics",
        "storage",
        "deductions",
        "pvz",
        "penalties",
        "acceptance",
        "paid_acceptance",
        "other_costs",
    ]
    unavailable_quality = {key: MetricStatus.UNAVAILABLE.value for key in keys}

    if not _source_usable(source_state):
        return FinancialComponentTotals(
            sales_amount=None,
            seller_payout=None,
            logistics_cost=None,
            storage_cost=None,
            deductions_amount=None,
            commission_amount=None,
            acquiring_amount=None,
            pvz_amount=None,
            penalties_amount=None,
            acceptance_amount=None,
            paid_acceptance_amount=None,
            other_costs_amount=None,
            revenue_gross=None,
            warnings=warnings,
            component_quality=unavailable_quality,
        )

    realization_records = _filter_by_date(normalized_bundle.realization, actual_date)
    if not realization_records:
        warnings.append("no realization records for selected actual date")

    labels_available = any(_label(record) for record in realization_records)

    sale_values: list[float] = []
    payout_values: list[float] = []
    revenue_values: list[float] = []
    sale_missing_count = 0
    payout_missing_count = 0

    bucket_values: dict[str, list[float]] = {
        "logistics": [],
        "storage": [],
        "deductions": [],
        "commission": [],
        "acquiring": [],
        "pvz": [],
        "penalties": [],
        "acceptance": [],
        "paid_acceptance": [],
        "other_costs": [],
    }
    bucket_missing_counts = {bucket: 0 for bucket in bucket_values}
    bucket_ambiguous_counts = {bucket: 0 for bucket in bucket_values}

    for record in realization_records:
        amount = record.amount
        event_type = str(record.event_type or "other").strip().lower()
        label_text = _label(record)

        if event_type == "sale":
            revenue_amount = record.revenue_amount if record.revenue_amount is not None else amount
            payout_amount = record.payout_amount if record.payout_amount is not None else amount
            if revenue_amount is None:
                sale_missing_count += 1
                warnings.append(f"sale event without revenue amount: {record.raw_ref or record.record_id or 'unknown'}")
            else:
                sale_values.append(float(revenue_amount))
                revenue_values.append(float(revenue_amount))
            if payout_amount is None:
                payout_missing_count += 1
                warnings.append(f"sale event without payout amount: {record.raw_ref or record.record_id or 'unknown'}")
            else:
                payout_values.append(float(payout_amount))
            continue

        if event_type == "return":
            payout_amount = record.payout_amount if record.payout_amount is not None else amount
            if payout_amount is None:
                payout_missing_count += 1
                warnings.append(f"return event without payout amount: {record.raw_ref or record.record_id or 'unknown'}")
            else:
                payout_values.append(float(payout_amount))
            continue

        explicit_used = False
        for bucket in (
            "commission",
            "acquiring",
            "logistics",
            "storage",
            "deductions",
            "penalties",
            "acceptance",
            "paid_acceptance",
            "other_costs",
        ):
            value = _record_component_value(record, bucket)
            if value is None:
                continue
            explicit_used = True
            bucket_values[bucket].append(value)

        if _contains_any(label_text, PVZ_KEYWORDS):
            pvz_value = _normalize_cost(record.amount)
            if pvz_value is not None:
                explicit_used = True
                bucket_values["pvz"].append(pvz_value)

        if explicit_used:
            if record.payout_amount is not None:
                payout_values.append(float(record.payout_amount))
            continue

        bucket, ambiguous = _classify_cost_bucket(record)
        if bucket is None:
            continue

        if ambiguous:
            bucket_ambiguous_counts[bucket] += 1
            warnings.append(
                f"ambiguous realization event classified as {bucket}: "
                f"{record.raw_ref or record.record_id or 'unknown'}"
            )

        if amount is None:
            bucket_missing_counts[bucket] += 1
            warnings.append(
                f"realization event has no amount for bucket={bucket}: "
                f"{record.raw_ref or record.record_id or 'unknown'}"
            )
            continue

        bucket_values[bucket].append(_normalize_cost(float(amount)) or 0.0)

    sales_amount, sales_quality = _finalize_component(
        values=sale_values,
        missing_amount_count=sale_missing_count,
        source_state=source_state,
        ambiguous_count=0,
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )
    seller_payout, payout_quality = _finalize_component(
        values=payout_values,
        missing_amount_count=payout_missing_count,
        source_state=source_state,
        ambiguous_count=0,
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )
    revenue_gross, revenue_quality = _finalize_component(
        values=revenue_values,
        missing_amount_count=sale_missing_count,
        source_state=source_state,
        ambiguous_count=0,
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )

    logistics_cost, logistics_quality = _finalize_component(
        values=bucket_values["logistics"],
        missing_amount_count=bucket_missing_counts["logistics"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["logistics"],
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )
    storage_cost, storage_quality = _finalize_component(
        values=bucket_values["storage"],
        missing_amount_count=bucket_missing_counts["storage"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["storage"],
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )
    deductions_amount, deductions_quality = _finalize_component(
        values=bucket_values["deductions"],
        missing_amount_count=bucket_missing_counts["deductions"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["deductions"],
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )
    commission_amount, commission_quality = _finalize_component(
        values=bucket_values["commission"],
        missing_amount_count=bucket_missing_counts["commission"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["commission"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    acquiring_amount, acquiring_quality = _finalize_component(
        values=bucket_values["acquiring"],
        missing_amount_count=bucket_missing_counts["acquiring"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["acquiring"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    pvz_amount, pvz_quality = _finalize_component(
        values=bucket_values["pvz"],
        missing_amount_count=bucket_missing_counts["pvz"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["pvz"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    penalties_amount, penalties_quality = _finalize_component(
        values=bucket_values["penalties"],
        missing_amount_count=bucket_missing_counts["penalties"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["penalties"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    acceptance_amount, acceptance_quality = _finalize_component(
        values=bucket_values["acceptance"],
        missing_amount_count=bucket_missing_counts["acceptance"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["acceptance"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    paid_acceptance_amount, paid_acceptance_quality = _finalize_component(
        values=bucket_values["paid_acceptance"],
        missing_amount_count=bucket_missing_counts["paid_acceptance"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["paid_acceptance"],
        allow_zero=True,
        labels_required=True,
        labels_available=labels_available,
    )
    other_costs_amount, other_quality = _finalize_component(
        values=bucket_values["other_costs"],
        missing_amount_count=bucket_missing_counts["other_costs"],
        source_state=source_state,
        ambiguous_count=bucket_ambiguous_counts["other_costs"],
        allow_zero=True,
        labels_required=False,
        labels_available=labels_available,
    )

    if not labels_available and realization_records:
        warnings.append("realization operation labels are missing; fine-grained classification is partial")

    component_quality = {
        "revenue": revenue_quality,
        "payout": payout_quality,
        "commission": commission_quality,
        "acquiring": acquiring_quality,
        "logistics": logistics_quality,
        "storage": storage_quality,
        "deductions": deductions_quality,
        "pvz": pvz_quality,
        "penalties": penalties_quality,
        "acceptance": acceptance_quality,
        "paid_acceptance": paid_acceptance_quality,
        "other_costs": other_quality,
    }

    return FinancialComponentTotals(
        sales_amount=sales_amount,
        seller_payout=seller_payout,
        logistics_cost=logistics_cost,
        storage_cost=storage_cost,
        deductions_amount=deductions_amount,
        commission_amount=commission_amount,
        acquiring_amount=acquiring_amount,
        pvz_amount=pvz_amount,
        penalties_amount=penalties_amount,
        acceptance_amount=acceptance_amount,
        paid_acceptance_amount=paid_acceptance_amount,
        other_costs_amount=other_costs_amount,
        revenue_gross=revenue_gross,
        warnings=warnings,
        component_quality=component_quality,
    )
