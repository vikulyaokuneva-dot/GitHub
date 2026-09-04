# Replay Bundle Contract

## Purpose

Stage 18.6 provides the capture and read boundary needed for genuine legacy
versus target replay. It deliberately contains no legacy adapter and no real
case because the repository has no qualifying immutable raw capture yet.

The loader never reconstructs an endpoint payload from `reconciled_rows.json`,
report payloads, normalized snapshots, or any derived artifact. It never
normalizes data, invokes Finance, imports legacy, or writes a fixture.

## Versioned Format

```text
tests/fixtures/replay/
  <case_id>/
    manifest.json
    metadata.json
    raw/
      <endpoint>.json
```

Both JSON control files use schema version `replay-bundle-v1`. `<case_id>` is
a stable lowercase identifier and every case is classified exactly as
`real_raw_capture`; synthetic and derived parity cases are rejected.

`metadata.json` declares one tenant/account scope and one raw-object metadata
record per payload. A record contains a deterministic object ID, endpoint
metadata and schema version, source identifier, request scope, UTC retrieval
timestamp, operational date, and payload path.

`manifest.json` lists every `raw/<endpoint>.json` path with its SHA-256 hash
and byte length. Metadata paths and manifest paths must match exactly. Any
changed, missing, renamed, or unlisted raw payload fails loading.

## API

```python
from packages.wb_core.replay import load_replay_bundle

bundle = load_replay_bundle("captured-wb-2026-08-20-seller-001")
```

The result contains immutable `RawObject` values. The loader validates schema,
scope, source/endpoint consistency, and UTC timestamps. It returns no
normalized fact, finance input/result, report payload, or legacy output.

## Legacy Adapter Gate

There is no legacy runner adapter. Existing legacy scheduled paths accept live
API/config/filesystem-oriented inputs, while the current target replay loader
returns typed raw objects. No approved direct legacy entrypoint accepting this
bundle contract was found. Creating an adapter from derived artifacts is
prohibited; creating a new direct raw legacy adapter requires a separate
review after a real capture exists.

## Capture Requirements

1. Capture raw WB endpoint responses before normalization.
2. Store request scope, source/API/schema metadata, stable source identifier,
   tenant/account scope, operational date, and UTC retrieval timestamp.
3. Remove credentials, tokens, cookies, and secrets before storage; the raw
   object validation rejects credential-like data.
4. Compute the manifest SHA-256 hashes after final redaction and never edit
   raw payloads in place.
5. Pair each target replay case with the exact legacy invocation inputs only
   after a separately approved direct legacy runner boundary is defined.

## Current Status

Stage 18.6 is complete as infrastructure. Real replay remains blocked pending
captured raw WB API bundles; Stage 19 must not start automatically.
