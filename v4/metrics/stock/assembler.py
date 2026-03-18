"""Stock metrics assembler.

Input: NormalizedBundle.
Output: StockMetricsSection.
Does not compute replenishment strategy and does not depend on other contours.
"""

from __future__ import annotations

from ...core.contracts import (
    MetricStatus,
    MetricValue,
    NormalizedBundle,
    NormalizedStockRecord,
    StockMetricsSection,
)


def _metric(
    value: float | int | None,
    *,
    status: MetricStatus,
    source: str | None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def _source_state(normalized_bundle: NormalizedBundle) -> str:
    status = normalized_bundle.source_statuses.get("stocks")
    if status is None:
        return "missing"
    raw = getattr(status, "status", None)
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw or "missing").strip().lower() or "missing"


def _source_usable(source_state: str) -> bool:
    return source_state in {"ok", "partial"}


def _status_for_source_state(source_state: str) -> MetricStatus:
    if source_state == "partial":
        return MetricStatus.PARTIAL
    return MetricStatus.CONFIRMED


def _stock_source_warnings(normalized_bundle: NormalizedBundle) -> list[str]:
    warnings: list[str] = []
    source_status = normalized_bundle.source_statuses.get("stocks")
    if source_status is not None:
        warnings.extend([f"stocks: {message}" for message in source_status.warnings])

    warnings.extend(
        warning
        for warning in normalized_bundle.warnings
        if "stock" in str(warning).lower()
    )
    return warnings


def _stock_entity_key(record: NormalizedStockRecord, index: int) -> str:
    """Return a stable entity key for distinct stock-item counts.

    Preferred key is nm_id + warehouse + size. If these are not available,
    fallback to record_id, then raw_ref, then index.
    """

    nm_id = str(record.nm_id).strip() if record.nm_id not in (None, "") else None
    warehouse = str(record.warehouse_name).strip() if record.warehouse_name else None
    size = str(record.size).strip() if record.size else None
    if nm_id is not None or warehouse is not None or size is not None:
        return f"nm:{nm_id}|wh:{warehouse}|size:{size}"

    if record.record_id:
        return f"record:{record.record_id}"
    if record.raw_ref:
        return f"raw:{record.raw_ref}"
    return f"idx:{index}"


def _to_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _section_note(source_state: str, warnings: list[str]) -> str | None:
    if not _source_usable(source_state):
        return "stock source unavailable; stock metrics are not computed"
    if source_state == "partial":
        return "stock metrics are partial due to source completeness"
    if warnings:
        return "stock metrics available with warnings"
    return None


def _coverage_note(
    *,
    source_state: str,
    records_count: int,
    missing_quantity_count: int,
) -> str:
    if not _source_usable(source_state):
        return "stock source unavailable"
    if records_count == 0:
        return "stock source returned no records for run"
    if missing_quantity_count > 0:
        return "partial stock quantities"
    return "coverage based on current stock snapshot"


def assemble_stock_metrics(normalized_bundle: NormalizedBundle) -> StockMetricsSection:
    source_state = _source_state(normalized_bundle)
    source_quality = {"stocks": source_state}
    warnings = _stock_source_warnings(normalized_bundle)

    if not _source_usable(source_state):
        unavailable = _metric(
            None,
            status=MetricStatus.UNAVAILABLE,
            source="stocks",
            note="stocks source is unavailable",
        )
        coverage_note = _coverage_note(source_state=source_state, records_count=0, missing_quantity_count=0)
        note = _section_note(source_state, warnings)
        return StockMetricsSection(
            total_stock_units=unavailable,
            in_stock_items_count=unavailable,
            out_of_stock_items_count=unavailable,
            distinct_nm_ids_count=unavailable,
            distinct_warehouses_count=unavailable,
            stock_coverage_note=coverage_note,
            source_quality=source_quality,
            warnings=warnings,
            note=note,
        )

    records = normalized_bundle.stocks
    if not records:
        warnings.append("stocks source has no records for this run")
        no_data_status = MetricStatus.PARTIAL if source_state == "partial" else MetricStatus.UNAVAILABLE
        unavailable = _metric(
            None,
            status=no_data_status,
            source="stocks",
            note="stock records are unavailable for this run",
        )
        coverage_note = _coverage_note(source_state=source_state, records_count=0, missing_quantity_count=0)
        note = _section_note(source_state, warnings)
        return StockMetricsSection(
            total_stock_units=unavailable,
            in_stock_items_count=unavailable,
            out_of_stock_items_count=unavailable,
            distinct_nm_ids_count=unavailable,
            distinct_warehouses_count=unavailable,
            stock_coverage_note=coverage_note,
            source_quality=source_quality,
            warnings=warnings,
            note=note,
        )

    quantity_values: list[float] = []
    missing_quantity_count = 0
    missing_nm_count = 0
    missing_warehouse_count = 0

    entity_state: dict[str, dict[str, bool]] = {}
    distinct_nm_ids: set[str] = set()
    distinct_warehouses: set[str] = set()

    for index, record in enumerate(records):
        key = _stock_entity_key(record, index)
        if key not in entity_state:
            entity_state[key] = {"has_positive": False, "has_non_positive": False, "has_known": False}

        nm_id = str(record.nm_id).strip() if record.nm_id not in (None, "") else None
        warehouse_name = str(record.warehouse_name).strip() if record.warehouse_name else None
        if nm_id:
            distinct_nm_ids.add(nm_id)
        else:
            missing_nm_count += 1
        if warehouse_name:
            distinct_warehouses.add(warehouse_name)
        else:
            missing_warehouse_count += 1

        quantity = _to_float(record.quantity)
        if quantity is None:
            missing_quantity_count += 1
            continue

        quantity_values.append(quantity)
        entity_state[key]["has_known"] = True
        if quantity > 0:
            entity_state[key]["has_positive"] = True
        else:
            entity_state[key]["has_non_positive"] = True

    if missing_quantity_count > 0:
        warnings.append("stock records contain missing quantity values")
    if missing_nm_count > 0:
        warnings.append("stock records contain missing nm_id values")
    if missing_warehouse_count > 0:
        warnings.append("stock records contain missing warehouse_name values")

    total_stock_units_status = _status_for_source_state(source_state)
    total_stock_units_note = None
    total_stock_units_value: float | None
    if quantity_values:
        total_stock_units_value = round(sum(quantity_values), 6)
        if missing_quantity_count > 0:
            total_stock_units_status = MetricStatus.PARTIAL
            total_stock_units_note = "total stock is based on rows with known quantities only"
    else:
        total_stock_units_value = None
        total_stock_units_status = MetricStatus.PARTIAL
        total_stock_units_note = "stock quantities are unavailable in source rows"

    in_stock_count = sum(1 for state in entity_state.values() if state["has_positive"])
    out_of_stock_count = sum(
        1
        for state in entity_state.values()
        if not state["has_positive"] and state["has_known"] and state["has_non_positive"]
    )

    entity_status = _status_for_source_state(source_state)
    entity_note = None
    if missing_quantity_count > 0:
        entity_status = MetricStatus.PARTIAL
        entity_note = "entities with missing quantity are excluded from stock-state counts"

    distinct_nm_status = _status_for_source_state(source_state)
    distinct_nm_note = None
    distinct_nm_value: int | None = len(distinct_nm_ids) if distinct_nm_ids else None
    if distinct_nm_value is None:
        distinct_nm_status = MetricStatus.PARTIAL
        distinct_nm_note = "nm_id is missing in source rows"
    elif missing_nm_count > 0:
        distinct_nm_status = MetricStatus.PARTIAL
        distinct_nm_note = "distinct nm_id count is partial due to missing nm_id rows"

    distinct_warehouse_status = _status_for_source_state(source_state)
    distinct_warehouse_note = None
    distinct_warehouse_value: int | None = len(distinct_warehouses) if distinct_warehouses else None
    if distinct_warehouse_value is None:
        distinct_warehouse_status = MetricStatus.PARTIAL
        distinct_warehouse_note = "warehouse_name is missing in source rows"
    elif missing_warehouse_count > 0:
        distinct_warehouse_status = MetricStatus.PARTIAL
        distinct_warehouse_note = "distinct warehouse count is partial due to missing warehouse rows"

    coverage_note = _coverage_note(
        source_state=source_state,
        records_count=len(records),
        missing_quantity_count=missing_quantity_count,
    )
    note = _section_note(source_state, warnings)

    return StockMetricsSection(
        total_stock_units=_metric(
            total_stock_units_value,
            status=total_stock_units_status,
            source="stocks",
            note=total_stock_units_note,
        ),
        in_stock_items_count=_metric(
            in_stock_count,
            status=entity_status,
            source="stocks",
            note=entity_note,
        ),
        out_of_stock_items_count=_metric(
            out_of_stock_count,
            status=entity_status,
            source="stocks",
            note=entity_note,
        ),
        distinct_nm_ids_count=_metric(
            distinct_nm_value,
            status=distinct_nm_status,
            source="stocks",
            note=distinct_nm_note,
        ),
        distinct_warehouses_count=_metric(
            distinct_warehouse_value,
            status=distinct_warehouse_status,
            source="stocks",
            note=distinct_warehouse_note,
        ),
        stock_coverage_note=coverage_note,
        source_quality=source_quality,
        warnings=warnings,
        note=note,
    )


def build(payload: NormalizedBundle | None = None) -> StockMetricsSection:
    """Back-compat alias for stage-1 naming."""

    if payload is None:
        return StockMetricsSection()
    return assemble_stock_metrics(payload)

