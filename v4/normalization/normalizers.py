"""Normalization adapters from raw ingestion payloads to canonical records.

Input: RawBundle/RawSourcePayload from ingestion layer.
Output: NormalizedBundle and per-source normalized records.
Does not compute KPI and does not aggregate business metrics.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ..core.contracts import (
    NormalizedAdsCampaignRecord,
    NormalizedAdsStatRecord,
    NormalizedBundle,
    NormalizedFunnelRecord,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    NormalizedStockRecord,
    RawBundle,
    RawSourcePayload,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def _coerce_date_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    if re.match(r"^\d{2}\.\d{2}\.\d{4}", text):
        day, month, year = text[:10].split(".")
        return f"{year}-{month}-{day}"
    return text


def _pick_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if value not in (None, ""):
                return value
    return None


def _pick_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _pick_value(row, keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick_float(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in row:
            parsed = _coerce_float(row.get(key))
            if parsed is not None:
                return parsed
    return None


def _pick_date(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in row:
            parsed = _coerce_date_text(row.get(key))
            if parsed is not None:
                return parsed
    return None


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "да", "истина"}:
        return True
    if text in {"0", "false", "no", "n", "нет", "ложь"}:
        return False
    return None


def _extract_rows(raw_source_payload: RawSourcePayload | None) -> list[dict[str, Any]]:
    if raw_source_payload is None:
        return []
    payload = raw_source_payload.payload
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_source_usable(raw_source_payload: RawSourcePayload | None) -> bool:
    if raw_source_payload is None:
        return False
    return raw_source_payload.status.status in (SourceStatusCode.OK, SourceStatusCode.PARTIAL)


def _source_tag(raw_source_payload: RawSourcePayload | None, fallback: str) -> str:
    if raw_source_payload is None:
        return fallback
    return str(raw_source_payload.source_name or fallback)


def _make_raw_ref(prefix: str, index: int, primary_id: Any) -> str:
    if primary_id not in (None, ""):
        return f"{prefix}:{primary_id}"
    return f"{prefix}:{index}"


def normalize_orders_source(raw_source_payload: RawSourcePayload | None) -> list[NormalizedOrderRecord]:
    if not _is_source_usable(raw_source_payload):
        return []

    source_tag = _source_tag(raw_source_payload, "orders")
    records: list[NormalizedOrderRecord] = []
    for index, row in enumerate(_extract_rows(raw_source_payload)):
        record_id = _pick_text(row, ("srid", "odid", "orderId", "orderUID", "gNumber"))
        nm_id = _pick_value(row, ("nmId", "nm_id", "nmid", "nmID"))
        records.append(
            NormalizedOrderRecord(
                record_id=record_id,
                seller_id=_pick_text(row, ("sellerId", "supplierId", "supplierID", "supplierContractCode")),
                nm_id=nm_id,
                subject_name=_pick_text(row, ("subject", "subjectName", "category", "categoryName")),
                quantity=_pick_float(row, ("quantity", "orderQty", "orderCount", "ordersCount", "orders")),
                price=_pick_float(row, ("totalPrice", "priceWithDisc", "finishedPrice", "convertedPrice", "price")),
                order_date=_pick_date(row, ("date", "lastChangeDate", "order_dt", "createdAt")),
                source_tag=source_tag,
                raw_ref=_make_raw_ref("orders", index, record_id),
            )
        )
    return records


def _detect_sales_return(row: dict[str, Any], operation_type: str | None) -> bool | None:
    explicit = _to_bool_or_none(_pick_value(row, ("isReturn", "is_return", "return", "isCancel", "is_cancel")))
    if explicit is not None:
        return explicit

    op = str(operation_type or "").strip().lower()
    if any(token in op for token in ("возврат", "return")):
        return True
    if any(token in op for token in ("продаж", "sale", "реализац")):
        return False

    sale_id = _pick_text(row, ("saleID", "saleId"))
    if sale_id:
        if sale_id.upper().startswith("R"):
            return True
        if sale_id.upper().startswith("S"):
            return False

    return None


def normalize_sales_source(raw_source_payload: RawSourcePayload | None) -> list[NormalizedSaleRecord]:
    if not _is_source_usable(raw_source_payload):
        return []

    source_tag = _source_tag(raw_source_payload, "sales")
    records: list[NormalizedSaleRecord] = []

    for index, row in enumerate(_extract_rows(raw_source_payload)):
        record_id = _pick_text(row, ("saleID", "saleId", "srid", "odid", "gNumber"))
        operation_type = _pick_text(
            row,
            (
                "operationType",
                "operation_type",
                "supplier_oper_name",
                "doc_type_name",
                "saleType",
                "sale_type",
            ),
        )
        records.append(
            NormalizedSaleRecord(
                record_id=record_id,
                seller_id=_pick_text(row, ("sellerId", "supplierId", "supplierID", "supplierContractCode")),
                nm_id=_pick_value(row, ("nmId", "nm_id", "nmid", "nmID")),
                quantity=_pick_float(row, ("quantity", "sa_quantity", "saleQty", "sales_qty")),
                sale_amount=_pick_float(
                    row,
                    ("revenue", "totalPrice", "finishedPrice", "priceWithDisc", "retail_amount", "saleAmount"),
                ),
                payout_amount=_pick_float(row, ("forPay", "ppvz_for_pay", "payout", "to_pay")),
                sale_date=_pick_date(row, ("date", "lastChangeDate", "sale_dt", "saleDate", "createdAt")),
                operation_type=operation_type,
                is_return=_detect_sales_return(row, operation_type),
                source_tag=source_tag,
                raw_ref=_make_raw_ref("sales", index, record_id),
            )
        )

    return records


def _map_realization_event_type(raw_label: str | None) -> str:
    text = str(raw_label or "").strip().lower()
    if not text:
        return "other"
    if any(token in text for token in ("логист", "достав", "перевоз", "складск")):
        return "logistics"
    if "хранен" in text:
        return "storage"
    if any(token in text for token in ("удерж", "штраф", "лояль", "балл")):
        return "deduction"
    if any(token in text for token in ("возврат", "return")):
        return "return"
    if any(token in text for token in ("продаж", "sale", "реализац")):
        return "sale"
    return "other"


def normalize_realization_source(raw_source_payload: RawSourcePayload | None) -> list[NormalizedRealizationRecord]:
    if not _is_source_usable(raw_source_payload):
        return []

    source_tag = _source_tag(raw_source_payload, "realization")
    records: list[NormalizedRealizationRecord] = []

    for index, row in enumerate(_extract_rows(raw_source_payload)):
        record_id = _pick_text(row, ("rrd_id", "rrdId", "srid", "saleID", "saleId", "odid", "rid"))
        event_type_raw = _pick_text(
            row,
            (
                "supplier_oper_name",
                "operationTypeName",
                "doc_type_name",
                "operationType",
                "operation_type",
                "payment_reason",
                "reason",
            ),
        )
        records.append(
            NormalizedRealizationRecord(
                record_id=record_id,
                seller_id=_pick_text(row, ("sellerId", "supplierId", "supplierID", "supplierContractCode")),
                nm_id=_pick_value(row, ("nm_id", "nmId", "nmID", "nmid")),
                event_date=_pick_date(row, ("rr_dt", "sale_dt", "date", "order_dt", "lastChangeDate", "create_dt")),
                event_type=_map_realization_event_type(event_type_raw),
                amount=_pick_float(
                    row,
                    (
                        "ppvz_for_pay",
                        "forPay",
                        "retail_amount",
                        "sale_amount",
                        "delivery_rub",
                        "storage_fee",
                        "penalty",
                        "acquiringFee",
                        "bonusPay",
                    ),
                ),
                quantity=_pick_float(row, ("quantity", "sa_quantity", "saleQty", "sales_qty", "qty")),
                source_tag=source_tag,
                raw_ref=_make_raw_ref("realization", index, record_id),
            )
        )

    return records


def normalize_stocks_source(raw_source_payload: RawSourcePayload | None) -> list[NormalizedStockRecord]:
    if not _is_source_usable(raw_source_payload):
        return []

    source_tag = _source_tag(raw_source_payload, "stocks")
    records: list[NormalizedStockRecord] = []

    for index, row in enumerate(_extract_rows(raw_source_payload)):
        record_id = _pick_text(row, ("barcode", "stockId", "recordId"))
        if record_id is None:
            nm_id_for_ref = _pick_value(row, ("nmId", "nm_id", "nmid", "nmID"))
            record_id = str(nm_id_for_ref) if nm_id_for_ref not in (None, "") else None

        records.append(
            NormalizedStockRecord(
                record_id=record_id,
                seller_id=_pick_text(row, ("sellerId", "supplierId", "supplierID", "supplierContractCode")),
                nm_id=_pick_value(row, ("nmId", "nm_id", "nmid", "nmID")),
                warehouse_name=_pick_text(row, ("warehouseName", "warehouse", "officeName")),
                size=_pick_text(row, ("techSize", "size", "sizeName")),
                quantity=_pick_float(row, ("quantityFull", "quantity", "qty")),
                stock_date=_pick_date(row, ("date", "lastChangeDate")),
                source_tag=source_tag,
                raw_ref=_make_raw_ref("stocks", index, record_id),
            )
        )

    return records


def _extract_ads_campaign_rows(campaigns_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(campaigns_payload, dict):
        return []

    rows: list[dict[str, Any]] = []
    raw = campaigns_payload.get("raw")
    if isinstance(raw, list):
        rows.extend([row for row in raw if isinstance(row, dict)])
    elif isinstance(raw, dict):
        adverts = raw.get("adverts")
        if isinstance(adverts, list):
            rows.extend([row for row in adverts if isinstance(row, dict)])
        else:
            for value in raw.values():
                if isinstance(value, list):
                    rows.extend([row for row in value if isinstance(row, dict)])

    if rows:
        return rows

    campaign_ids = campaigns_payload.get("campaign_ids")
    if isinstance(campaign_ids, list):
        for campaign_id in campaign_ids:
            rows.append({"id": campaign_id})

    return rows


def _extract_ads_stats_rows(stats_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(stats_payload, dict):
        return []

    rows: list[dict[str, Any]] = []

    direct_rows = stats_payload.get("rows")
    if isinstance(direct_rows, list):
        rows.extend([row for row in direct_rows if isinstance(row, dict)])

    raw_chunks = stats_payload.get("raw_chunks")
    if isinstance(raw_chunks, list):
        for chunk in raw_chunks:
            if isinstance(chunk, list):
                rows.extend([row for row in chunk if isinstance(row, dict)])
            elif isinstance(chunk, dict):
                rows.append(chunk)

    return rows


def _expand_ads_daily_stats(row: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    daily_stats = row.get("dailyStats")
    if not isinstance(daily_stats, list):
        return [(_pick_date(row, ("date", "day", "dt")), row)]

    expanded: list[tuple[str | None, dict[str, Any]]] = []
    for daily in daily_stats:
        if not isinstance(daily, dict):
            continue
        stat_obj = daily.get("stat") if isinstance(daily.get("stat"), dict) else daily
        if not isinstance(stat_obj, dict):
            continue
        stat_date = _pick_date(daily, ("date", "day", "dt"))
        if stat_date is None:
            stat_date = _pick_date(stat_obj, ("date", "day", "dt"))
        expanded.append((stat_date, stat_obj))

    return expanded or [(_pick_date(row, ("date", "day", "dt")), row)]


def normalize_ads_source(
    raw_source_payload: RawSourcePayload | None,
) -> tuple[list[NormalizedAdsCampaignRecord], list[NormalizedAdsStatRecord]]:
    if not _is_source_usable(raw_source_payload):
        return [], []

    if not isinstance(raw_source_payload.payload, dict):
        return [], []

    payload = raw_source_payload.payload
    campaigns_payload = payload.get("campaigns")
    stats_payload = payload.get("stats")

    campaign_rows = _extract_ads_campaign_rows(campaigns_payload if isinstance(campaigns_payload, dict) else None)
    campaigns: list[NormalizedAdsCampaignRecord] = []
    for index, row in enumerate(campaign_rows):
        campaign_id = _pick_value(row, ("advertId", "id", "campaignId", "campaign_id"))
        campaigns.append(
            NormalizedAdsCampaignRecord(
                campaign_id=campaign_id,
                campaign_name=_pick_text(row, ("name", "campaignName", "advertName")),
                campaign_type=_pick_text(row, ("type", "advertType", "campaignType")),
                status=_pick_text(row, ("status", "state", "campaignStatus")),
                start_date=_pick_date(row, ("startDate", "startTime", "createTime", "createdAt")),
                end_date=_pick_date(row, ("endDate", "endTime", "finishTime")),
                source_tag="ads_campaigns",
                raw_ref=_make_raw_ref("ads_campaign", index, campaign_id),
            )
        )

    stats_rows = _extract_ads_stats_rows(stats_payload if isinstance(stats_payload, dict) else None)
    stats: list[NormalizedAdsStatRecord] = []
    for row_index, row in enumerate(stats_rows):
        campaign_id = _pick_value(row, ("advertId", "campaignId", "campaign_id", "id"))
        expanded_stats = _expand_ads_daily_stats(row)
        for daily_index, (stat_date, stat_row) in enumerate(expanded_stats):
            stats.append(
                NormalizedAdsStatRecord(
                    campaign_id=campaign_id,
                    stat_date=stat_date,
                    impressions=_pick_float(stat_row, ("views", "impressions", "shows", "openCount")),
                    clicks=_pick_float(stat_row, ("clicks", "click")),
                    spend=_pick_float(stat_row, ("spend", "cost", "sum")),
                    orders=_pick_float(stat_row, ("orders", "orderCount", "ordersCount")),
                    revenue=_pick_float(stat_row, ("revenue", "revenueAttr", "orderSum")),
                    source_tag="ads_stats",
                    raw_ref=f"ads_stats:{campaign_id if campaign_id is not None else row_index}:{daily_index}",
                )
            )

    return campaigns, stats


def _funnel_stat_block(row: dict[str, Any]) -> dict[str, Any]:
    statistic = row.get("statistic")
    if isinstance(statistic, dict):
        selected = statistic.get("selected") or statistic.get("current") or statistic.get("now")
        if isinstance(selected, dict):
            return selected
    return row


def _funnel_entity_id(row: dict[str, Any]) -> str | int | None:
    direct = _pick_value(row, ("nmId", "nm_id", "nmid", "nmID", "id", "entity_id"))
    if direct is not None:
        return direct
    product = row.get("product")
    if isinstance(product, dict):
        return _pick_value(product, ("nmId", "nm_id", "nmid", "id"))
    return None


def normalize_funnel_source(raw_source_payload: RawSourcePayload | None) -> list[NormalizedFunnelRecord]:
    if not _is_source_usable(raw_source_payload):
        return []

    source_tag = _source_tag(raw_source_payload, "funnel")
    records: list[NormalizedFunnelRecord] = []
    for index, row in enumerate(_extract_rows(raw_source_payload)):
        stat = _funnel_stat_block(row)
        entity_id = _funnel_entity_id(row)
        records.append(
            NormalizedFunnelRecord(
                entity_id=entity_id,
                event_date=_pick_date(stat, ("date", "day", "dt")) or _pick_date(row, ("date", "day", "dt")),
                impressions=_pick_float(stat, ("views", "impressions", "openCount", "openCardCount")),
                opens=_pick_float(stat, ("opens", "openCount", "openCardCount")),
                cart_adds=_pick_float(stat, ("add_to_cart", "cartCount", "addToCartCount")),
                orders=_pick_float(stat, ("orders", "orderCount")),
                buys=_pick_float(stat, ("buys", "buyoutCount")),
                source_tag=source_tag,
                raw_ref=_make_raw_ref("funnel", index, entity_id),
            )
        )

    return records


def _combine_ads_sources_if_needed(raw_bundle: RawBundle) -> RawSourcePayload | None:
    ads_source = raw_bundle.sources.get("ads")
    if ads_source is not None:
        return ads_source

    campaigns = raw_bundle.sources.get("ads_campaigns")
    stats = raw_bundle.sources.get("ads_stats")
    if campaigns is None and stats is None:
        return None

    base = campaigns if campaigns is not None else stats
    assert base is not None

    combined_payload = {
        "campaigns": campaigns.payload if campaigns is not None else None,
        "stats": stats.payload if stats is not None else None,
        "campaign_ids": (
            campaigns.payload.get("campaign_ids")
            if campaigns is not None and isinstance(campaigns.payload, dict)
            else None
        ),
    }

    status = replace(base.status, source_name="ads")
    return RawSourcePayload(source_name="ads", payload=combined_payload, status=status)


def build_normalized_bundle(raw_bundle: RawBundle) -> NormalizedBundle:
    source_statuses = dict(raw_bundle.source_status)

    orders = normalize_orders_source(raw_bundle.sources.get("orders"))
    sales = normalize_sales_source(raw_bundle.sources.get("sales"))
    realization = normalize_realization_source(raw_bundle.sources.get("realization"))
    stocks = normalize_stocks_source(raw_bundle.sources.get("stocks"))

    ads_source = _combine_ads_sources_if_needed(raw_bundle)
    ads_campaigns, ads_stats = normalize_ads_source(ads_source)

    funnel = normalize_funnel_source(raw_bundle.sources.get("funnel"))

    warnings: list[str] = []
    for source_name, status in source_statuses.items():
        for warning in status.warnings:
            warnings.append(f"{source_name}: {warning}")

    diagnostics = dict(raw_bundle.diagnostics)
    diagnostics.update(
        {
            "normalized_orders_count": len(orders),
            "normalized_sales_count": len(sales),
            "normalized_realization_count": len(realization),
            "normalized_stocks_count": len(stocks),
            "normalized_ads_campaigns_count": len(ads_campaigns),
            "normalized_ads_stats_count": len(ads_stats),
            "normalized_funnel_count": len(funnel),
            "normalized_sources_count": len(source_statuses),
        }
    )

    return NormalizedBundle(
        run_context=raw_bundle.run_context,
        orders=orders,
        sales=sales,
        realization=realization,
        stocks=stocks,
        ads_campaigns=ads_campaigns,
        ads_stats=ads_stats,
        funnel=funnel,
        source_statuses=source_statuses,
        warnings=warnings,
        diagnostics=diagnostics,
    )


def normalize(raw_bundle: RawBundle) -> NormalizedBundle:
    """Back-compat adapter for stage-1 call sites."""

    return build_normalized_bundle(raw_bundle)
