# Canonical Normalization

## Purpose

Stage 3 introduces the first target canonicalization boundary:

```text
RawObject -> SalesFunnelProductsNormalizer -> CanonicalSalesFunnelProduct
```

It accepts one immutable Stage 2 raw object and produces immutable,
domain-ready technical records. It does not define a sale, buyout, revenue,
profit, finance status, reconciliation result, or report metric.

The only source slice is the synthetic operational WB endpoint
`sales_funnel_products`. There is no network, filesystem, legacy, report, or
finance dependency.

## Responsibilities

- Verify the raw endpoint and object type are the declared source contract.
- Copy source object identity, source, endpoint, schema version, retrieval
  time, and record index into canonical provenance.
- Structurally extract product identifiers and explicitly named source fields.
- Convert `orderSum` to `Decimal` without rounding or financial calculation.
- Retain source input states so missing, null, empty string, zero, and string
  zero remain distinguishable.
- Preserve `operational_date` supplied by `RawObject`; fail if absent.
- Map a known currency to `RUB` or preserve an unknown value as explicit
  `unknown` plus `currency_raw`.
- Produce a deterministic immutable tuple of immutable records.

## Non-Responsibilities

- No endpoint comparison, reconciliation, aggregation, deduplication, rate,
  buyout, sale, revenue, profit, commission, COGS, tax, logistics, ad spend,
  or financial status calculation.
- No defaulting of missing values to zero.
- No derivation of `operational_date` from `retrieved_at` or current time.
- No source mutation, persistence, transport, legacy import, report/PDF/email
  access, network access, filesystem access, or global state.

## Canonical Model

`CanonicalSalesFunnelProduct` contains only fields used by the current source
slice:

| Canonical field | Type | Source and meaning |
| --- | --- | --- |
| `source_metadata.source` | string | `RawObject.source` |
| `source_metadata.scope` | tenant/account scope | `RawObject.scope`; prevents cross-account fact mixing |
| `source_metadata.source_object_id` | string | `RawObject.object_id` |
| `source_metadata.endpoint_name` | string | `RawObject.endpoint.name` |
| `source_metadata.object_type` | enum | `RawObject.object_type` |
| `source_metadata.schema_version` | string | `RawObject.schema_version` |
| `source_metadata.retrieved_at` | UTC datetime | `RawObject.retrieved_at` |
| `source_metadata.source_record_index` | integer | index within `data.products` |
| `operational_date` | date | `RawObject.operational_date` only |
| `nm_id` | nullable string | `product.nmId` structural identifier |
| `seller_sku` | nullable string | `product.vendorCode` structural identifier |
| `quantity` | nullable integer | `statistic.selected.orderCount`; source count, not a completed-sale interpretation |
| `source_open_count` | nullable integer | `statistic.selected.openCount`; unaggregated source field |
| `source_cart_count` | nullable integer | `statistic.selected.cartCount`; unaggregated source field |
| `source_amount` | nullable `Decimal` | `statistic.selected.orderSum`; source value only |
| `currency` | nullable enum | known `RUB`, otherwise explicit `unknown` |
| `currency_raw` | nullable string | original non-empty source currency text |
| `quantity_input`, `source_open_count_input`, `source_cart_count_input`, `source_amount_input`, `currency_input` | immutable metadata | source path, presence state, and raw scalar kind |

## Explicit Raw to Canonical Mapping

| Raw field | Canonical field | Type / transformation | Nullable | Semantic boundary |
| --- | --- | --- | --- | --- |
| `RawObject.object_id` | `source_metadata.source_object_id` | copy | no | raw provenance only |
| `RawObject.source` | `source_metadata.source` | copy | no | raw provenance only |
| `RawObject.scope` | `source_metadata.scope` | copy tenant/account scope | no | source tenancy only |
| `RawObject.retrieved_at` | `source_metadata.retrieved_at` | copy UTC datetime | no | retrieval metadata only |
| `RawObject.operational_date` | `operational_date` | copy date; error when absent | no | business-period identity only |
| `data.products[].product.nmId` | `nm_id` | trim/string conversion; boolean rejected | yes | product identifier only |
| `data.products[].product.vendorCode` | `seller_sku` | trim/string conversion; boolean rejected | yes | product identifier only |
| `data.products[].statistic.selected.orderCount` | `quantity` | integer or integer string; preserve input state | yes | source count only |
| `data.products[].statistic.selected.openCount` | `source_open_count` | integer or integer string | yes | source field only |
| `data.products[].statistic.selected.cartCount` | `source_cart_count` | integer or integer string | yes | source field only |
| `data.products[].statistic.selected.orderSum` | `source_amount` | `Decimal(str(value))`, no rounding | yes | source monetary value only |
| `data.products[].statistic.selected.currency` | `currency`, `currency_raw` | known `RUB`; otherwise `unknown` + raw text | yes | source currency label only |

The same mapping is present as `SALES_FUNNEL_PRODUCTS_FIELD_MAPPING` in code.
There are no aliases or hidden fallback fields in this first slice.

## Date Semantics

`operational_date` and `retrieved_at` are different required concepts:

```text
operational_date: the requested WB business period
retrieved_at:     when the response entered the raw boundary, always UTC
```

The normalizer copies both values. It never uses the retrieval timestamp to
invent, substitute, or adjust an operational date. The normalizer rejects a
raw object with no operational date even if `retrieved_at` is present.

## Money Semantics

`source_amount` is a raw source value represented as `Decimal`. For a source
value `"1234.5600"`, the canonical result is `Decimal("1234.5600")`; its scale
is not rounded away. The normalizer does not add, subtract, allocate, convert,
or otherwise calculate money. Float input, where supplied by an external raw
source, is converted through its string representation rather than binary
arithmetic; target monetary outputs remain `Decimal`.

## Missing, Null, Empty, and Zero

`CanonicalFieldInput` carries both a presence state and a raw value kind:

| Raw condition | State | Canonical value |
| --- | --- | --- |
| field absent | `missing` | `None` |
| field is `null` | `null` | `None` |
| field is `""` | `empty_string` | `None` |
| field is `0` | `value` / `integer` | `0` |
| field is `"0"` | `value` / `string` | converted to `0` only for integer-compatible source fields |

Malformed non-empty values raise `NormalizationError`. The normalizer does not
silently treat malformed input as an unknown or a zero.

## Enum Rules

The only source enum in this slice is currency. `RUB` maps to the canonical
`RUB` enum. A non-empty unknown currency maps to canonical `unknown` while
preserving the original source text in `currency_raw`. This is an explicit
unknown representation, not a fallback to RUB.

## Immutability and Determinism

Canonical Pydantic models are frozen. Their fields are copied from the raw
object or created from scalar values; later source mutation cannot change a
canonical record. Repeated calls with the same raw object return value-equal
canonical tuples in source array order. The normalizer has no time, network,
filesystem, or global-state dependency.

## Error Policy

`NormalizationError` is raised for:

- an unsupported endpoint or object type;
- missing operational date;
- malformed source envelope or product list;
- malformed nested record shape;
- boolean identifiers/counts/money;
- non-integer count values;
- invalid/non-finite monetary values;
- a non-string present currency.

Errors are structural. They do not classify data as financially valid,
reconcile sources, or make business conclusions.

## Synthetic Scenario

The Stage 2 synthetic raw object contains one `sales_funnel_products` record:

```text
nmId=1001
vendorCode=SYNTH-ART-1001
operational_date=2026-08-20
retrieved_at=2026-08-24T10:30:00Z
openCount=42
cartCount=7
orderCount=2
orderSum="1234.56"
currency=RUB
```

The Stage 3 normalizer emits one canonical record. No conclusion is drawn from
the counts or amount.

## Future Extension Pattern

Each additional endpoint requires a separate task with:

1. endpoint metadata and a raw fixture;
2. a minimal canonical model and explicit mapping table;
3. missing/null/zero, enum, date, money, immutability, and determinism tests;
4. a normalizer with no business interpretation;
5. a documented parity/contract decision before a domain or reconciliation
   layer consumes it.

Stage 4 may define reconciliation contracts across independently normalized
records. It must not be folded into this normalizer.

## Stage 8 Finance Detail Slice

Stage 8 adds an independent financial source boundary. It does not alter the
sales-funnel contract:

```text
RawObject(FINANCE_DETAIL) -> FinanceDetailNormalizer -> CanonicalFinanceDetailRecord
```

`FINANCE_DETAIL` is a financial endpoint with an explicitly requested financial
business day. Its raw object retains the response array, tenant/account scope,
schema version, retrieval time in UTC, and request period. Each canonical row
preserves source record identity (`rrdId` when present; otherwise a diagnostic
raw-object/index identity), raw input state, and these separate source views:

| Raw field | Canonical field | Semantics |
| --- | --- | --- |
| `rrDate` | `financial_date` | actual finance report date, never inferred |
| `saleDt` | `sale_date` | source sale date, independent from report date |
| `retailAmount` | `retail_amount` | source gross-realization candidate |
| `retailPriceWithDiscRub` | `buyer_discounted_price` | per-unit buyer view, not P&L revenue |
| `ppvzForPay` | `seller_payout` | settlement view, not P&L revenue |
| `supplierOperName` / `docTypeName` | `classification` | source-text classification only |

The normalizer makes no P&L decision. The Stage 8 Finance adapter is the sole
owner of the revenue mapping: it emits `realized_revenue` from `retailAmount`
only for a classified financial-sale record with a durable `rrdId`. Returns,
unclassified records, missing `retailAmount`, and diagnostic-only identities
remain retained facts but cannot become authoritative revenue. Missing, null,
empty, and explicit zero source values remain distinct.
