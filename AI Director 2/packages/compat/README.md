# Compatibility boundary

Only this package may import proven legacy code from the repository root. New
domain packages must depend on interfaces, not on `v3`, `src`, `report_v2` or
`wb_api_core` directly.

## Golden snapshot gate

`legacy_snapshot_parity.py` is a read-only migration harness. It replays the
legacy `normalize -> reconcile -> snapshot` pipeline for the purely synthetic
fixture in `tests/fixtures/golden/wb_core_snapshot_v1/` and compares the result
with the immutable expected snapshot.

The manifest carries SHA-256 hashes of canonical parsed JSON. A fixture update
must deliberately update its expected snapshot and manifest hash; it must not
contain seller data, raw production payloads, tokens, or credentials.

Run the gate from this project directory:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/unit/test_legacy_snapshot_parity.py -q
```

The harness is not a production WB client and never performs network requests
or writes files.
