STAGE 20.17 PASS — FIRST FAILURE HANDLED

CHANGE: apps/api/main.py line 252 — except expanded by RuntimeError; 503 for transport errors; 400 preserved for lookup/value errors.
NO NEW LIVE WB REQUESTS: 0
CODE / CONTRACT / REPLAY / FINANCE / NORMALIZATION / MARKETPLACE / ABS / ENV / GIT: UNCHANGED
REPLAY: finance only (sha256 3f4c...)
FIRST FAILURE: WB 429 → RuntimeError (transport.py:104) → caught at main.py → HTTP 503 (controlled, not 500)
VERDICT: STAGE 20.17 PASS; adapter not implemented; Stage 20.18 not started.
