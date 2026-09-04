"""Deterministic structural normalization for one synthetic WB source shape."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    FINANCE_DETAIL_ENDPOINT,
    ORDERS_ENDPOINT,
    PayloadKind,
    RawObject,
    RawObjectType,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    SALES_ENDPOINT,
    STOCKS_ENDPOINT,
)

from .canonical import (
    CanonicalCurrency,
    CanonicalAdvertisingPerformance,
    CanonicalFinanceDetailRecord,
    CanonicalFieldInput,
    CanonicalInputState,
    CanonicalOperationalOrder,
    CanonicalOperationalSale,
    CanonicalSalesFunnelProduct,
    CanonicalSourceMoney,
    CanonicalSourceMetadata,
    CanonicalStockSnapshot,
    AdvertisingAttributionScope,
    CanonicalValueKind,
    FinancialRecordClassification,
)

SALES_FUNNEL_PRODUCTS_FIELD_MAPPING: dict[str, str] = {
    "data.products[].product.nmId": "nm_id",
    "data.products[].product.vendorCode": "seller_sku",
    "data.products[].statistic.selected.orderCount": "quantity",
    "data.products[].statistic.selected.openCount": "source_open_count",
    "data.products[].statistic.selected.cartCount": "source_cart_count",
    "data.products[].statistic.selected.buyoutCount": "buyout_count",
    "data.products[].statistic.selected.buyoutSum": "buyout_sum",
    "data.products[].statistic.selected.orderSum": "source_amount",
    "data.products[].statistic.selected.currency": "currency",
    "RawObject.operational_date": "operational_date",
    "RawObject.retrieved_at": "source_metadata.retrieved_at",
    "RawObject.object_id": "source_metadata.source_object_id",
}

ORDERS_FIELD_MAPPING: dict[str, str] = {
    "data[].srid": "source_event_id",
    "data[].nmId": "nm_id",
    "data[].supplierArticle": "seller_sku",
    "data[].quantity": "quantity",
    "data[].priceWithDisc": "amount",
    "data[].isCancel": "is_cancel",
    "data[].date": "source_event_date",
    "RawObject.operational_date": "operational_date",
}

SALES_FIELD_MAPPING: dict[str, str] = {
    "data[].srid": "source_event_id",
    "data[].nmId": "nm_id",
    "data[].supplierArticle": "seller_sku",
    "data[].quantity": "quantity",
    "data[].priceWithDisc": "amount",
    "data[].date": "source_event_date",
    "RawObject.operational_date": "operational_date",
}

STOCKS_FIELD_MAPPING: dict[str, str] = {
    "data[].nmId": "nm_id",
    "data[].supplierArticle": "seller_sku",
    "data[].warehouseName": "warehouse_name",
    "data[].quantity": "available_quantity",
    "data[].inWayToClient": "in_way_to_client_quantity",
    "data[].inWayFromClient": "in_way_from_client_quantity",
    "RawObject.operational_date": "operational_date",
}

ADVERTISING_PERFORMANCE_FIELD_MAPPING: dict[str, str] = {
    "data[].advertId": "campaign_id",
    "data[].nmId": "nm_id",
    "data[].attributionScope": "attribution_scope",
    "data[].sum": "spend",
    "data[].impressions": "impressions",
    "data[].clicks": "clicks",
    "data[].orders": "orders",
    "RawObject.operational_date": "operational_date",
}

FINANCE_DETAIL_FIELD_MAPPING: dict[str, str] = {
    "rrdId": "source_record_id_input",
    "rrDate": "financial_date",
    "saleDt": "sale_date",
    "nmId": "nm_id",
    "supplierArticle": "seller_sku",
    "quantity": "quantity",
    "retailAmount": "retail_amount",
    "retailPriceWithDiscRub": "buyer_discounted_price",
    "ppvzForPay": "seller_payout",
    "sellerOperName/supplierOperName": "operation_name",
    "docTypeName": "document_type",
    "currency": "currency",
    "supplierOperName/docTypeName": "classification",
    "ppvzSalesCommission|deliveryService|deliveryRub|paidStorage|storageFee|"
    "paidAcceptance|acquiringFee|penalty|penaltyAmount|deduction|rebillLogisticCost": "marketplace_charges",
    "RawObject.operational_date": "operational_date",
    "RawObject.retrieved_at": "source_metadata.retrieved_at",
}

# Source money fields that describe a marketplace charge. The normalizer only
# records the value and the field it came from; it never assigns an economic
# sign. `packages/finance/marketplace_policy.py` owns that decision.
FINANCE_DETAIL_CHARGE_FIELDS: tuple[tuple[str, ...], ...] = (
    ("ppvzSalesCommission",),
    ("deliveryService", "deliveryRub"),
    ("paidStorage", "storageFee"),
    ("paidAcceptance",),
    ("acquiringFee",),
    ("penalty", "penaltyAmount"),
    ("deduction",),
    ("rebillLogisticCost",),
)

# Money fields the detailed finance report also sends, for which the project has
# no approved economic meaning yet. They are retained so a period can never
# silently lose a candidate charge, and the finance adapter reports them.
FINANCE_DETAIL_OTHER_MONEY_FIELDS: tuple[tuple[str, ...], ...] = (
    ("cashbackAmount",),
    ("spp",),
    ("kvw",),
    ("kvwBase",),
    ("vw",),
    ("vwNds",),
    ("loyaltyDiscount",),
    ("sellerPromo",),
    ("sellerPromoDiscount",),
    ("productDiscountForReport",),
    ("installmentCofinancingAmount",),
    ("supRatingUp",),
    ("cashbackDiscount",),
    ("cashbackCommissionChange",),
)


class NormalizationError(ValueError):
    """Raised when source data cannot be structurally represented canonically."""


class RawObjectNormalizer(Protocol):
    """A deterministic, no-I/O converter from a raw object to canonical records."""

    def normalize(self, raw_object: RawObject) -> tuple[CanonicalSalesFunnelProduct, ...]:
        """Produce immutable canonical records without business interpretation."""


def _value_kind(value: object, *, is_missing: bool) -> CanonicalValueKind:
    if is_missing:
        return CanonicalValueKind.MISSING
    if value is None:
        return CanonicalValueKind.NULL
    if isinstance(value, str) and not value.strip():
        return CanonicalValueKind.EMPTY_STRING
    if isinstance(value, bool):
        return CanonicalValueKind.BOOLEAN
    if isinstance(value, int):
        return CanonicalValueKind.INTEGER
    if isinstance(value, float):
        return CanonicalValueKind.FLOAT
    return CanonicalValueKind.STRING


def _input_metadata(*, raw_path: str, source: Mapping[str, Any], key: str) -> tuple[object, CanonicalFieldInput]:
    if key not in source:
        return None, CanonicalFieldInput(
            raw_path=raw_path,
            state=CanonicalInputState.MISSING,
            value_kind=CanonicalValueKind.MISSING,
        )

    value = source[key]
    kind = _value_kind(value, is_missing=False)
    if value is None:
        state = CanonicalInputState.NULL
    elif kind == CanonicalValueKind.EMPTY_STRING:
        state = CanonicalInputState.EMPTY_STRING
    else:
        state = CanonicalInputState.VALUE
    return value, CanonicalFieldInput(raw_path=raw_path, state=state, value_kind=kind)


def _optional_identifier(value: object, *, raw_path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise NormalizationError(f"{raw_path} must not be boolean")
    text = str(value).strip()
    return text or None


def _integer_value(value: object, metadata: CanonicalFieldInput, *, field_name: str) -> int | None:
    if metadata.state != CanonicalInputState.VALUE:
        return None
    if isinstance(value, bool):
        raise NormalizationError(f"{field_name} must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        # JSON numbers have one numeric type; legacy transports may emit 123.0 for 123.
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise NormalizationError(f"{field_name} must be an integer when present")


def _decimal_value(value: object, metadata: CanonicalFieldInput, *, field_name: str) -> Decimal | None:
    if metadata.state != CanonicalInputState.VALUE:
        return None
    if isinstance(value, bool):
        raise NormalizationError(f"{field_name} must be a decimal-compatible value, not boolean")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, (int, str)):
        try:
            parsed = Decimal(str(value).strip())
        except InvalidOperation as error:
            raise NormalizationError(f"{field_name} must be decimal-compatible when present") from error
    elif isinstance(value, float):
        parsed = Decimal(str(value))
    else:
        raise NormalizationError(f"{field_name} must be decimal-compatible when present")
    if not parsed.is_finite():
        raise NormalizationError(f"{field_name} must be finite")
    return parsed


def _currency_value(value: object, metadata: CanonicalFieldInput) -> tuple[CanonicalCurrency | None, str | None]:
    if metadata.state != CanonicalInputState.VALUE:
        return None, None
    if not isinstance(value, str):
        raise NormalizationError("currency must be a string when present")
    raw_currency = value.strip()
    normalized = raw_currency.upper()
    if normalized == CanonicalCurrency.RUB:
        return CanonicalCurrency.RUB, raw_currency
    return CanonicalCurrency.UNKNOWN, raw_currency


def _optional_integer_value(value: object, metadata: CanonicalFieldInput, *, field_name: str) -> int | None:
    return _integer_value(value, metadata, field_name=field_name)


def _date_value(value: object, metadata: CanonicalFieldInput, *, field_name: str) -> date | None:
    if metadata.state != CanonicalInputState.VALUE:
        return None
    if not isinstance(value, str):
        raise NormalizationError(f"{field_name} must be an ISO date string when present")
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as error:
        raise NormalizationError(f"{field_name} must be an ISO date string when present") from error


def _boolean_value(value: object, metadata: CanonicalFieldInput, *, field_name: str) -> bool | None:
    if metadata.state != CanonicalInputState.VALUE:
        return None
    if isinstance(value, bool):
        return value
    raise NormalizationError(f"{field_name} must be a boolean when present")


def _advertising_scope(value: object, metadata: CanonicalFieldInput, *, nm_id: str | None) -> AdvertisingAttributionScope:
    if metadata.state != CanonicalInputState.VALUE:
        return AdvertisingAttributionScope.DIRECT_SKU if nm_id is not None else AdvertisingAttributionScope.UNKNOWN
    if not isinstance(value, str):
        raise NormalizationError("attributionScope must be a string when present")
    try:
        scope = AdvertisingAttributionScope(value.strip().lower())
    except ValueError as error:
        raise NormalizationError("attributionScope must be a supported advertising scope") from error
    if scope == AdvertisingAttributionScope.DIRECT_SKU and nm_id is None:
        raise NormalizationError("direct_sku attributionScope requires nmId")
    return scope


def _first_input_metadata(
    *, raw_path: str, source: Mapping[str, Any], keys: tuple[str, ...]
) -> tuple[object, CanonicalFieldInput]:
    for key in keys:
        if key in source:
            return _input_metadata(raw_path=raw_path, source=source, key=key)
    return _input_metadata(raw_path=raw_path, source=source, key=keys[0])


def _source_money_fields(
    row: Mapping[str, Any], field_groups: tuple[tuple[str, ...], ...]
) -> tuple[CanonicalSourceMoney, ...]:
    """Project every present source money field, keeping the source sign untouched.

    An absent, null or empty field produces no entry: it is not a zero charge.
    """

    charges: list[CanonicalSourceMoney] = []
    for keys in field_groups:
        for key in keys:
            if key not in row:
                continue
            value, metadata = _input_metadata(raw_path=key, source=row, key=key)
            if metadata.state != CanonicalInputState.VALUE:
                break
            charges.append(
                CanonicalSourceMoney(
                    source_field=key,
                    raw_path=key,
                    state=metadata.state,
                    value_kind=metadata.value_kind,
                    value=_decimal_value(value, metadata, field_name=key),
                )
            )
            break
    return tuple(charges)


def _finance_operation_name(row: Mapping[str, Any]) -> str | None:
    """Read the operation name from the field the detailed finance endpoint actually sends."""

    for key in ("sellerOperName", "supplierOperName"):
        name = _optional_identifier(row.get(key), raw_path=key)
        if name:
            return name
    return None


def _finance_text_classification(operation_name: str | None, document_type: str | None) -> FinancialRecordClassification:
    text = " ".join(part.lower() for part in (operation_name, document_type) if part).strip()
    if any(marker in text for marker in ("возврат", "return", "refund", "сторно")):
        return FinancialRecordClassification.RETURN
    if any(marker in text for marker in ("продаж", "реализац")):
        return FinancialRecordClassification.FINANCIAL_SALE
    if any(marker in text for marker in ("возмещ", "компенсац", "reimburse", "compensat")):
        return FinancialRecordClassification.REIMBURSEMENT
    if any(marker in text for marker in ("логист", "доставк", "перевоз")):
        return FinancialRecordClassification.LOGISTICS
    if any(marker in text for marker in ("хран", "storage")):
        return FinancialRecordClassification.STORAGE
    if any(marker in text for marker in ("штраф", "penalty", "fine")):
        return FinancialRecordClassification.PENALTY
    if any(marker in text for marker in ("удержан", "deduct", "коррект", "acquiring")):
        return FinancialRecordClassification.DEDUCTION
    return FinancialRecordClassification.OTHER


def _required_mapping(value: object, *, raw_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizationError(f"{raw_path} must be an object")
    return value


def _products_payload(raw_object: RawObject) -> Sequence[object]:
    payload = _required_mapping(raw_object.payload, raw_path="payload")
    data = _required_mapping(payload.get("data"), raw_path="payload.data")
    products = data.get("products")
    if not isinstance(products, Sequence) or isinstance(products, (str, bytes, bytearray)):
        raise NormalizationError("payload.data.products must be an array")
    return products


def _rows_payload(raw_object: RawObject, *, endpoint_name: str) -> Sequence[object]:
    if raw_object.endpoint.expected_payload_kind == PayloadKind.ARRAY and isinstance(raw_object.payload, tuple):
        rows = raw_object.payload
    else:
        payload = _required_mapping(raw_object.payload, raw_path="payload")
        rows = payload.get("data")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise NormalizationError(f"{endpoint_name} payload.data must be an array")
    return rows


def _source_metadata(raw_object: RawObject, *, index: int) -> CanonicalSourceMetadata:
    return CanonicalSourceMetadata(
        source=raw_object.source,
        scope=raw_object.scope,
        source_object_id=raw_object.object_id,
        endpoint_name=raw_object.endpoint.name,
        object_type=raw_object.object_type,
        schema_version=raw_object.schema_version,
        retrieved_at=raw_object.retrieved_at,
        source_record_index=index,
    )


class SalesFunnelProductsNormalizer:
    """Normalize only the declared sales-funnel source fields without computing metrics."""

    def normalize(self, raw_object: RawObject) -> tuple[CanonicalSalesFunnelProduct, ...]:
        if raw_object.endpoint.name != SALES_FUNNEL_PRODUCTS_ENDPOINT.name:
            raise NormalizationError("sales_funnel_products normalizer received an unsupported endpoint")
        if raw_object.object_type != RawObjectType.SALES_FUNNEL_PRODUCTS:
            raise NormalizationError("sales_funnel_products normalizer received an unsupported object_type")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")

        records: list[CanonicalSalesFunnelProduct] = []
        for index, product_item in enumerate(_products_payload(raw_object)):
            row = _required_mapping(product_item, raw_path=f"payload.data.products[{index}]")
            product = _required_mapping(row.get("product", {}), raw_path=f"payload.data.products[{index}].product")
            statistic = _required_mapping(
                row.get("statistic", {}), raw_path=f"payload.data.products[{index}].statistic"
            )
            selected = _required_mapping(
                statistic.get("selected", {}), raw_path=f"payload.data.products[{index}].statistic.selected"
            )

            quantity_raw, quantity_input = _input_metadata(
                raw_path="statistic.selected.orderCount", source=selected, key="orderCount"
            )
            amount_raw, amount_input = _input_metadata(
                raw_path="statistic.selected.orderSum", source=selected, key="orderSum"
            )
            currency_raw, currency_input = _input_metadata(
                raw_path="statistic.selected.currency", source=selected, key="currency"
            )
            open_raw, open_input = _input_metadata(
                raw_path="statistic.selected.openCount", source=selected, key="openCount"
            )
            cart_raw, cart_input = _input_metadata(
                raw_path="statistic.selected.cartCount", source=selected, key="cartCount"
            )
            currency_value = _currency_value(currency_raw, currency_input)

            records.append(
                CanonicalSalesFunnelProduct(
                    source_metadata=_source_metadata(raw_object, index=index),
                    operational_date=operational_date,
                    nm_id=_optional_identifier(product.get("nmId"), raw_path="product.nmId"),
                    seller_sku=_optional_identifier(product.get("vendorCode"), raw_path="product.vendorCode"),
                    quantity=_integer_value(quantity_raw, quantity_input, field_name="orderCount"),
                    quantity_input=quantity_input,
                    source_open_count=_optional_integer_value(open_raw, open_input, field_name="openCount"),
                    source_open_count_input=open_input,
                    source_cart_count=_optional_integer_value(cart_raw, cart_input, field_name="cartCount"),
                    source_cart_count_input=cart_input,
                    buyout_count=_optional_integer_value(
                        *_input_metadata(raw_path="statistic.selected.buyoutCount", source=selected, key="buyoutCount"),
                        field_name="buyoutCount",
                    ),
                    buyout_count_input=_input_metadata(
                        raw_path="statistic.selected.buyoutCount", source=selected, key="buyoutCount"
                    )[1],
                    buyout_sum=_decimal_value(
                        *_input_metadata(raw_path="statistic.selected.buyoutSum", source=selected, key="buyoutSum"),
                        field_name="buyoutSum",
                    ),
                    buyout_sum_input=_input_metadata(
                        raw_path="statistic.selected.buyoutSum", source=selected, key="buyoutSum"
                    )[1],
                    source_amount=_decimal_value(amount_raw, amount_input, field_name="orderSum"),
                    source_amount_input=amount_input,
                    currency=currency_value[0],
                    currency_raw=currency_value[1],
                    currency_input=currency_input,
                )
            )
        return tuple(records)


def normalize_sales_funnel_products(raw_object: RawObject) -> tuple[CanonicalSalesFunnelProduct, ...]:
    """Normalize one raw object with the sole Stage 3 source normalizer."""

    return SalesFunnelProductsNormalizer().normalize(raw_object)


class FinanceDetailNormalizer:
    """Normalize finance-detail source fields without aggregating or assigning P&L components."""

    def normalize(self, raw_object: RawObject) -> tuple[CanonicalFinanceDetailRecord, ...]:
        if raw_object.endpoint.name != FINANCE_DETAIL_ENDPOINT.name:
            raise NormalizationError("finance_detail normalizer received an unsupported endpoint")
        if raw_object.object_type != RawObjectType.FINANCE_DETAIL:
            raise NormalizationError("finance_detail normalizer received an unsupported object_type")
        if raw_object.endpoint.expected_payload_kind == PayloadKind.ARRAY and isinstance(raw_object.payload, tuple):
            raw_rows = raw_object.payload
        else:
            payload = _required_mapping(raw_object.payload, raw_path="payload")
            raw_rows = payload.get("data")
        if not isinstance(raw_rows, tuple):
            raise NormalizationError("finance_detail payload.data must be an array")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")

        records: list[CanonicalFinanceDetailRecord] = []
        for index, raw_row in enumerate(raw_rows):
            row = _required_mapping(raw_row, raw_path=f"payload[{index}]")
            source_id_raw, source_id_input = _input_metadata(raw_path="rrdId", source=row, key="rrdId")
            financial_date_raw, financial_date_input = _input_metadata(raw_path="rrDate", source=row, key="rrDate")
            sale_date_raw, sale_date_input = _input_metadata(raw_path="saleDt", source=row, key="saleDt")
            quantity_raw, quantity_input = _input_metadata(raw_path="quantity", source=row, key="quantity")
            retail_raw, retail_input = _input_metadata(raw_path="retailAmount", source=row, key="retailAmount")
            buyer_raw, buyer_input = _first_input_metadata(
                raw_path="retailPriceWithDiscRub",
                source=row,
                keys=("retailPriceWithDiscRub", "retailPriceWithDisc"),
            )
            payout_raw, payout_input = _input_metadata(raw_path="ppvzForPay", source=row, key="ppvzForPay")
            currency_raw, currency_input = _input_metadata(raw_path="currency", source=row, key="currency")
            operation_name = _finance_operation_name(row)
            document_type = _optional_identifier(row.get("docTypeName"), raw_path="docTypeName")
            source_record_id = (
                _optional_identifier(source_id_raw, raw_path="rrdId")
                if source_id_input.state == CanonicalInputState.VALUE
                else None
            )
            if source_record_id is None:
                source_record_id = f"{raw_object.object_id}:{index}"
            currency_value = _currency_value(currency_raw, currency_input)

            records.append(
                CanonicalFinanceDetailRecord(
                    source_metadata=_source_metadata(raw_object, index=index),
                    source_record_id=source_record_id,
                    source_record_id_input=source_id_input,
                    operational_date=operational_date,
                    financial_date=_date_value(financial_date_raw, financial_date_input, field_name="rrDate"),
                    financial_date_input=financial_date_input,
                    sale_date=_date_value(sale_date_raw, sale_date_input, field_name="saleDt"),
                    sale_date_input=sale_date_input,
                    nm_id=_optional_identifier(row.get("nmId"), raw_path="nmId"),
                    seller_sku=_optional_identifier(row.get("supplierArticle"), raw_path="supplierArticle"),
                    quantity=_decimal_value(quantity_raw, quantity_input, field_name="quantity"),
                    quantity_input=quantity_input,
                    retail_amount=_decimal_value(retail_raw, retail_input, field_name="retailAmount"),
                    retail_amount_input=retail_input,
                    buyer_discounted_price=_decimal_value(
                        buyer_raw, buyer_input, field_name="retailPriceWithDiscRub"
                    ),
                    buyer_discounted_price_input=buyer_input,
                    seller_payout=_decimal_value(payout_raw, payout_input, field_name="ppvzForPay"),
                    seller_payout_input=payout_input,
                    currency=currency_value[0],
                    currency_raw=currency_value[1],
                    currency_input=currency_input,
                    operation_name=operation_name,
                    document_type=document_type,
                    classification=_finance_text_classification(operation_name, document_type),
                    marketplace_charges=_source_money_fields(row, FINANCE_DETAIL_CHARGE_FIELDS),
                    unapproved_money_fields=tuple(
                        charge
                        for charge in _source_money_fields(row, FINANCE_DETAIL_OTHER_MONEY_FIELDS)
                        if charge.value != 0
                    ),
                )
            )
        return tuple(records)


def normalize_finance_detail(raw_object: RawObject) -> tuple[CanonicalFinanceDetailRecord, ...]:
    """Normalize one immutable finance-detail raw object."""

    return FinanceDetailNormalizer().normalize(raw_object)


def _statistics_row_quantity_input(
    row: Mapping[str, Any],
) -> tuple[object, CanonicalFieldInput]:
    """Resolve quantity for one WB statistics row (``/supplier/orders``, ``/supplier/sales``).

    The WB statistics format emits exactly one item per row and has no
    ``quantity`` field, so an absent quantity means exactly one item.
    ``null`` / empty-string stay missing (explicit unusable source value is not
    the documented absent-field form), and no other source inherits this rule:
    only the endpoint-gated orders/sales record builders call this helper.
    """

    quantity_raw, quantity_input = _input_metadata(raw_path="quantity", source=row, key="quantity")
    if quantity_input.state == CanonicalInputState.MISSING:
        return 1, CanonicalFieldInput(
            raw_path="quantity",
            state=CanonicalInputState.VALUE,
            value_kind=CanonicalValueKind.INTEGER,
        )
    return quantity_raw, quantity_input


class OperationalNormalizer:
    """Normalize declared operational endpoint shapes without finance interpretation."""

    def normalize_orders(self, raw_object: RawObject) -> tuple[CanonicalOperationalOrder, ...]:
        if raw_object.endpoint.name != ORDERS_ENDPOINT.name or raw_object.object_type != RawObjectType.ORDERS:
            raise NormalizationError("orders normalizer received an unsupported endpoint")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")
        return tuple(
            self._order_record(raw_object, operational_date, _required_mapping(item, raw_path=f"payload.data[{index}]"), index)
            for index, item in enumerate(_rows_payload(raw_object, endpoint_name="orders"))
        )

    def normalize_sales(self, raw_object: RawObject) -> tuple[CanonicalOperationalSale, ...]:
        if raw_object.endpoint.name != SALES_ENDPOINT.name or raw_object.object_type != RawObjectType.SALES:
            raise NormalizationError("sales normalizer received an unsupported endpoint")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")
        return tuple(
            self._sale_record(raw_object, operational_date, _required_mapping(item, raw_path=f"payload.data[{index}]"), index)
            for index, item in enumerate(_rows_payload(raw_object, endpoint_name="sales"))
        )

    def normalize_stocks(self, raw_object: RawObject) -> tuple[CanonicalStockSnapshot, ...]:
        if raw_object.endpoint.name != STOCKS_ENDPOINT.name or raw_object.object_type != RawObjectType.STOCKS:
            raise NormalizationError("stocks normalizer received an unsupported endpoint")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")
        records: list[CanonicalStockSnapshot] = []
        for index, item in enumerate(_rows_payload(raw_object, endpoint_name="stocks")):
            row = _required_mapping(item, raw_path=f"payload.data[{index}]")
            available_raw, available_input = _input_metadata(raw_path="quantity", source=row, key="quantity")
            to_client_raw, to_client_input = _input_metadata(raw_path="inWayToClient", source=row, key="inWayToClient")
            from_client_raw, from_client_input = _input_metadata(
                raw_path="inWayFromClient", source=row, key="inWayFromClient"
            )
            records.append(
                CanonicalStockSnapshot(
                    source_metadata=_source_metadata(raw_object, index=index),
                    operational_date=operational_date,
                    nm_id=_optional_identifier(row.get("nmId"), raw_path="nmId"),
                    seller_sku=_optional_identifier(row.get("supplierArticle"), raw_path="supplierArticle"),
                    warehouse_name=_optional_identifier(row.get("warehouseName"), raw_path="warehouseName"),
                    available_quantity=_decimal_value(available_raw, available_input, field_name="quantity"),
                    available_quantity_input=available_input,
                    in_way_to_client_quantity=_decimal_value(
                        to_client_raw, to_client_input, field_name="inWayToClient"
                    ),
                    in_way_to_client_quantity_input=to_client_input,
                    in_way_from_client_quantity=_decimal_value(
                        from_client_raw, from_client_input, field_name="inWayFromClient"
                    ),
                    in_way_from_client_quantity_input=from_client_input,
                )
            )
        return tuple(records)

    def normalize_advertising(self, raw_object: RawObject) -> tuple[CanonicalAdvertisingPerformance, ...]:
        if (
            raw_object.endpoint.name != ADVERTISING_PERFORMANCE_ENDPOINT.name
            or raw_object.object_type != RawObjectType.ADVERTISING_PERFORMANCE
        ):
            raise NormalizationError("advertising normalizer received an unsupported endpoint")
        operational_date = raw_object.operational_date
        if operational_date is None:
            raise NormalizationError("operational_date is required; retrieved_at must not be used as a substitute")
        records: list[CanonicalAdvertisingPerformance] = []
        for index, item in enumerate(_rows_payload(raw_object, endpoint_name="advertising_performance")):
            row = _required_mapping(item, raw_path=f"payload.data[{index}]")
            spend_raw, spend_input = _input_metadata(raw_path="sum", source=row, key="sum")
            impressions_raw, impressions_input = _input_metadata(raw_path="impressions", source=row, key="impressions")
            clicks_raw, clicks_input = _input_metadata(raw_path="clicks", source=row, key="clicks")
            orders_raw, orders_input = _input_metadata(raw_path="orders", source=row, key="orders")
            scope_raw, scope_input = _input_metadata(raw_path="attributionScope", source=row, key="attributionScope")
            nm_id = _optional_identifier(row.get("nmId"), raw_path="nmId")
            records.append(
                CanonicalAdvertisingPerformance(
                    source_metadata=_source_metadata(raw_object, index=index),
                    operational_date=operational_date,
                    campaign_id=_optional_identifier(row.get("advertId"), raw_path="advertId"),
                    nm_id=nm_id,
                    attribution_scope=_advertising_scope(scope_raw, scope_input, nm_id=nm_id),
                    spend=_decimal_value(spend_raw, spend_input, field_name="sum"),
                    spend_input=spend_input,
                    impressions=_integer_value(impressions_raw, impressions_input, field_name="impressions"),
                    impressions_input=impressions_input,
                    clicks=_integer_value(clicks_raw, clicks_input, field_name="clicks"),
                    clicks_input=clicks_input,
                    orders=_integer_value(orders_raw, orders_input, field_name="orders"),
                    orders_input=orders_input,
                )
            )
        return tuple(records)

    @staticmethod
    def _order_record(
        raw_object: RawObject, operational_date: date, row: Mapping[str, Any], index: int
    ) -> CanonicalOperationalOrder:
        event_id_raw, event_id_input = _input_metadata(raw_path="srid", source=row, key="srid")
        quantity_raw, quantity_input = _statistics_row_quantity_input(row)
        amount_raw, amount_input = _input_metadata(raw_path="priceWithDisc", source=row, key="priceWithDisc")
        cancel_raw, cancel_input = _input_metadata(raw_path="isCancel", source=row, key="isCancel")
        date_raw, date_input = _input_metadata(raw_path="date", source=row, key="date")
        return CanonicalOperationalOrder(
            source_metadata=_source_metadata(raw_object, index=index),
            operational_date=operational_date,
            source_event_id=_optional_identifier(event_id_raw, raw_path="srid"),
            source_event_id_input=event_id_input,
            nm_id=_optional_identifier(row.get("nmId"), raw_path="nmId"),
            seller_sku=_optional_identifier(row.get("supplierArticle"), raw_path="supplierArticle"),
            quantity=_decimal_value(quantity_raw, quantity_input, field_name="quantity"),
            quantity_input=quantity_input,
            amount=_decimal_value(amount_raw, amount_input, field_name="priceWithDisc"),
            amount_input=amount_input,
            is_cancel=_boolean_value(cancel_raw, cancel_input, field_name="isCancel"),
            is_cancel_input=cancel_input,
            source_event_date=_date_value(date_raw, date_input, field_name="date"),
            source_event_date_input=date_input,
        )

    @staticmethod
    def _sale_record(
        raw_object: RawObject, operational_date: date, row: Mapping[str, Any], index: int
    ) -> CanonicalOperationalSale:
        event_id_raw, event_id_input = _input_metadata(raw_path="srid", source=row, key="srid")
        quantity_raw, quantity_input = _statistics_row_quantity_input(row)
        amount_raw, amount_input = _input_metadata(raw_path="priceWithDisc", source=row, key="priceWithDisc")
        date_raw, date_input = _input_metadata(raw_path="date", source=row, key="date")
        return CanonicalOperationalSale(
            source_metadata=_source_metadata(raw_object, index=index),
            operational_date=operational_date,
            source_event_id=_optional_identifier(event_id_raw, raw_path="srid"),
            source_event_id_input=event_id_input,
            nm_id=_optional_identifier(row.get("nmId"), raw_path="nmId"),
            seller_sku=_optional_identifier(row.get("supplierArticle"), raw_path="supplierArticle"),
            quantity=_decimal_value(quantity_raw, quantity_input, field_name="quantity"),
            quantity_input=quantity_input,
            amount=_decimal_value(amount_raw, amount_input, field_name="priceWithDisc"),
            amount_input=amount_input,
            source_event_date=_date_value(date_raw, date_input, field_name="date"),
            source_event_date_input=date_input,
        )


def normalize_orders(raw_object: RawObject) -> tuple[CanonicalOperationalOrder, ...]:
    """Normalize one immutable operational orders object."""

    return OperationalNormalizer().normalize_orders(raw_object)


def normalize_sales(raw_object: RawObject) -> tuple[CanonicalOperationalSale, ...]:
    """Normalize one immutable operational sales object."""

    return OperationalNormalizer().normalize_sales(raw_object)


def normalize_stocks(raw_object: RawObject) -> tuple[CanonicalStockSnapshot, ...]:
    """Normalize one immutable warehouse-stocks object."""

    return OperationalNormalizer().normalize_stocks(raw_object)


def normalize_advertising_performance(raw_object: RawObject) -> tuple[CanonicalAdvertisingPerformance, ...]:
    """Normalize advertising rows while preserving their authoritative source scope."""

    return OperationalNormalizer().normalize_advertising(raw_object)
