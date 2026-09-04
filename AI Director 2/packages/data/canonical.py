"""Immutable canonical records produced by the initial normalization slice."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.wb_core.contracts import RawObjectType, TenantAccountScope


class CanonicalInputState(StrEnum):
    """Whether a source field was present and usable before structural conversion."""

    MISSING = "missing"
    NULL = "null"
    EMPTY_STRING = "empty_string"
    VALUE = "value"


class CanonicalValueKind(StrEnum):
    """Raw scalar kind retained to distinguish source representations."""

    MISSING = "missing"
    NULL = "null"
    EMPTY_STRING = "empty_string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"


class CanonicalCurrency(StrEnum):
    """Currency codes admitted by the initial source contract."""

    RUB = "RUB"
    UNKNOWN = "unknown"


class FinancialRecordClassification(StrEnum):
    """Source-text classification for a finance-detail record."""

    FINANCIAL_SALE = "financial_sale"
    RETURN = "return"
    LOGISTICS = "logistics"
    STORAGE = "storage"
    PENALTY = "penalty"
    DEDUCTION = "deduction"
    REIMBURSEMENT = "reimbursement"
    OTHER = "other"


class CanonicalFieldInput(BaseModel):
    """Source-path and value-state metadata for one normalized field."""

    model_config = ConfigDict(frozen=True)

    raw_path: str = Field(min_length=1, max_length=300)
    state: CanonicalInputState
    value_kind: CanonicalValueKind


class CanonicalSourceMetadata(BaseModel):
    """Immutable provenance copied from a raw object, not inferred by a normalizer."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1, max_length=100)
    scope: TenantAccountScope
    source_object_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    endpoint_name: str = Field(min_length=1, max_length=100)
    object_type: RawObjectType
    schema_version: str = Field(min_length=1, max_length=50)
    retrieved_at: datetime
    source_record_index: int = Field(ge=0)

    @field_validator("retrieved_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("retrieved_at must be timezone-aware UTC")
        return value


class CanonicalSalesFunnelProduct(BaseModel):
    """Structural canonical form of one `sales_funnel_products` source record."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    quantity: int | None = None
    quantity_input: CanonicalFieldInput
    source_open_count: int | None = None
    source_open_count_input: CanonicalFieldInput
    source_cart_count: int | None = None
    source_cart_count_input: CanonicalFieldInput
    buyout_count: int | None = None
    buyout_count_input: CanonicalFieldInput
    buyout_sum: Decimal | None = None
    buyout_sum_input: CanonicalFieldInput
    source_amount: Decimal | None = None
    source_amount_input: CanonicalFieldInput
    currency: CanonicalCurrency | None = None
    currency_raw: str | None = Field(default=None, min_length=1, max_length=20)
    currency_input: CanonicalFieldInput

    @model_validator(mode="after")
    def require_value_fields_to_match_input_state(self) -> CanonicalSalesFunnelProduct:
        if self.quantity_input.state != CanonicalInputState.VALUE and self.quantity is not None:
            raise ValueError("quantity must be null unless quantity_input.state is value")
        if self.source_open_count_input.state != CanonicalInputState.VALUE and self.source_open_count is not None:
            raise ValueError("source_open_count must be null unless source_open_count_input.state is value")
        if self.source_cart_count_input.state != CanonicalInputState.VALUE and self.source_cart_count is not None:
            raise ValueError("source_cart_count must be null unless source_cart_count_input.state is value")
        if self.buyout_count_input.state != CanonicalInputState.VALUE and self.buyout_count is not None:
            raise ValueError("buyout_count must be null unless buyout_count_input.state is value")
        if self.buyout_sum_input.state != CanonicalInputState.VALUE and self.buyout_sum is not None:
            raise ValueError("buyout_sum must be null unless buyout_sum_input.state is value")
        if self.source_amount_input.state != CanonicalInputState.VALUE and self.source_amount is not None:
            raise ValueError("source_amount must be null unless source_amount_input.state is value")
        if self.currency_input.state != CanonicalInputState.VALUE and (
            self.currency is not None or self.currency_raw is not None
        ):
            raise ValueError("currency fields must be null unless currency_input.state is value")
        return self


class CanonicalOperationalOrder(BaseModel):
    """One operational order event; it is never a financial realization."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    source_event_id: str | None = Field(default=None, min_length=1, max_length=300)
    source_event_id_input: CanonicalFieldInput
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    quantity: Decimal | None = None
    quantity_input: CanonicalFieldInput
    amount: Decimal | None = None
    amount_input: CanonicalFieldInput
    is_cancel: bool | None = None
    is_cancel_input: CanonicalFieldInput
    source_event_date: date | None = None
    source_event_date_input: CanonicalFieldInput

    @model_validator(mode="after")
    def require_values_to_follow_input_state(self) -> CanonicalOperationalOrder:
        for field_name, value, source_input in (
            ("quantity", self.quantity, self.quantity_input),
            ("amount", self.amount, self.amount_input),
            ("is_cancel", self.is_cancel, self.is_cancel_input),
            ("source_event_date", self.source_event_date, self.source_event_date_input),
        ):
            if source_input.state != CanonicalInputState.VALUE and value is not None:
                raise ValueError(f"{field_name} must be null unless its source input state is value")
        return self


class CanonicalOperationalSale(BaseModel):
    """One operational sales-source event; it is not an authoritative finance fact."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    source_event_id: str | None = Field(default=None, min_length=1, max_length=300)
    source_event_id_input: CanonicalFieldInput
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    quantity: Decimal | None = None
    quantity_input: CanonicalFieldInput
    amount: Decimal | None = None
    amount_input: CanonicalFieldInput
    source_event_date: date | None = None
    source_event_date_input: CanonicalFieldInput

    @model_validator(mode="after")
    def require_values_to_follow_input_state(self) -> CanonicalOperationalSale:
        for field_name, value, source_input in (
            ("quantity", self.quantity, self.quantity_input),
            ("amount", self.amount, self.amount_input),
            ("source_event_date", self.source_event_date, self.source_event_date_input),
        ):
            if source_input.state != CanonicalInputState.VALUE and value is not None:
                raise ValueError(f"{field_name} must be null unless its source input state is value")
        return self


class CanonicalStockSnapshot(BaseModel):
    """Warehouse stock snapshot; available and in-transit quantities stay separate."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    warehouse_name: str | None = Field(default=None, min_length=1, max_length=300)
    available_quantity: Decimal | None = None
    available_quantity_input: CanonicalFieldInput
    in_way_to_client_quantity: Decimal | None = None
    in_way_to_client_quantity_input: CanonicalFieldInput
    in_way_from_client_quantity: Decimal | None = None
    in_way_from_client_quantity_input: CanonicalFieldInput

    @model_validator(mode="after")
    def require_values_to_follow_input_state(self) -> CanonicalStockSnapshot:
        for field_name, value, source_input in (
            ("available_quantity", self.available_quantity, self.available_quantity_input),
            ("in_way_to_client_quantity", self.in_way_to_client_quantity, self.in_way_to_client_quantity_input),
            ("in_way_from_client_quantity", self.in_way_from_client_quantity, self.in_way_from_client_quantity_input),
        ):
            if source_input.state != CanonicalInputState.VALUE and value is not None:
                raise ValueError(f"{field_name} must be null unless its source input state is value")
        return self


class AdvertisingAttributionScope(StrEnum):
    """Scope at which advertising evidence is authoritative."""

    DIRECT_SKU = "direct_sku"
    CAMPAIGN = "campaign"
    PERIOD = "period"
    ASSOCIATED = "associated"
    UNKNOWN = "unknown"


class CanonicalAdvertisingPerformance(BaseModel):
    """Source advertising performance retained at its evidenced attribution scope."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    campaign_id: str | None = Field(default=None, min_length=1, max_length=100)
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    attribution_scope: AdvertisingAttributionScope
    spend: Decimal | None = None
    spend_input: CanonicalFieldInput
    impressions: int | None = None
    impressions_input: CanonicalFieldInput
    clicks: int | None = None
    clicks_input: CanonicalFieldInput
    orders: int | None = None
    orders_input: CanonicalFieldInput

    @model_validator(mode="after")
    def require_values_to_follow_input_state(self) -> CanonicalAdvertisingPerformance:
        for field_name, value, source_input in (
            ("spend", self.spend, self.spend_input),
            ("impressions", self.impressions, self.impressions_input),
            ("clicks", self.clicks, self.clicks_input),
            ("orders", self.orders, self.orders_input),
        ):
            if source_input.state != CanonicalInputState.VALUE and value is not None:
                raise ValueError(f"{field_name} must be null unless its source input state is value")
        if self.attribution_scope == AdvertisingAttributionScope.DIRECT_SKU and self.nm_id is None:
            raise ValueError("direct_sku advertising performance requires nm_id")
        return self


class CanonicalSourceMoney(BaseModel):
    """One source money field kept with its original sign and source path.

    The normalization layer never interprets a sign: it records what WB sent.
    Economic meaning is assigned downstream by an explicit, versioned sign
    policy, so an unexpected sign stays visible instead of being repaired.
    """

    model_config = ConfigDict(frozen=True)

    source_field: str = Field(min_length=1, max_length=100)
    raw_path: str = Field(min_length=1, max_length=300)
    state: CanonicalInputState
    value_kind: CanonicalValueKind
    value: Decimal | None = None

    @field_validator("value", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("canonical source money must not be float")
        return value

    @model_validator(mode="after")
    def require_value_to_follow_state(self) -> CanonicalSourceMoney:
        if self.state != CanonicalInputState.VALUE and self.value is not None:
            raise ValueError(f"{self.source_field} must be null unless its source input state is value")
        if self.state == CanonicalInputState.VALUE and self.value is None:
            raise ValueError(f"{self.source_field} requires a Decimal value when its source state is value")
        return self


class CanonicalFinanceDetailRecord(BaseModel):
    """Structural finance-detail record with separate source monetary views."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    source_record_id: str = Field(min_length=1, max_length=400)
    source_record_id_input: CanonicalFieldInput
    operational_date: date
    financial_date: date | None = None
    financial_date_input: CanonicalFieldInput
    sale_date: date | None = None
    sale_date_input: CanonicalFieldInput
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    quantity: Decimal | None = None
    quantity_input: CanonicalFieldInput
    retail_amount: Decimal | None = None
    retail_amount_input: CanonicalFieldInput
    buyer_discounted_price: Decimal | None = None
    buyer_discounted_price_input: CanonicalFieldInput
    seller_payout: Decimal | None = None
    seller_payout_input: CanonicalFieldInput
    currency: CanonicalCurrency | None = None
    currency_raw: str | None = Field(default=None, min_length=1, max_length=20)
    currency_input: CanonicalFieldInput
    operation_name: str | None = Field(default=None, max_length=300)
    document_type: str | None = Field(default=None, max_length=300)
    classification: FinancialRecordClassification
    marketplace_charges: tuple[CanonicalSourceMoney, ...] = ()
    unapproved_money_fields: tuple[CanonicalSourceMoney, ...] = ()

    @model_validator(mode="after")
    def require_values_to_follow_input_state(self) -> CanonicalFinanceDetailRecord:
        values = (
            ("quantity", self.quantity, self.quantity_input),
            ("retail_amount", self.retail_amount, self.retail_amount_input),
            ("buyer_discounted_price", self.buyer_discounted_price, self.buyer_discounted_price_input),
            ("seller_payout", self.seller_payout, self.seller_payout_input),
        )
        for field_name, value, source_input in values:
            if source_input.state != CanonicalInputState.VALUE and value is not None:
                raise ValueError(f"{field_name} must be null unless its source input state is value")
        if self.financial_date_input.state != CanonicalInputState.VALUE and self.financial_date is not None:
            raise ValueError("financial_date must be null unless its source input state is value")
        if self.sale_date_input.state != CanonicalInputState.VALUE and self.sale_date is not None:
            raise ValueError("sale_date must be null unless its source input state is value")
        if self.currency_input.state != CanonicalInputState.VALUE and (
            self.currency is not None or self.currency_raw is not None
        ):
            raise ValueError("currency fields must be null unless currency_input.state is value")
        charge_fields = tuple(charge.source_field for charge in self.marketplace_charges) + tuple(
            charge.source_field for charge in self.unapproved_money_fields
        )
        if len(set(charge_fields)) != len(charge_fields):
            raise ValueError("marketplace charge source fields must be unique per record")
        return self
