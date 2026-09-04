# Stage 19 Closed: BLOCKED_BY_SCOPE_CONTRACT

## Final Migration Disposition

Stage 19 replay/parity is closed as `BLOCKED_BY_SCOPE_CONTRACT`. The replay
infrastructure remains prepared for a future authoritative tenant/account
scope, but no further replay, Legacy parity adapter, or tenancy workaround will
be added.

The Final Migration Mode was also assessed against the existing V2 production
input boundary. A real V2 WB ingestion cannot start safely in the current
repository because the production scope and persistence prerequisites do not
exist:

- `RawObject` requires an authoritative `TenantAccountScope` with real
  `tenant_id` and `account_id` UUIDs.
- Neither AI Director 2 configuration nor the approved Project 1 configuration
  supplies those identities; the only authoritative ownership value is
  `seller_id`.
- The only available raw-object repository is
  `InMemoryRawObjectRepository`, explicitly test-only. There is no production
  tenant/account repository, account registration, or durable raw storage.

Using a seller ID as a UUID, deriving UUIDs, creating a replay-only context,
or bypassing `RawObject` would violate the Final Migration constraints and
would not be a production V2 run. No such workaround was implemented.

This is a production-input incompatibility, one of the stated Final Migration
stop conditions. No WB request, raw capture, V2 finance run, or report was
started from this incomplete production boundary.

## Result

The Project 1 credential source was found and used only as a process-local
runtime value. No credential value was copied, logged, committed, written into
a capture, or added to AI Director 2 configuration.

Project 1 source discovery found these local configuration sources:

| Source | Finding | Use |
| --- | --- | --- |
| `D:/WB/Бот ИИ менеджер/AI Director/.env` | Non-empty `WB_API_TOKEN` is configured | Used only to set `WB_API_TOKEN` for one child process. |
| `D:/WB/Бот ИИ менеджер/GitHub/.env` | Non-empty `WB_API_TOKEN` is configured | Confirmed as a local configuration source; its value was not read into source control or artifacts. |
| `D:/WB/Бот ИИ менеджер/AI Director/cabinets/seller_001/config.yaml` | `seller_id: seller_001`, `wb.token_ref: WB_API_TOKEN` | Identifies the seller and secret reference, but not tenant/account UUID ownership. |
| Project 1 `.vscode/tasks.json` | Launches `python -m v3.entry daily` | Does not supply an alternative token or ownership scope. |

The runtime credential passed a first read-only health request through
`wb_api_core.client.WBApiClient` to the product-prices endpoint:

```text
authentication: confirmed
HTTP status: 200
response shape: JSON object
```

No WB write endpoint was called. A later probe to the same endpoint returned
HTTP 429; no further network requests or capture attempts were made.

## Stage 19B decision

Stage 19B approved a replay-only `seller_id` source scope and a possible
`ReplayContext`, while expressly prohibiting any production tenancy change,
UUID fabrication, and fake conversion to `TenantAccountScope`.

The isolated scope can safely exist in ReplayBundle metadata as:

```text
scope_type = seller
scope_mode = replay_only
seller_id = <authoritative Project 1 seller_id>
```

However, it cannot reach the existing V2 production pipeline under the stated
constraints. A replay-only metadata type is not accepted by the first target
runtime boundary, `RawObject`.

The target replay loader returns `RawObject` values, and `RawObject.scope` is
`TenantAccountScope`, whose two fields are UUIDs. That type is then copied into
canonical provenance and required by the target repository, reconciliation,
operational, Finance, COGS, and tax contracts. The following runtime paths
would require semantic type changes, not merely a metadata extension:

```text
packages/wb_core/contracts.py
  TenantAccountScope -> RawObject -> InMemoryRawObjectRepository
packages/data/canonical.py
  CanonicalSourceMetadata.scope
packages/reconciliation/contracts.py and service.py
packages/operational/contracts.py and service.py
packages/finance/contracts.py
packages/products/contracts.py
packages/tax/contracts.py
```

Replacing a UUID tenant/account scope with a seller scope across those paths
would alter the cross-account isolation contract and require broad regression
coverage. A seller-only field in replay `metadata.json` would not solve this:
the loader could no longer create V2 `RawObject` values, so it would not enable
the required V2 replay.

Creating a `ReplayContext` that bypasses `RawObject` would require duplicating
or changing the target normalizers, canonical provenance, operational
aggregation, reconciliation, and finance flow. That would be a separate V2
business-pipeline implementation, not a minimal technical adapter, and could
not establish parity with the existing V2 path. Constructing a
`TenantAccountScope` inside the adapter would violate the explicit prohibition
on fake UUIDs regardless of whether it is labeled replay-only.

## Explicit blocker

**The requested ReplaySourceScope → ReplayContext → existing V2 replay route
is impossible without either changing production tenancy-bearing contracts or
manufacturing a prohibited UUID scope.**

This is not a credential blocker. Authentication is available. It is a data
identity and format blocker:

1. The target V2 replay pipeline begins with `RawObject`, which strictly
   requires `TenantAccountScope`; it has no replay-only source-scope boundary.
2. `RawCaptureWriter` writes `wb-api-raw-capture-v1` with a capture manifest.
   The replay loader accepts only `replay-bundle-v1` with separate
   `manifest.json`, `metadata.json`, and `raw/<endpoint>.json` files.
3. `RawCaptureWriter` accepts arbitrary non-empty tenant/account strings. The
   replay contract requires `TenantAccountScope` UUID values. Project 1's
   seller configuration provides only `seller_id` and has no authoritative
   tenant UUID or account UUID mapping. Inventing UUIDs, deriving them from
   `seller_id`, or using `seller_id` as a fake UUID is prohibited.
4. The capture hook can capture any successful endpoint response, but the
   replay contract currently admits only a fixed endpoint set and expects raw
   JSON objects. The proven health endpoint (`/api/v2/list/goods/filter`) has
   no current `EndpointMetadata` entry. Several operational WB endpoints can
   return top-level arrays, which the current loader rejects before
   normalization.
5. A conversion from capture output to `replay-bundle-v1` would itself be a
   new capture-to-bundle adapter. It can be implemented deterministically only
   after the output scope is authoritative and the selected endpoints have
   compatible `EndpointMetadata` and payload-shape policies.

## What was not done

- No raw WB response was stored after the health check.
- No `tests/fixtures/replay/<case_id>` directory was created.
- No tenant/account scope was invented from `seller_id`.
- No snapshot, debug, reconciled rows, report payload, cache, or local report
  was used as raw input.
- No legacy replay adapter, V2 replay, finance calculation, or parity report
  was run.
- No Stage 9 sign policy, Golden Fixture, legacy metric semantics, or business
  pipeline was changed.

## Required unblock decision

A separately approved narrow change must establish both:

1. An authoritative UUID tenant/account scope for the Project 1 seller; or a
   separately approved change introducing a replay-only execution pipeline
   with its own canonical and financial contracts. The latter is not a
   version-compatible adapter to the existing V2 pipeline.
2. After the scope decision, a compatible, immutable mapping from the approved raw capture records to
   `replay-bundle-v1`, including the endpoint metadata/payload-shape policy for
   the selected real endpoints.

After that decision, rerun an explicit live capture only after the WB rate
limit window permits it, then validate the resulting bundle and proceed with
read-only Legacy versus V2 parity.
