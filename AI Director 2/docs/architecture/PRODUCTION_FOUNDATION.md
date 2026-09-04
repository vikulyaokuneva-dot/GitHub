# Production Foundation: Account Registration and Durable Raw Storage

This slice replaces the prior production input blocker with a minimal durable
foundation. It does not resume replay or Legacy parity. Stage 19 remains
`CLOSED / BLOCKED_BY_SCOPE_CONTRACT`.

## Account identity

`packages.accounts` registers a Wildberries seller before ingestion. The
registration creates random system UUIDs for `tenant_id` and `account_id` once
and persists their mapping to the external `seller_id`. These are internal,
stable tenancy identities, not WB values and not UUIDs derived from a seller
identifier. A `TenantAccountScope` is available only from the resulting
`AccountRegistration`.

The stored `CredentialRef` is an opaque reference such as `WB_API_TOKEN`; it
contains no token material. Secret storage remains a separate infrastructure
concern.

## Storage

The first durable implementation is `SQLiteRawObjectRepository`, built on the
Python standard-library `sqlite3` module. It uses the existing `RawObject`
contract without altering its schema or tenancy semantics. Payload and request
metadata are serialized from the already validated immutable object and read
back through `RawObject`, which re-applies UTC, endpoint, scope, and
credential-free validation.

Each repository operation opens, commits, and closes its own SQLite connection.
The connection enables foreign keys, WAL journal mode, `synchronous=FULL`, and
a bounded ten-second SQLite busy timeout. This preserves durability and gives a
contending writer a finite wait; it is not a network or ingestion retry loop.

`packages.persistence.sqlite` owns a versioned migration list. Migration 1
creates `account_registrations` and tenant/account-scoped `raw_objects`; its
down migration drops both tables. Integration tests cover apply and rollback.

## First ingestion slice

`WBSalesFunnelIngestionService` accepts a read-only transport port and performs
only this sequence:

```text
registered account -> TenantAccountScope -> WB sales-funnel transport
-> RawObject -> SQLiteRawObjectRepository -> scoped readback -> canonical normalization
```

The root `wb_api_core.WBApiClient` is bound only by
`packages.compat.wb_sales_funnel_transport`. No domain package imports the
legacy transport directly. The slice intentionally excludes finance,
reconciliation, reporting, COGS, tax, automation, and all other endpoints.

## Operational boundary

A live call requires a separately selected registered seller, a process-local
credential resolver, and an explicit runtime database path outside Git. A 429
response is an operational blocker; this slice does not alter retry or rate
limit behavior.

## Current raw-boundary limit

The existing orders and sales endpoint contracts are declared as JSON objects
with `payload.data` arrays, while their live WB endpoints return a top-level
JSON array. The raw contract now admits array roots for these endpoint
metadata entries and preserves the HTTP response bytes in a separate immutable
blob with an SHA-256. No `{ "data": ... }` wrapper is generated. The orders
normalizer accepts both its historical fixture object shape and the live raw
array; this preserves existing fixture compatibility while production ingestion
uses the untouched array.
