STAGE 20.16 — FIRST FAILURE POINT (VERIFIED FROM EXISTING DATA ONLY; NO NEW WB CALLS)
FIRST FAILURE: Transport layer (WBApiClient → 429) → RuntimeError (wb_sales_funnel_transport.py line 104) → unhandled at main.py line 246 (missing except RuntimeError) → HTTP 500 (not 429, not partial, not 200).
VERIFICATION METHOD: replay_bundle normalization (PASS); replay_bundle audit (audit_status=partial); legacy debug artifacts (2026-07-26); no new live WB requests; no code changes.
VERDICT: FIRST_FAILURE = TRANSPORT_ERROR_HANDLING; separate ROOT_CAUSE_500 = UNHANDLED_RUNTIME_ERROR.
CODE CHANGED: NONE. NEW WB REQUESTS: 0. NEXT: handle RuntimeError gracefully (not in this stage — design only); adapter contract remains NO-GO (STAGE 20.15 / 20.11 blockers).
