# Stage 18.8 Blocker: Approved Raw Capture Boundary

## Resolution

Stage 18.8A resolves the Stage 18.8 instrumentation blocker with one approved,
minimal legacy change and one isolated capture helper. The confirmed raw
boundary remains:

```text
wb_api_core.client.WBApiClient.request_json
```

`request_json()` receives `requests.request(...).json()` and returns that
decoded response as `payload` before any loader extraction, normalization,
reconciliation, finance calculation, snapshot construction, or report build.
The response is therefore suitable in principle for a future raw capture.

The hook is now implemented in
[`wb_api_core/client.py`](../../../wb_api_core/client.py):
`WBApiClient.__init__` accepts an optional `capture_writer`, and
`WBApiClient.request_json` invokes its `capture` method immediately after a
successful `response.json()` and before returning the existing response
dictionary. The writer is disabled by default because its default value is
`None`.

## Evidence

In `WBApiClient.request_json()`:

```text
requests.request(...)
  -> response.json()
  -> { endpoint, path, payload, status_code, method, base_url, retry metadata }
```

This occurs before callers in
[`wb_api_core/loaders.py`](../../../wb_api_core/loaders.py) project the
response into `rows_raw`, aggregate advertising values, or project search
details. Capture after `load_bundle()` would therefore be incomplete and, for
some endpoint families, semantically transformed.

No supported callback, observer, injectable transport, or capture destination
is present on `WBApiClient`. The only existing raw-file writer is the older
`src.wb_client.WBClient._save_raw`; it is not the scheduled production client,
does not provide a complete capture contract, and must not be reused as a
ReplayBundle capture mechanism.

## Approved implementation

The hook has no effect when no `capture_writer` is supplied. In that default
mode it creates no files, makes no additional requests, and retains the exact
existing return value, retries, authentication, request construction, ordering,
and error behavior.

When explicitly supplied, the separately owned
[`wb_api_core/raw_capture.py`](../../../wb_api_core/raw_capture.py)
`RawCaptureWriter` receives the decoded raw response and safe request metadata.
It writes only to the caller-provided capture destination:

```text
<explicit destination>/<capture_id>/
  manifest.json
  raw/
    0001_<endpoint>.json
```

It records payload SHA-256 and byte length, UTC retrieval time, supplied
tenant/account scope, optional operational date, endpoint/path/method, source
metadata, and HTTP status. It never writes legacy artifacts, report payloads,
snapshots, cache files, or SQLite.

The writer recursively rejects credential-like keys and values in request
metadata, response payload, source identifier, and generated manifest before
writing the captured object. It does not redact unknown values. It never
receives `Authorization` headers, cookies, or the request URL. A capture error
raises `RawCaptureError` directly from `request_json`; it is not retried or
converted into a legacy API result.

## Historical blocker rationale

Before Stage 18.8A, a separate target-side component could not observe this
value without one of the following prohibited approaches:

- modifying `wb_api_core.client.WBApiClient.request_json`;
- monkey-patching legacy runtime behavior;
- capturing from extracted `rows_raw`, cache files, snapshots, or reports;
- rerunning `wb_api_core.run_daily`, which performs network calls and mutable
  filesystem/SQLite work.

The first option is a legacy-code change. The remaining options do not meet the
Stage 18.8 raw-boundary or read-only requirements.

## Preserved behavior

No capture mode is wired into `run_daily`; no production capture was run.
`normalize`, `reconcile`, `snapshot`, `report_v2`, finance, V3 semantics,
endpoint behavior, caches, and SQLite remain unchanged. The Golden Fixture is
unchanged. The hook is instrumentation only; it is not a replay adapter or a
ReplayBundle loader.

Focused tests in
[`wb_api_core/tests/test_raw_capture.py`](../../../wb_api_core/tests/test_raw_capture.py)
prove the disabled default, raw payload persistence, unchanged returned object,
SHA-256/byte length/UTC/scope metadata, credential and `Authorization`
rejection, loud capture failures without retries, and absence of normalization
or reconciliation calls.

Stage 18.8A is complete. Stage 19 must not start automatically.
