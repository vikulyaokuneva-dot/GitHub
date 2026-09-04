# Stage 18.7: Legacy Raw Capture Audit

## Scope and result

This document audits the existing legacy runtime only. It does not create a
ReplayBundle, replay adapter, capture adapter, synthetic input, or new business
logic. Legacy code and the Golden Fixture remain unchanged.

The scheduled production path has an in-process raw response boundary, but it
does not currently persist a complete, immutable, replayable collection of WB
responses. Consequently, an approved read-only legacy replay entry point does
not exist.

```text
LEGACY_RAW_CAPTURE_ENTRYPOINT = wb_api_core.client.WBApiClient.request_json
```

This is the earliest response boundary in the principal scheduled path. It is
not a CLI capture command and is not itself a ReplayBundle-compatible replay
entry point.

The following files are explicitly derived artifacts, not raw input. They were
not used to reconstruct raw requests or responses in this audit:

- `snapshot.json`
- `debug.json`
- `reconciled_rows.json`
- `report_payload_v2.json`
- `report_meta.json`

## 1. Actual legacy runtime path

The scheduled workflow is
[`D:/WB/Бот ИИ менеджер/GitHub/.github/workflows/daily.yml`](../../../.github/workflows/daily.yml).
Its `Run report` step invokes the following chain for the selected seller and
operational date:

```text
python -m wb_api_core.run_daily --seller <seller> --date <date>
  -> wb_api_core.run_daily.run_daily()
  -> wb_api_core.client.WBApiClient()
  -> wb_api_core.loaders.load_bundle()
  -> wb_api_core.normalize.normalize_bundle(raw_bundle)
  -> wb_api_core.reconcile.reconcile_bundle(raw_bundle, normalized_bundle, target_date)
  -> wb_api_core.snapshot.build_snapshot()
  -> wb_api_core.artifacts.write_artifacts()
     -> snapshot.json, debug.json, reconciled_rows.json

python -m v3.history.api_history_backfill --seller <seller> --date <date>
python -m v3.entry daily --seller <seller> --date <date>
  -> v3.entry._run_daily_for_seller()
  -> v3.pipeline.daily_input_stage.run_daily_input_stage()
  -> normally loads wb_api_core snapshot/reconciled artifacts
  -> v3.pipeline.daily_output_stage.run_daily_output_stage()
  -> report_v2.run_report_v2.build_report_v2_from_files()
     -> report_payload_v2.json, report_v2.pdf, email_v2.html, email_v2.txt
```

The concrete core entry point is
[`wb_api_core/run_daily.py`](../../../wb_api_core/run_daily.py). It constructs
the client, calls `load_bundle`, normalizes, reconciles, applies cache/fallback
logic, writes price history, builds snapshot/debug objects, and writes
artifacts. It is therefore a live, stateful command, not a read-only processor.

`v3.sync_from_entry` is not a data capture layer. The function is
[`v3/pipeline/daily_stage_support.py`](../../../v3/pipeline/daily_stage_support.py)
`sync_from_entry`; it imports names from `v3.entry` into a stage namespace.

## 2. WB clients

| Client | Code location | Runtime role | Raw-boundary status |
| --- | --- | --- | --- |
| `wb_api_core.client.WBApiClient` | [`wb_api_core/client.py`](../../../wb_api_core/client.py) | Principal client used by scheduled `wb_api_core.run_daily` | Authoritative capture boundary for the main path: `request_json()` receives `requests.request(...).json()` before loader extraction. |
| `v3.api.wb_client.WBApiClient` | [`v3/api/wb_client.py`](../../../v3/api/wb_client.py) | Alternate V3 live branch when a core snapshot is absent and a WB token exists | Separate response boundary, but not normally selected after the scheduled core run. |
| `v3.wb_client.WBClient` | [`v3/wb_client.py`](../../../v3/wb_client.py) | Legacy V3 helper, notably the advertising fallback (`LegacyAdsClient`) | Several methods map source responses before returning them; capture must happen before those mappings. |
| `src.wb_client.WBClient` | [`src/wb_client.py`](../../../src/wb_client.py) | Older/deprecated direct flow, not the scheduled daily core path | Its `_save_raw()` writes ad-hoc HTTP data under `out/raw`; this lacks an immutable manifest and is not a ReplayBundle entry point. |

The first three are the active client families relevant to the V3/core paths.
The fourth is recorded because it contains existing raw-file behavior, but it
does not alter the conclusion for the actual scheduled runtime.

## 3. Endpoints

The principal client endpoint constants are in
[`wb_api_core/client.py`](../../../wb_api_core/client.py), and the request
composition is in [`wb_api_core/loaders.py`](../../../wb_api_core/loaders.py).

| Logical source | Endpoint(s) | Loader behavior |
| --- | --- | --- |
| Orders | `GET /api/v1/supplier/orders` | Extracts rows into `raw_bundle["orders"]["rows_raw"]`. |
| Sales | `GET /api/v1/supplier/sales` | Extracts rows into `raw_bundle["sales"]["rows_raw"]`. |
| WB warehouse stocks | `POST /api/analytics/v1/stocks-report/wb-warehouses` | Paginates and concatenates extracted rows. |
| Final finance | `POST /api/finance/v1/sales-reports/detailed` | Extracts realization rows; may use the fallback below and date-lag attempts. |
| Finance fallback | `GET /api/v5/supplier/reportDetailByPeriod` | Used after primary-finance failure, including the 429 fallback path. |
| Cabinet commerce / sales funnel | `POST /api/analytics/v3/sales-funnel/products` | Paginates product rows and can use cabinet cache fallback. |
| Advert list | `GET /api/advert/v2/adverts` | Supplies advert IDs for statistics requests. |
| Advert statistics | `GET /adv/v3/fullstats` | Aggregated by the loader into per-SKU rows; original per-request payloads are not retained in the bundle. |
| Search groups | `POST /api/v2/search-report/table/groups` | Drives detail requests. |
| Search details | `POST /api/v2/search-report/table/details` | Projects selected fields into `all_rows`; full detail responses are not retained. |
| Product prices | `GET /api/v2/list/goods/filter` | Retains payload pages in memory as `raw_payload`. |
| FBS new orders | `GET /api/v3/orders/new` | Retains the response payload in memory as part of FBS price `raw_payload`. |
| FBS order history | `GET /api/v3/orders` | Retains history payload pages in memory as part of FBS price `raw_payload`. |

The alternate V3 client has its own endpoint declarations in
[`v3/api/endpoints.py`](../../../v3/api/endpoints.py). Those calls only become
the runtime source when `daily_input_stage` cannot load a valid core snapshot
and a live token is available.

## 4. Raw response boundary

In the main path, `wb_api_core.client.WBApiClient.request_json()` calls
`requests.request(...)`, then on HTTP 200 calls `response.json()` and returns a
dictionary containing the untouched decoded response as `payload`, together
with endpoint name, path, method, base URL, status, retries, and error
diagnostics.

`wb_api_core.loaders.load_bundle()` is the next boundary. It calls source
loaders and returns the pre-normalization `raw_bundle` with these top-level
sources:

```text
product_prices
fbs_order_prices
cabinet_commerce
finance_final
orders
sales
stocks
ads
search_report
```

Most loaders reduce the response immediately to `rows_raw`, which is extracted
endpoint data rather than a full response capture. The `ads` and
`search_report` loaders additionally aggregate/project response data before
their `rows_raw` result is returned. Price loaders are the exception: their
full payload pages remain temporarily available as `raw_payload`, and
`run_daily` calls `write_raw_price_payloads` for them.

`rows_raw` in the cabinet cache is therefore useful source evidence, but it is
not a complete raw request/response record: it lacks all requested endpoint
payloads, immutable integrity material, and complete request provenance.

## 5. Normalize entry point

`wb_api_core.normalize.normalize_bundle(raw_bundle)` in
[`wb_api_core/normalize.py`](../../../wb_api_core/normalize.py) is the legacy
normalization entry point. It accepts the in-memory `raw_bundle` returned by
`load_bundle`; normalizing a derived snapshot or a report payload is not the
same contract.

## 6. Reconcile entry point

`wb_api_core.reconcile.reconcile_bundle(raw_bundle, normalized_bundle,
target_date)` in [`wb_api_core/reconcile.py`](../../../wb_api_core/reconcile.py)
is the reconciliation entry point. It is called after normalization by
`run_daily` and before snapshot construction.

## 7. Snapshot entry point

`wb_api_core.snapshot.build_snapshot(...)` in
[`wb_api_core/snapshot.py`](../../../wb_api_core/snapshot.py) builds the core
snapshot from the reconciliation result. `wb_api_core.artifacts.write_artifacts`
in [`wb_api_core/artifacts.py`](../../../wb_api_core/artifacts.py) writes:

```text
cabinets/<seller>/artifacts/wb_api_core/<run_date>/snapshot.json
cabinets/<seller>/artifacts/wb_api_core/<run_date>/debug.json
cabinets/<seller>/artifacts/wb_api_core/<run_date>/reconciled_rows.json
```

`v3.core_report_bridge` reads `snapshot.json` and optionally `debug.json` from
this directory. `report_v2.run_report_v2.build_report_v2_from_files()` accepts
those derived files and creates the report payload, PDF, and email files. None
of these functions is a raw-input entry point.

## 8. Required configuration

Only variable and configuration names are recorded here; no credential values
were read or stored.

| Category | Names / source | Use |
| --- | --- | --- |
| Core live token | `WB_API_TOKEN` | Resolved by `wb_api_core.token_resolver.resolve_wb_api_token`. `WB_API_TOKEN_ENV_NAME` is a Python constant naming this variable, not a second configured environment variable. |
| HTTP base URLs | `WB_STATISTICS_BASE_URL`, `WB_FINANCE_BASE_URL`, `WB_ANALYTICS_BASE_URL`, `WB_ADVERT_BASE_URL`, `WB_PRICES_BASE_URL`, `WB_MARKETPLACE_BASE_URL` | Optional endpoint-family overrides for the principal client. |
| HTTP controls | `WB_API_TIMEOUT_SECONDS`, `WB_API_MAX_RETRIES`, `WB_API_GLOBAL_BUDGET` | Principal-client timeout, retry, and request-budget controls. |
| Dates | `TZ`, normally `Europe/Moscow`; `WB_MAX_FINANCE_LAG_DAYS` in the alternate V3 path | Determines operational-date handling and finance lag behavior. |
| Workflow selection | `WB_SELLER_ID`, `WB_REQUESTED_DATE`, `REPORT_VERSION` | Seller, requested date, and output/report branch. |
| Seller config | `v3` seller config loaded by `load_seller_config` | V3 stage configuration, including report-timezone resolution. |

## 9. Filesystem dependencies

The core command reads and writes state, so executing it is not read-only.
Relevant paths under repository root are:

| Path | Dependency |
| --- | --- |
| `cabinets/<seller>/artifacts/wb_api_core/<run_date>/` | Core snapshot/debug/reconciled output; later consumed by V3. |
| `cabinets/<seller>/artifacts/wb_api_core/cache/cabinet_commerce_daily/<date>.json` | Cabinet-commerce cache and fallback evidence. |
| `cabinets/<seller>/data/product_prices.sqlite3` | Updated by `PriceSnapshotStore` during `run_daily`. |
| `cabinets/<seller>/history/prices/raw/` | Price raw payload files written by `write_raw_price_payloads`. |
| `cabinets/<seller>/input/` | Seller-scoped local-report inputs scanned by V3. |
| `cabinets/<seller>/history/` | History/backfill state maintained by the workflow. |
| `out/raw/` | Default ad-hoc raw directory of the older `src.wb_client.WBClient`, outside the main scheduled core path. |

`run_daily` also reads latest/same-operational snapshots and may apply those
fallbacks. A replay must not silently inherit such filesystem state.

## 10. Credential requirements

Live WB capture requires a WB API credential exposed as `WB_API_TOKEN`.
No credential is needed to load an already captured immutable bundle, but no
such loader exists in legacy today.

Email delivery has separate credentials (`YANDEX_SMTP_USER`,
`YANDEX_SMTP_APP_PASS`, `EMAIL_TO`) in the workflow. They are not required for
WB capture, normalization, reconciliation, or raw replay analysis. No actual
tokens, values, or secrets were inspected, emitted, or committed.

## 11. Read-only capture possibility

There is no existing read-only capture command or mode.

- `wb_api_core.run_daily.run_daily()` creates a live client and calls networked
  loaders.
- It reads caches and may apply cache/snapshot fallbacks.
- It writes core artifacts, finance cache, price SQLite history, and price raw
  payload files.
- It therefore cannot be invoked as a read-only operation on a saved payload.

The technical interception point for a future live capture is
`WBApiClient.request_json()` before a loader extracts or aggregates `payload`.
Such a change would need to serialize each response with request metadata,
retrieval timestamp, tenant scope, operational date, source identifiers, and
hashes. It is deliberately not implemented by Stage 18.7.

## 12. ReplayBundle compatibility

The pure-function-shaped portion of the legacy core can be described as:

```text
correctly shaped raw_bundle
  -> normalize_bundle(raw_bundle)
  -> reconcile_bundle(raw_bundle, normalized_bundle, target_date)
  -> build_snapshot(...)
```

However, no existing public entry point accepts a versioned immutable
ReplayBundle, verifies its manifest, constructs that precise `raw_bundle`, or
disables filesystem fallbacks. `load_bundle()` requires a live `WBApiClient`
and triggers endpoint calls; it cannot load captured responses.

Creating a mapping from a future ReplayBundle's raw endpoint records to the
legacy `raw_bundle` would be a new replay adapter. Stage 18.7 explicitly does
not create it. Existing price raw files and cabinet-cache `rows_raw` are also
insufficient: they do not cover all endpoint requests or provide a manifest
and immutable provenance for one coherent run.

## 13. Remaining blocker

**EXPLICIT BLOCKER: no approved read-only legacy entry point accepts a
ReplayBundle or a complete captured collection of raw WB responses.**

The scheduled production flow preserves only selected raw fragments (price
payload files and some extracted cache rows) and otherwise writes derived
artifacts. A true parity replay cannot safely use those artifacts as raw input.

To remove this blocker in a separately approved future stage, two independent
pieces of work are required:

1. A live capture facility at the `request_json()` boundary that writes every
   response and request/provenance record into an immutable, hashed bundle.
2. A read-only legacy replay adapter/entry point that consumes that exact
   bundle, constructs the legacy pre-normalization input without network or
   fallback state, and proves its behavior with parity tests.

Neither item is implemented here.
