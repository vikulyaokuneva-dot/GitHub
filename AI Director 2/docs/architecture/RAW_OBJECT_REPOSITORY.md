# Raw Object Repository

## Purpose

`packages/wb_core` provides the Stage 2 contract for preserving a raw WB API
response before normalization. It establishes deterministic, scoped access to
an immutable raw object without creating a database, object-store integration,
network client, cache, finance calculation, report dependency, or legacy
dependency.

The contract is the first link in the target flow:

```text
WB client -> ingestion boundary -> RawObjectRepository -> normalizer -> domain facts
```

The Stage 2 code implements only the repository portion and one synthetic
read-only scenario. A future WB client is responsible for transport and may
call `save` only at the ingestion boundary.

## Responsibilities

- Retain source, endpoint, object type, schema version, request scope, raw
  payload, operational identity, and retrieval metadata together.
- Require a trusted `TenantAccountScope` for every save/read/list operation.
- Keep `operational_date` separate from `retrieved_at`.
- Reject credential-like fields and values before an object is admitted.
- Return deep-copied raw objects so consumer mutation cannot damage stored
  payloads.
- List objects deterministically by `object_id` within one tenant/account.

## Non-Responsibilities

- No network calls, credential lookup, retries, rate limiting, pagination
  execution, filesystem persistence, database persistence, caching, or event
  bus.
- No normalization, finance, sales, logistics, advertising, analytics, report,
  PDF, email, AI, or automation logic.
- No computation or interpretation of raw numeric fields. Raw money-like
  values are retained exactly as supplied by the synthetic source payload.
- No direct legacy, `report_v2`, or `core_report_bridge` dependency.

## RawObject Contract

`RawObject` is defined in `packages/wb_core/contracts.py` and contains:

| Field | Meaning |
| --- | --- |
| `object_id` | deterministic immutable ingestion identity; 64 lowercase hex characters |
| `scope` | trusted tenant/account ownership boundary |
| `endpoint` | `EndpointMetadata` describing the static endpoint contract |
| `object_type`, `source`, `schema_version` | repeated identity fields validated against endpoint metadata |
| `retrieved_at` | required UTC retrieval timestamp |
| `operational_date` | WB business date, when required by endpoint semantics |
| `request_scope` | safe request parameters, excluding headers/credentials |
| `payload` | raw source object without credential-like content |

`retrieved_at` is retrieval metadata, never a substitute for
`operational_date`. The synthetic object belongs to `2026-08-20` and was
retrieved at `2026-08-24T10:30:00Z`; both values are preserved independently.

## EndpointMetadata Contract

Stage 2 registers one endpoint only: `sales_funnel_products`.

| Property | Value |
| --- | --- |
| HTTP method | `POST` |
| Logical domain | `analytics` |
| Object type | `sales_funnel_products` |
| Source | `wildberries` |
| Expected payload kind | `object` |
| Data class | `operational` |
| Operational-date semantics | `requested_business_day` |
| Pagination | `offset_limit` |
| Schema version | `analytics-v3` |

This metadata describes a contract. It is not a WB SDK and does not make a
request. Additional endpoints must be introduced independently with their own
contract tests and fixtures.

## Repository Contract

`RawObjectRepository` exposes three methods:

```python
save(raw_object: RawObject) -> None
get(*, scope: TenantAccountScope, object_id: str) -> RawObject
list(*, scope: TenantAccountScope, endpoint_name: str | None = None) -> tuple[RawObject, ...]
```

`save` is intentionally an ingestion-only mutation boundary. Domain consumers
receive read copies through `get` or `list`. The Stage 2 implementation,
`InMemoryRawObjectRepository`, is deterministic and test-only; its identity is
`(tenant_id, account_id, object_id)`. Duplicate identities raise
`DuplicateRawObjectError`; missing/scoped-away objects raise
`RawObjectNotFoundError`.

## Immutability Rules

1. Admission deep-copies `request_scope` and `payload`.
2. The in-memory repository deep-copies again on save.
3. Every read returns a fresh deep copy.
4. Modifying a source payload after `save` cannot alter storage.
5. Modifying a payload returned by `get` or `list` cannot alter storage.

The current model is frozen at the object-field level. Deep-copy isolation is
the enforcement mechanism for nested raw JSON structures, which stay
JSON-compatible for the later normalization boundary.

## Security Rules

The contract rejects nested credential-like field names containing:

```text
authorization, api_key, apikey, token, client_secret, secret,
password, cookie, credential
```

It also rejects string values beginning with `Bearer `, `Basic `, or `sk-`, as
well as values containing `WB_API_TOKEN`.
Raw request headers are not represented; callers must store only safe request
parameters in `request_scope`. This is intentionally conservative. A future
credential vault belongs behind a separate trusted interface and must never be
stored inside `RawObject`.

## Synthetic Scenario

`packages/wb_core/synthetic_scenario.py` provides a complete reproducible path:

```text
synthetic request scope
  -> sales_funnel_products endpoint metadata
  -> synthetic raw payload
  -> RawObject
  -> InMemoryRawObjectRepository.save
  -> scoped read-only get
```

The fixture is hard-coded synthetic data, has no credentials, uses no network,
and does not share or modify the Stage 1 golden fixture. It intentionally stops
before normalization.

## Future Extension Points

- Replace the in-memory implementation with a PostgreSQL metadata repository
  and object-storage payload repository behind the same protocol.
- Add endpoint registry lookup and per-endpoint request/rate-limit policies.
- Add idempotent ingestion request fingerprints and ingestion job provenance.
- Create the Stage 3 canonical normalization contract that reads `RawObject`.
- Add schema-versioned raw payload validation without changing raw retention.

No finance kernel, report migration, or legacy client adapter is authorized by
this Stage 2 contract.
