# Raw Capture Instrumentation

## Purpose

Stage 18.8A adds an opt-in transport instrumentation boundary for capturing
real WB API responses before legacy processing. It is not a replay adapter,
does not create ReplayBundle cases, and is not connected to `run_daily`.

The only legacy hook is:

```text
wb_api_core.client.WBApiClient.request_json()
  -> requests.request(...)
  -> response.json()
  -> optional RawCaptureWriter.capture(...)
  -> existing response dictionary
```

The call occurs only for successful HTTP 200 JSON responses and before any
loader extracts rows, aggregates values, normalizes, reconciles, calculates
finance, builds a snapshot, or builds a report.

## Enablement

Capture is disabled by default. Existing callers that construct
`WBApiClient()` or `WBApiClient(token)` retain legacy behavior and create no
capture files.

An explicit caller must construct `RawCaptureWriter` with a new, separate
destination, then pass it as `capture_writer` to `WBApiClient`. The caller owns
the capture ID, tenant/account scope, and operational date. No environment
variable silently enables capture, and `run_daily` does not enable it.

```python
from wb_api_core.client import WBApiClient
from wb_api_core.raw_capture import RawCaptureWriter

writer = RawCaptureWriter(
    destination="D:/approved-captures",
    capture_id="wb-capture-001",
    tenant_id="approved-tenant-scope",
    account_id="approved-account-scope",
    operational_date="2026-08-25",
)
client = WBApiClient(capture_writer=writer)
```

This snippet is an instrumentation setup example only. It is not permission to
perform live capture and contains no credential value.

## Output contract

The writer creates one isolated directory only after the first safe response:

```text
<explicit destination>/<capture_id>/
  manifest.json
  raw/
    0001_<endpoint>.json
```

The canonical JSON bytes in each raw file determine the recorded SHA-256 and
byte length. `manifest.json` is canonically serialized, making its field order
deterministic for the same inputs and clock values.

For every capture object the manifest records:

- endpoint name, relative path, and HTTP method;
- safe request metadata (`params` and non-GET JSON body only);
- raw decoded JSON response;
- UTC retrieval timestamp;
- supplied tenant/account scope and optional operational date;
- source metadata and optional source identifier;
- HTTP status code;
- SHA-256 and byte length of the raw file.

The capture directory is separate from legacy artifact paths. The writer never
writes `snapshot.json`, `debug.json`, `reconciled_rows.json`,
`report_payload_v2.json`, cache files, or SQLite.

## Security behavior

Before every write, the writer recursively scans request metadata, payload,
source identifier, and generated manifest. It rejects credential-like fields
including `Authorization`, token/API-key/secret/password/cookie/credential
names, known bearer/basic-style values, and credential-looking URL query
parameters. Unknown credential-like material is rejected, never masked.

The hook never passes HTTP headers, cookies, `Authorization`, full request URLs,
or client tokens to the writer. A rejected value or I/O error raises
`RawCaptureError` loudly. The client does not retry this failure or return a
modified legacy response.

## Boundaries

The instrumentation only observes and serializes the decoded response. It does
not mutate the payload or response object, call legacy normalize/reconcile,
finance, snapshot, report generation, caches, or SQLite. It does not validate
or load a ReplayBundle and does not provide legacy replay.

Real capture remains a separate manual operation with an approved credential.
