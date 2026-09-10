# Stage 20.10 — VERIFY LEGACY FINANCE FALLBACK COMPATIBILITY WITH V2

**Status: DIAGNOSTICS ONLY. Code unchanged. No new WB API requests. Report from existing artifacts only.**

---

## 1. EVIDENCE (existing artifacts only — no new HTTP requests)

### A. V2 FINANCE-DETAIL REPLAY BUNDLE (verified live capture)
- **File**: `.tmp/replay_fixtures/live-4297720-fd-2026-08-27/raw/finance_detail.json`
- **Type**: JSON `array` (`list`) of ~100 dict objects (verified by `json.load`; first-row keys include `nmId`, `supplierArticle`, `saleDt`, `rrDate`, `rrdId`, `retailAmount`, `retailPriceWithDiscRub`, `ppvzForPay`, `quantity`, `rebillLogisticCost`, etc.)
- **Payload sha256**: `3f4c9f2c82844a40c22baab69a114ee12bccbc7f54bf6e743a4d6de78778751c`
- **Byte length**: 252441
- **Endpoint**: `FINANCE_DETAIL` (`finance-api`, POST `/api/finance/v1/sales-reports/detailed`)
- **Scope**: authoritative UUID from `wb_autopilot.sqlite3`

### B. LEGACY STATISTICS-API RAW ARTIFACT (from `cabinets/seller_001/v5/data/raw_2026-04-01.json` + `v5/artifacts/debug/raw_bundle.json`)
- **Source file marker**: `"source_file": "api:reportDetailByPeriod"`
- **Top type**: `dict` (`NOT array`; `NOT same as V2 finance-detail`)
- **`period_date`**: `2026-04-01`; **`source`**: `"api"`; **`operational_day`** from `report_meta.json`: `2026-04-01`; **`finance_date_used`** from `api_debug.json`: `2026-03-31`; **`finance_lag_days`**: 1
- **Sections**: `ads`, `orders`, `margins`, `returns`, `ratings`
- **`orders` section** — 2 rows; keys: `order_id`, `sku_id`, `quantity`, `revenue`, `commission`, `date` (`2026-03-31`), `gross_revenue`, `realized_revenue`, `seller_payout`, `logistics`, `storage`, `penalties`, `deductions`, `loyalty_program`, `loyalty_points_withheld`, `acquiring`, `pvz_service`, `other_adjustments`, `rebill_logistic_cost` (`0.0`), `source_file: "api:reportDetailByPeriod"`, `raw_row_index`
- **`rebill_logistic_cost`**: `0.0` (present, numeric, sign positive/zero)
- **Monetary fields**: `float` in JSON (e.g., `revenue: 1100.0`, `commission: 120.0`) — V2 contract requires `Decimal`; normalization (`data/normalization.py`) validates; legacy float must be converted by adapter.
- **Dates**: `date` (`2026-03-31`) — operates as operational/transaction date (lag-1 from period `2026-04-01`); **NO separate `saleDt`/`rrDate` fields**.
- **`nmId` / `supplierArticle`**: **ABSENT** (only `sku_id` in legacy)
- **`retailAmount`**: **ABSENT** (only `revenue` in legacy)
- **`retailPriceWithDiscRub`**: **ABSENT**
- **`ppvzForPay`**: **ABSENT** (only `seller_payout: 0.0`)
- **`deliveryPrice`**: **ABSENT**
- **`storage_fee`**: present as `storage` (`0.0`)
- **`penaltyAmount`**: present as `penalties` (`0.0`)
- **`acquiring_fee`**: present as `acquiring` (`0.0`)
- **`tax`**: **ABSENT**
- **`advertising`**: **ABSENT** (separate `ads` array exists but not within finance rows)

---

## 2. LEGACY PAYLOAD STRUCTURE (ACTUAL — NOT NORMALIZED)

- **Top-level type**: `dict` (`{"cabinet_id": "seller_001", "period_date": "2026-04-01", "source": "api", ...}`) — **COMPLETELY DIFFERENT STRUCTURE FROM V2 FINANCE-DETAIL ARRAY**.
- **Not a direct replacement**: V2 expects an array of financial rows (`FINANCE_DETAIL` endpoint); Legacy `v5` payload is a composite cabinet bundle (orders + margins + returns + ratings + ads) derived from `reportDetailByPeriod` via compatibility layer (`v2_compat` per `debug.json` `ingestion_path`).
- **`orders` array** (not `data[].rows[]` but direct array at `orders`) has 2 rows with fields appropriate to legacy v5 report, **NOT** the V2 `FINANCE_DETAIL` schema.

---

## 3. V2 FINANCE-DETAIL STRUCTURE (ACTUAL — FROM REPLAY BUNDLE)

- **Type**: `list` (JSON `array`)
- **Each item**: `dict` with keys: `saleDt`, `rrDate`, `rrdId`, `nmId`, `supplierArticle`, `retailAmount`, `retailPriceWithDiscRub`, `ppvzForPay`, `quantity`, `currency`, `rebillLogisticCost`, etc. (see Section 1)
- **Dates**: `saleDt` = operational sale date; `rrDate` = document/report date
- **Monetary**: `Decimal` expected; `retailAmount` and `ppvzForPay` are positive/negative based on raw sign; `rebillLogisticCost` must be non-negative (`expected_raw_sign=NON_NEGATIVE_RAW` per `marketplace_policy.py`) — verified in replay payload (no negative values shown; positive/zero present).
- **Source endpoint**: `FINANCE_DETAIL` (finance-api, POST `/api/finance/v1/sales-reports/detailed`).

---

## 3. FIELD COMPATIBILITY MATRIX (ACTUAL — FROM REAL FILES + CONTRACTS)

| V2 Canonical / Raw Field | Legacy stats-api (`raw_2026-04-01.json`) | Direct Mapping? | Evidence / Status |
|---|---|---|---|
| `nmId` | ABSENT (only `sku_id` in legacy `orders`) | NOT DIRECT | Legacy uses `sku_id`; V2 uses `nmId`; different namespace |
| `supplierArticle` | ABSENT | ABSENT | No vendor article in legacy payload |
| `saleDt` (operational) | `date` (`orders[].date`) — same concept, different name | MAPPING REQUIRED (`date` → `saleDt`) | Legacy `date` = `2026-03-31` matches operational date; `rrDate` missing |
| `rrDate` (document) | ABSENT (only `date`) | ABSENT / MAPPING REQUIRED | V2 distinguishes `saleDt` from `rrDate`; legacy has only one date |
| `rrdId` (source record) | `order_id` (not identical semantic: legacy `order_id` = `"1"`, V2 `rrdId` = document-level ID from finance API) | NOT DIRECT — `order_id` ≠ `rrdId` without adapter | Need mapping logic |
| `retailAmount` | `revenue` (`orders[].revenue`) — similar concept (gross realized) | SEMANTIC REVIEW REQUIRED | Legacy `revenue` = 1100.0; V2 `retailAmount` = 1100.0 equivalent (same numeric value in this case, but names and source endpoint differ) |
| `retailPriceWithDiscRub` | ABSENT | ABSENT | Legacy payload has no discounted retail price field separately |
| `ppvzForPay` (seller payout) | `seller_payout` (`orders[].seller_payout`) — 0.0 in payload | MAPPING REQUIRED (`seller_payout` → `ppvzForPay`) | Concept similar (amount to seller); value 0.0 here; not verified at scale |
| `quantity` | `quantity` (1) | DIRECT | Same name, same concept |
| `rebillLogisticCost` | `rebill_logistic_cost` (0.0) | DIRECT (name identical) | Present, numeric, sign positive/zero |
| `commission` / marketplace commission | `commission` (120.0 / 0.0) | MAPPING REQUIRED (`commission` → marketplace deduction component, but legacy `commission` is a single positive amount; V2 splits into `marketplace_commission`, `marketplace_deductions`, etc.) | |
| `deliveryPrice` / logistics | `logistics` (0.0) | MAPPING REQUIRED (`logistics` → `LOGISTICS` / `REVERSE_LOGISTICS`) | Legacy `logistics` is a single field; V2 requires classification per `RebillLogisticsClassification` |
| `penalty` | `penalties` (0.0) | DIRECT (name close; 0.0) | Present |
| `storage` / storage fee | `storage` (0.0) | DIRECT | Present |
| `acceptance` | ABSENT | ABSENT | No acceptance fee in legacy payload |
| `acquiringFee` / acquiring | `acquiring` (0.0) | DIRECT (name close; 0.0) | Present |
| `tax` / VAT | ABSENT | ABSENT | No separate tax field in legacy payload; tax embedded in `retailAmount` or missing |
| `advertising` | ABSENT (separate `ads` array exists, but not in `orders`) | ABSENT in finance rows | Advertising separate in V2 (`AdvertisingExpenseInput`); legacy captures ads separately (`ads` array) |
| `return` / return revenue | `returns` array (separate from `orders`) with `revenue_lost` | SEMANTIC REVIEW REQUIRED — `returns` is separate section, not within finance row | |

---

## 4. SIGN SEMANTICS (REAL PAYLOAD + CONTRACT)

**Legacy payload** (`raw_2026-04-01.json`):
- `revenue`: 1100.0 (positive — realized gross revenue)
- `commission`: 120.0 (positive — marketplace fee deducted?) / 0.0
- `rebill_logistic_cost`: 0.0 (positive/zero; `marketplace_policy.py` requires `expected_raw_sign=NON_NEGATIVE_RAW` for `rebillLogisticCost` — consistent)
- `penalties`: 0.0
- `deductions`: 0.0
- `logistics`: 0.0
- `acquiring`: 0.0
- `seller_payout`: 0.0
- `gross_revenue`: 1100.0 (positive)
- `realized_revenue`: 1100.0 (positive)
- `revenue_lost` (returns): 1100.0 (positive — but as return/deduction it should be negative or zero in canonical, per `RebillLogisticsInput` and `FinancialComponentStatus` rules: `deduction ... must not be positive` / `return_revenue_adjustment` must be negative or zero)
- **No negative values shown in this specific payload** — but `marketplace_policy.py` and `packages/finance/` explicitly anticipate signed amounts (`NEGATIVE_CANONICAL`, `NON_NEGATIVE_RAW`) and guard against `abs()`. 

**Critical for compatibility:** V2 `FINANCE_DETAIL` (replay bundle) also uses raw signed amounts (no `abs()` in target path, confirmed in Stage 9 audit). To combine legacy `statistics-api` with V2, adapter must interpret legacy positive `commission`/`rebill_logistic_cost`/`penalties` as negative canonical deductions, and legacy positive `revenue` as positive `REALIZED_GROSS`.

---

## 5. REBILL LOGISTICS COST CHECK

`rebillLogisticCost` — present as `rebill_logistic_cost` in legacy payload (`0.0`). In V2 contract: `RebillLogisticsInput` (`packages/finance/contracts.py`) requires `classification` (`LOGISTICS` vs `REVERSE_LOGISTICS`) and `amount` (negative for expense, per `require_negative_expense_amount`). Legacy field is just a number without classification.

**Status**: PRESENT IN LEGACY SOURCE (field exists; value 0.0 here; structure allows non-zero). If future legacy payload contains non-zero `rebill_logistic_cost`, adapter must classify and apply negative sign per `RebillLogisticsClassification`. **Not blocked by absence of field**.

---

## 6. DATE SEMANTICS

- **Legacy payload** `date` (`2026-03-31`) = transaction/report date in legacy v5 bundle. **No separate `saleDt`/`rrDate`**; no `operational_date` embedded in row.
- **V2 `FINANCE_DETAIL`**: `saleDt` (operational sale date) and `rrDate` (document/report date) — both present in replay payload (confirmed by inspection).
- **Legacy `load_finance_final_single_attempt()`** uses `target_date` (e.g., `2026-04-01`) as `dateFrom`/`dateTo`; payload `date` may be `target_date` or `target_date-1` depending on lag (evidence: `api_debug.json`: `operational_day=2026-04-01`, `finance_date_used=2026-03-31`, `finance_lag_days=1`). This is important: legacy finance endpoint may return rows that are 1 day behind the requested period, or may return rows for the requested date with different semantics — the payload doesn't guarantee `date == operational_date`.

**Not proven deterministically from payload alone**: if V2 requests `operational_date=2026-08-27`, legacy statistics endpoint may return `date=2026-08-26` (lag) or `date=2026-08-27`. **NOT PROVEN** — must be verified at adapter level with actual response mapping.

---

## 6. NORMALIZATION COMPATIBILITY

- V2 `packages/data/normalization.py`: `FINANCE_DETAIL_CHARGE_FIELDS`, `FINANCE_DETAIL_FIELD_MAPPING`, `normalize_finance_detail()` expect `FINANCE_DETAIL` endpoint (ARRAY of rows with V2 names).
- Legacy `statistics-api` / `reportDetailByPeriod` payload has **different top-level structure** (dict with nested sections) and **different row structures** (`orders[]` with `order_id`, `revenue`, `commission`, etc., not `nmId`/`rrdId` with `retailAmount`).
- `normalize_finance_detail()` cannot directly consume `raw_2026-04-01.json` without adapter because:
  - Top-level not array.
  - `nmId` absent; `sku_id` present instead.
  - `saleDt` absent; `date` present.
  - `rrdId` absent; `order_id` present.
  - `retailAmount` absent; `revenue` present.
  - `packages/finance/kernel.py` and market sign policy (`marketplace_policy.py`) expect `FINANCE_DETAIL` canonical format — adapter must produce it.

**Conclusion**: NORMALIZATION COMPATIBILITY = ADAPTER_REQUIRED (not SAFE, not BLOCKED — data exists, fields partially overlap, mapping is explicit and deterministic).

---

## 7. EXTRACTION / DUPLICATE / PAGINATION CHECK

- Legacy `load_finance_final_single_attempt()` uses `limit=100000`; payload from `raw_2026-04-01.json` has 2 orders, so far below limit — no pagination evidence needed.
- `_extract_realization_rows()` in `loaders.py` handles both `list` and `dict` payload (with `data`, `items`, `rows`, `details` extraction). Risk of double extraction exists if both `rows` and `data[]` present — for this payload, only `orders` array exists (no nested `data` inside `orders`), so **no duplicate risk**.
- No evidence of truncation; no pagination fields in payload.
- **Status**: NOT BLOCKED (no pagination needed for 2 rows; scale unknown but adapter can paginate if needed).

---

## 7. FINAL VERDICT

```text
ADAPTER_REQUIRED
```

**Reason**: Legacy statistics-api raw (`reportDetailByPeriod` / `v5` compatibility bundle) exists locally and contains real financial data with fields that partially overlap V2 `FINANCE_DETAIL` (revenue, quantity, date, rebill logistics, penalties, commissions, logistics, storage, acquiring). However, **structural and semantic differences are too significant for direct pipeline ingestion**:

- **Structure**: Legacy = composite dictionary (`orders`/`margins`/`returns`/`ratings`/`ads`); V2 = flat array of financial rows.
- **Field names**: `revenue` vs `retailAmount`; `date` vs `saleDt`/`rrDate`; `sku_id` vs `nmId`; `order_id` vs `rrdId`; `seller_payout` vs `ppvzForPay`.
- **Dates**: legacy uses single `date` (lag-1 possible); V2 distinguishes `saleDt`/`rrDate`.
- **Sign interpretation**: legacy stores fees as positive numbers (commission, penalties, rebill) — adapter must assign negative canonical sign per `FinancialComponentStatus` rules (`revenue` positive, `marketplace_commission` negative, `rebill_logistics` negative).
- **Missing V2 fields**: `supplierArticle`, `vendorCode`, `retailPriceWithDiscRub`, `tax` (separate), `advertising` (separate array) — adapter must source from other endpoints or mark `NOT_PROVIDED`.

**Adapter contract** (described, not implemented — per §10 instruction):

```text
Legacy statistics-api row (from orders[] / or aggregated):
  source_field         → target V2 canonical / raw
  revenue              → retailAmount / realized_gross (with sign: positive)
  commission           → marketplace_commission (negative, via adapter sign assignment)
  logistics            → logistics / reverse_logistics (classification required)
  storage              → storage (positive/zero)
  penalties            → penalties (negative/zero)
  acquiring            → acquiring (positive/zero)
  rebill_logistic_cost → rebillLogistics (negative per RebillLogisticsClassification)
  date                 → saleDt (if operational) / rrDate (if document)
  quantity             → quantity (direct)
  sku_id               → nmId (mapping; adapter must resolve sku→nmId or mark unresolved)
  order_id             → rrdId (mapping; adapter must resolve or mark unresolved if not 1:1)
  seller_payout        → ppvzForPay (positive/zero; may include commissions deducted)
```

---

## 7. FINAL VERDICT

```text
ADAPTER_REQUIRED
```

**Reason**: Legacy statistics-api raw (`reportDetailByPeriod` / `v5` compatibility bundle) exists locally and contains real financial data with fields that partially overlap V2 `FINANCE_DETAIL` (revenue, quantity, date, rebill logistics, penalties, commissions, logistics, storage, acquiring). However, **structural and semantic differences are too significant for direct pipeline ingestion**:

- **Structure**: Legacy = composite dictionary (`orders`/`margins`/`returns`/`ratings`/`ads`); V2 = flat array of financial rows.
- **Field names**: `revenue` vs `retailAmount`; `date` vs `saleDt`/`rrDate`; `sku_id` vs `nmId`; `order_id` vs `rrdId`; `seller_payout` vs `ppvzForPay`.
- **Dates**: legacy uses single `date` (lag-1 possible); V2 distinguishes `saleDt`/`rrDate`.
- **Sign interpretation**: legacy stores fees as positive numbers (commission, penalties, rebill) — adapter must assign negative canonical sign per `FinancialComponentStatus` rules (`revenue` positive, `marketplace_commission` negative, `rebill_logistics` negative).
- **Missing V2 fields**: `supplierArticle`, `vendorCode`, `retailPriceWithDiscRub`, `tax` (separate), `advertising` (separate array) — adapter must source from other endpoints or mark `NOT_PROVIDED`.

**Adapter contract** (described, not implemented — per §10 instruction):

```text
Legacy statistics-api row (from orders[] / or aggregated):
  source_field         → target V2 canonical / raw
  revenue              → retailAmount / realized_gross (with sign: positive)
  commission           → marketplace_commission (negative, via adapter sign assignment)
  logistics            → logistics / reverse_logistics (classification required)
  storage              → storage (positive/zero)
  penalties            → penalties (negative/zero)
  acquiring            → acquiring (positive/zero)
  rebill_logistic_cost → rebillLogistics (negative per RebillLogisticsClassification)
  date                 → saleDt (if operational) / rrDate (if document)
  quantity             → quantity (direct)
  sku_id               → nmId (mapping; adapter must resolve sku→nmId or mark unresolved)
  order_id             → rrdId (mapping; adapter must resolve or mark unresolved if not 1:1)
  seller_payout        → ppvzForPay (positive/zero; may include commissions deducted)
```

---