STAGE 20.14 — EVIDENCE RESOLUTION SUMMARY (NO CODE CHANGE)

Status: ONLY DIAGNOSTIC. NO ADAPTER IMPLEMENTED. NO LIVE REQUESTS. NO CODE EDITS.

---

EVIDENCE FOUND (existing code/artifacts only — NO NEW WB CALLS):

B1 SKU -> NMID: NOT_RESOLVED
  Evidence: normalization.py FINANCE_DETAIL_FIELD_MAPPING requires "nmId"; legacy v5 payload uses "sku_id"; reconciliation/service.py uses "nm_id or seller_sku" (line 43) — different identity fields; fixtures/golden show "nmId: 1001, vendorCode: ART-1001" (different from "sku_id: 111"); no mapping table/file in repo.

B2 ORDER_ID -> RRDID: NOT_RESOLVED
  Evidence: FINANCE_DETAIL_FIELD_MAPPING: "rrdId" -> "source_record_id_input"; legacy payload has "order_id"; no mapping connecting "order_id" to "rrdId"; replay bundle uses "rrdId" (document-level); different semantics.

B3 DATE / SALEDT / RRDATE: PARTIALLY_PROVEN
  Evidence: legacy debug.json shows "operational_date" + "finance_date_used" + "finance_lag_days: 1" (confirmed lag mechanism); replay bundle has both "saleDt" and "rrDate"; adapter can safely receive "operational_date" and set "saleDt = operational_date"; "rrDate" cannot be proven from single "date" in legacy (only one date field); must document as NOT_PROVEN if only legacy source available.

B4 REVENUE -> RETAIL_AMOUNT / REALIZED_GROSS: NOT_PROVEN
  Evidence: legacy payload has "revenue" (positive float); V2 replay has "retailAmount"; no mapping contract proves "revenue == retailAmount" (different endpoint: statistics-api vs finance-api); adapter must not assume equivalence; no adapter contract proves semantic equivalence; adapter must either confirm domain or use NOT_PROVIDED.

B5 REBILL_LOGISTICS CLASSIFICATION: NOT_PROVEN
  Evidence: legacy payload has "rebill_logistic_cost: 0.0" (present, positive/zero raw); marketplace_policy.py confirms non-negative raw -> negative canonical; RebillLogisticsInput requires classification (LOGISTICS vs REVERSE_LOGISTICS); legacy payload has unclassified operation_type ("??????") — no direction evidence; adapter must not invent classification.

B6 REVENUE BASES (BUYER_DISCOUNTED / SELLER_PAYOUT / REALIZED_GROSS): NOT_PROVEN
  Evidence: legacy payload has "revenue", "gross_revenue", "realized_revenue", "seller_payout" all at same positive value (1100.0) for first row — collapsed; V2 RevenueBasis requires distinct views; no split evidence; adapter must not fabricate split.

---
CODE CHANGES: NONE (docs/STAGE_20_14_REPORT.md only; no tracked file changed).
NEW WB API REQUESTS: 0.
ENV / TOKEN / GIT / REPLAYBUNDLE / .env / FINANCE / NORMALIZATION / ENDPOINT_POLICY / REPLAY / AUDIT: UNCHANGED.
REPLAYBUNDLE INTEGRITY: finance_detail sha256 unchanged (3f4c...).
VERDICT: NO-GO FOR ADAPTER IMPLEMENTATION (design contract complete; 6 blockers unresolved; no assumption used; no code changed). Next requires either identity lookup source (B1/B2) or date contract confirmation (B3) or revenue confirmation (B4/B6) or rebill direction (B5) before adapter can be implemented safely.
