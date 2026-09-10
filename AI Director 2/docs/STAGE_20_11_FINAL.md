STAGE_20_11_FINAL

Status: ADAPTER_SPEC_READY (design complete) / NO-GO (implementation blocked)
Blockers (confirmed from existing artifacts + contracts):
  1. SKU_ID -> NMID (NOT_PROVEN 1:1 mapping; adapter must resolve or NOT_PROVIDED)
  2. ORDER_ID -> RRDID (NOT_PROVEN equality; adapter must not assume)
  3. DATE / SALEDT / RRDATE (NOT_PROVEN — lag-1 from debug.json; adapter requires proof)
  4. REVENUE -> RETAIL_AMOUNT / REALIZED_GROSS (NOT_PROVEN — 100==100 not proof; different endpoints)
  5. REBILL_LOGISTICS CLASSIFICATION (NOT_PROVEN — LOGISTICS vs REVERSE_LOGISTICS; adapter must not invent)
  6. REVENUE BASES (BUYER_DISCOUNTED / SELLER_PAYOUT / REALIZED_GROSS separation from single `revenue` field — adapter requires domain confirmation)
Contract: ADAPTER_BOUNDED (input = LegacyStatisticsFinanceAdapter from statistics-api / v5; output = V2 FINANCE_DETAIL compatible; uses NO abs(); uses NO float arithmetic; NO invention of missing values; NO fabrication of identity/date/classification; NO code written; NO new WB requests; NO ReplayBundle change; NO .env change; NO Finance Kernel change; NO normalization change)
Files: docs/STAGE_20_11_REPORT.md (created) — contains full adapter contract (§1-§19), field matrix (§4), sign contract (§5), date contract (§6), identity contract (§7), failure policy (§9), provenance (§15), final verdict ADAPTER_SPEC_READY / NO-GO with blockers list (§10, §20).
No production adapter file created (per instruction — design only).
No code changed (verified: replay.py, contracts, endpoint_policy, loaders, audit, analysis unchanged from previous stages; docs/ reports new only).
No new HTTP requests to WB (only existing artifacts read: .tmp/replay_fixtures/, cabinets/seller_001/v5/, .tmp/debug.json, replay_bundle, existing contracts/code).
No secret/token/log exposed.
STOP CONDITION MET: stage ends with design complete; next stage (20.11+) requires resolving identity/date/rebill classification before adapter implementation.
