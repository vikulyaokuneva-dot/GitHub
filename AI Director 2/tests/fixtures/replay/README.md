# Replay Bundle Capture Format

This directory intentionally contains **no synthetic or reconstructed parity
case**. A case added here must be a redacted `real_raw_capture` from the WB
API, captured before normalization.

```text
replay/
  <case_id>/
    manifest.json
    metadata.json
    raw/
      <endpoint>.json
```

`metadata.json` declares one tenant/account scope, the UTC capture timestamp,
and one raw-object record for every endpoint payload. Each raw-object record
contains its endpoint metadata, source identifier, object ID, request scope,
UTC retrieval timestamp, and operational date.

`manifest.json` has schema version `replay-bundle-v1` and one SHA-256 plus byte
length for every file under `raw/`. The loader rejects missing, renamed,
modified, or unlisted payloads. It returns immutable `RawObject` values and
does not normalize, calculate finance, execute legacy, or read derived legacy
artifacts.

Do not create a case from `reconciled_rows.json`, report payloads, normalized
snapshots, or derived artifacts. Keep credentials, tokens, and secrets out of
capture payloads and metadata.
