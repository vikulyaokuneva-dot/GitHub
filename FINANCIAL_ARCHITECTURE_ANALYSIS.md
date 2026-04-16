# v3 Financial Architecture Analysis

**Date**: April 16, 2026  
**Scope**: Complete financial layer of v3 project  
**Status**: Detailed architecture mapping

---

## Executive Summary

The v3 financial layer consists of:
- **Data Loading**: Multi-endpoint financial ingestion with primary/fallback strategy
- **Field Normalization**: Semantic field mapping to handle API schema variations
- **Aggregation**: Account-level and SKU-level financial metrics
- **Integration**: Financial data mixed with operational metrics (orders, sales, ads)
- **Reporting**: Financial snapshots stored in report_meta and used in facts/decisions

---

## 1. Financial Data Loading Architecture

### 1.1 Primary Financial API Endpoint

**File**: [v3/api/endpoints.py](v3/api/endpoints.py)

```python
FINANCE_SALES_REPORTS_DETAILED = WBEndpoint(
    name="finance_sales_reports_detailed",
    base=BASE_STATISTICS,
    path="/api/finance/v1/sales-reports/detailed",
)
```

- **Purpose**: Get detailed financial data by period
- **Primary Load Method**: `_load_realization_from_finance_detailed_period()` in [v3/ingestion/api_realization_loader.py](v3/ingestion/api_realization_loader.py)
- **Returns**: `api_debug` with `finance_api_mode: "new" | "new_by_report_id"`

### 1.2 Legacy Fallback Endpoint

**File**: [v3/ingestion/api_realization_loader.py](v3/ingestion/api_realization_loader.py) (line ~814)

```python
REALIZATION = WBEndpoint(
    name="realization", 
    base=BASE_STATISTICS, 
    path="/api/v5/supplier/reportDetailByPeriod"
)
```

**Fallback Condition**: (Line 793-802)
```python
def _should_fallback_to_legacy(primary_debug: Dict[str, Any]) -> bool:
    if not bool(primary_debug.get("success", False)):
        return True
    if bool(primary_debug.get("finance_payload_incompatible", False)):
        return True
    return False
```

**Fallback Result**: `api_debug` with `finance_api_mode: "legacy_fallback"`

### 1.3 Finance API Modes

| Mode | Source | When Used | Status |
|------|--------|-----------|--------|
| `new` | Finance API (detailed) | Primary success | Full financial data |
| `new_by_report_id` | Finance API (filtered) | Report ID available | Optimized query |
| `legacy_direct` | v5 reportDetailByPeriod | Direct legacy load | Fallback |
| `legacy_fallback` | v5 reportDetailByPeriod | Primary failed | Error recovery |

**Tracking**: [v3/pipeline/daily_input_stage.py](v3/pipeline/daily_input_stage.py) line 522

---

## 2. Financial Field Normalization

### 2.1 Field Alias System

**File**: [v3/metrics/financial_models.py](v3/metrics/financial_models.py#L6-L82)

Maps multiple API field names to semantic financial groups:

```python
FINANCIAL_ROW_FIELD_ALIASES = {
    "wb_commission": (
        "ppvz_sales_commission",
        "ppvzSalesCommission",
        "commission_amount",
        "commissionAmount",
        "wb_reward_before_agent",
    ),
    "logistics": (
        "delivery_rub",
        "deliveryRub",
        "logistics",
        "logistics_cost",
        "rebill_logistic_cost",
    ),
    "storage": (
        "storage_fee",
        "storageFee",
        "storage",
    ),
    "penalties": (
        "penalty",
        "penaltyAmount",
        "fine",
    ),
    "payout": (
        "ppvz_for_pay",
        "ppvzForPay",
        "to_pay",
        "toPay",
    ),
    # ... more fields
}
```

### 2.2 Field Extraction Methods

**File**: [v3/wb_client.py](v3/wb_client.py)

```python
def _pick_first_float(row: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    """Try each key in order, return first non-null numeric value"""
    for key in keys:
        value = cls._as_float(row.get(key))
        if value is not None:
            return value
    return default

def _pick_optional_float(row: Dict[str, Any], keys: Iterable[str]) -> float | None:
    """Same as above but returns None if all keys missing"""
    for key in keys:
        value = cls._as_float(row.get(key))
        if value is not None:
            return value
    return None
```

### 2.3 Sales Data Normalization

**File**: [v3/ingestion/api_sales_loader.py](v3/ingestion/api_sales_loader.py#L128-L156)

Realization rows contain rich financial data. Sales API rows (orders/sales) contain **only commerce data**:

```python
# Sales API fields - NO financial deductions
item = {
    "revenue": round(revenue, 2),
    "profit": round(revenue, 2),  # Provisional = revenue (no costs)
    "cost_price": 0.0,
    "wb_commission": 0.0,
    "logistics": 0.0,
    "penalties": 0.0,
    "storage": 0.0,
    "deductions": 0.0,
    "_source_dataset": "sales_api",
}
```

**⚠️ Critical**: Sales API rows are **not** used as financial contour when realization rows available.

---

## 3. Financial Data Validation

### 3.1 Data Integrity Checks

**File**: [v3/validation/data_integrity.py](v3/validation/data_integrity.py)

**FINANCIAL_COMPONENT_KEYS** (tracked for completeness):
```python
FINANCIAL_COMPONENT_KEYS = (
    "revenue",
    "commission",      # wb_commission
    "logistics",
    "storage",
    "penalties",
    "deductions",
    "cost_price",
    "tax",
    "ads_spend",
)
```

**Function**: `evaluate_financial_integrity()`
- Input: sales rows, data sources metadata
- Output: 
  - `financial_completeness_pct` (0-100%)
  - `financial_finality_status` ("final" | "partial" | "sparse" | "unavailable")
  - Component summaries (commission, deductions totals)

**Finality Status Determination** (line 156-175):
```
final       = all 9 components present
partial     = 5-8 components present
sparse      = 1-4 components present
unavailable = 0 components present
```

### 3.2 SKU Attribution Validation

**File**: [v3/validation/data_integrity.py](v3/validation/data_integrity.py#L44-L100)

Identifies unassigned financial rows (rows with financial data but no SKU):

```python
def _is_true_unassigned_financial_row(row: Mapping[str, Any]) -> bool:
    """Row with costs but zero revenue = true unassigned"""
    revenue = abs(_safe_float(row.get("revenue")))
    cost_items = (cost_price + wb_commission + logistics + storage + 
                  penalties + deductions + ads_spend)
    return revenue <= 1e-9 and cost_items > 1e-9
```

---

## 4. Financial Metrics Aggregation

### 4.1 Daily Financial KPI Assembly

**File**: [v3/pipeline/daily_metrics_stage.py](v3/pipeline/daily_metrics_stage.py)

**Main Function**: `build_daily_financial_kpi()` (line ~230)

**Inputs**:
- `account_totals` from financial kernel (totals dict with gross revenue, commissions, logistics, etc.)
- `daily_kpi` (operational metrics)
- `daily_metrics` (sku-level metrics)

**Outputs**: `FinancialKpiContract` with:

```python
@dataclass
class FinancialKpiContract:
    date: str
    revenue: float | None
    cost_price: float | None
    wb_commission: float | None
    logistics: float | None
    storage: float | None
    penalties: float | None
    deductions: float | None
    ads_spend: float | None
    gross_profit: float | None
    net_profit: float | None
    margin_pct: float | None
    profitability_pct: float | None
    completeness_pct: float
    is_partial: bool
    confirmed: bool
```

### 4.2 Profit Calculation Formulas

**Location**: [v3/wb_client.py](v3/wb_client.py#L299-L302) and [v3/pipeline/daily_metrics_stage.py](v3/pipeline/daily_metrics_stage.py#L249-L296)

```python
# Base profit formula
profit = revenue - cost_price - wb_commission - logistics - penalties - storage - deductions

# Or explicit profit field if available
explicit_profit = row.get("profit") or row.get("netProfit") or row.get("income")
```

**Margin Calculations** (daily_metrics_stage.py):

```python
# Margin = (profit / revenue) * 100
margin = (net_profit / seller_payout) * 100.0 if seller_payout > 0 else None

# Profitability = (profit / cost_price) * 100
profitability_pct = (net_profit / cost_price) * 100.0 if cost_price > 0 else None
```

### 4.3 Financial Kernel

**File**: [v3/metrics/financial_kernel.py](v3/metrics/financial_kernel.py)

**Input Contract**:
```python
@dataclass
class FinancialKernelInput:
    realization_rows: List[Dict[str, Any]]
    tax_rate: float = 0.06
    cogs_rows: List[Dict[str, Any]] | None = None
    cogs_file_found: bool | None = None
    source_meta: Dict[str, Any] = field(default_factory=dict)
```

**Output Contract**:
```python
@dataclass
class FinancialKernelOutput:
    account_financial_totals: AccountFinancialTotals
    sku_financials: Dict[int, SKUFinancialRow]
    commission_breakdown: CommissionBreakdown
    cogs_diagnostics: Dict[str, Any]
    warnings: List[Dict[str, Any]]
    source_meta: Dict[str, Any]
    kernel_status: str  # "skeleton" | "loaded" | "computed"
```

**SKU-Level Financials**:
```python
@dataclass
class SKUFinancialRow:
    sales_qty: int
    returns_qty: int
    sales_revenue: float
    returns_revenue_est: float
    net_revenue: float
    commission: float
    logistics: float
    storage: float
    penalties: float
    payout: float
    tax_alloc: float
    cogs: float
    profit: float
    margin: float
```

---

## 5. Financial + Operational Data Integration

### 5.1 Data Loading Pipeline

**File**: [v3/pipeline/daily_input_stage.py](v3/pipeline/daily_input_stage.py)

**Sequence**:

```
1. Load Realization Rows (Financial)
   └─ Try Finance API (/api/finance/v1/sales-reports/detailed)
   └─ Fallback: Legacy endpoint (/api/v5/supplier/reportDetailByPeriod)

2. Load Operational Data (Commerce)
   ├─ Orders API (/api/v1/supplier/orders)
   ├─ Sales API (/api/v1/supplier/sales)
   └─ Stocks API (/api/v1/supplier/stocks)

3. Load Ads Data
   └─ Ads API (legacy advert-api)

4. Mixing Strategy:
   - SALES (financial) rows = api_realization_rows (preferred)
   - If realization empty && local report exists → Use local financial report
   - ORDERS/STOCKS/ADS rows = use as-is for commerce/funnel metrics
```

### 5.2 Data Structure After Loading

**File**: [v3/raw/models.py](v3/raw/models.py#L6-L23)

```python
@dataclass
class RawIngestionBundle:
    source_mode: str  # "wb_api" | "local_reports_fallback"
    
    # Operational data
    api_orders_rows: List[Dict]
    api_sales_rows: List[Dict]
    api_stocks_rows: List[Dict]
    
    # Financial data (combined from primary/fallback)
    api_realization_rows: List[Dict]  # Primary financial source
    
    # Ads data
    api_ads_rows: List[Dict]
    
    # Debug metadata
    api_debug: Dict[str, Any]
    input_debug: Dict[str, Any]
```

### 5.3 Daily Metrics Assembly

**File**: [v3/pipeline/daily_metrics_stage.py](v3/pipeline/daily_metrics_stage.py#L200-L400)

**Mixes**:
- Financial KPI (from realization rows via financial kernel)
- Order KPI (orders count, amount)
- Buyout KPI (sales/buyouts count, amount)
- Ads Summary (ads rows attribution)
- SKU Metrics (aggregated by SKU from all sources)

**Result**: `daily_metrics` dict with:
```python
{
    "financial_kpi": {...},        # Profit, margin, commission
    "order_kpi": {...},            # Orders count/amount
    "buyout_kpi": {...},           # Buyouts count/amount
    "ads_summary": {...},          # Ads rows, CTR, CPC
    "sku_metrics": [               # Per-SKU aggregation
        {
            "sku": "...",
            "revenue": ...,
            "profit": ...,
            "orders_count": ...,
            "ads_spend": ...,
            # ...
        }
    ],
    "financial_debug": {...}       # Diagnostics
}
```

---

## 6. Financial Snapshots in Facts/Metrics/Report Meta

### 6.1 Financial KPI Contract in Report Meta

**File**: [v3/domain/event_model.py](v3/domain/event_model.py#L159-L195)

**Function**: `build_financial_kpi_contract()`

Input sources:
- `financial_kpi` dict (from daily_metrics_stage)
- `data_sources` (metadata about where each field came from)
- `event_date_model` (dates and timezone)

Output stored in `report_meta["financial_kpi"]`:

```python
{
    "date": "2026-04-16",
    "revenue": 12500.00,
    "cost_price": 5000.00,
    "wb_commission": 1500.00,
    "logistics": 800.00,
    "storage": 300.00,
    "penalties": 100.00,
    "deductions": 50.00,
    "ads_spend": 400.00,
    "gross_profit": 12500 - 1500 = 11000.00,
    "net_profit": 11000 - 5000 - 800 - 300 - 100 - 50 - 400 = 4350.00,
    "margin_pct": (4350 / 12500) * 100 = 34.8%,
    "profitability_pct": (4350 / 5000) * 100 = 87.0%,
    "completeness_pct": 100.0,
    "is_partial": false,
    "confirmed": true,
    "financial_date_aligned": true,
    "financial_alignment_status": "aligned",
}
```

### 6.2 Profit Contribution Analysis

**File**: [v3/analytics/profit_contribution.py](v3/analytics/profit_contribution.py)

**Function**: `build_profit_contribution(metrics: Dict)` (line 129)

**Input**: SKU metrics with profit field

**Output**: Profit contribution analysis
```python
{
    "sku_metrics": [
        {
            "sku": "123456",
            "profit": 1500.00,
            "profit_group": "P1",        # P1-P4 groups
            "profit_rank": 1,
            "profit_share": 0.345,       # Share of total profit
            "cumulative_profit_share": 0.345,
            "class": "P1"
        }
    ],
    "top_profit_skus": [...5 items],
    "top_loss_skus": [...5 items],
    "profit_concentration_label": "high" | "medium" | "low",
    "top_20_profit_share": 0.67,
}
```

### 6.3 Profit Delta in Memory

**File**: [v3/memory/decision_outcomes.py](v3/memory/decision_outcomes.py#L88-L235)

Tracks profit changes between decision outcomes:

```python
deltas = {
    "profit_delta": curr_profit - base_profit,          # Absolute change
    "profit_delta_pct": (profit change / base) * 100,   # % change
    "margin_pct_delta": ...,
    "buys_delta": ...,
    "ads_spend_delta": ...,
}
```

---

## 7. Current Problems and Gaps

### 7.1 Partial Financial Status

**When**: `financial_finality_status = "partial"`
**Cause**: Some financial components missing (e.g., cost_price, deductions)
**Impact**: 
- Profit calculation incomplete/inaccurate
- `margin_pct` and `profitability_pct` may be None
- Report guardrails disable profit-based commentary

**Location**: [v3/validation/report_guardrails.py](v3/validation/report_guardrails.py#L62-L132)

### 7.2 Legacy Fallback Usage

**When**: Primary Finance API returns no data or incompatible payload
**Fallback**: Switch to `/api/v5/supplier/reportDetailByPeriod`
**Issues**:
- Field mapping may differ
- Schema compatibility uncertain
- Diagnostics tracked but not always visible

**Location**: [v3/ingestion/api_realization_loader.py](v3/ingestion/api_realization_loader.py#L793-L835)

### 7.3 Financial Lag

**Config**: `WB_MAX_FINANCE_LAG_DAYS` (default: 3 days)
**Problem**: Finance data may lag behind operational data
**Result**: `financial_alignment_status = "lagged_fallback"`

**Location**: [v3/pipeline/daily_input_stage.py](v3/pipeline/daily_input_stage.py#L448-L456)

### 7.4 COGS Integration

**Status**: Financial kernel supports COGS but uses fallback if COGS rows missing
**Location**: [v3/metrics/financial_kernel.py](v3/metrics/financial_kernel.py)
**Issue**: COGS file detection not always reliable

### 7.5 Deductions Field

**Situation**: `deductions` field may not be present in all API responses
**Fallback**: Assumes 0.0 if missing
**Impact**: Profit underestimated if deductions actually exist

**Location**: [v3/wb_client.py](v3/wb_client.py#L282-L287)

---

## 8. Current Data Contract Summary

### 8.1 Financial Row Structure

**Minimal Required Fields**:
```python
{
    "nmId": 123456,                    # SKU identifier
    "quantity": 5,                     # Units sold
    "retailPriceWithDiscRub": 2000.00, # Revenue per unit
    "ppvzSalesCommission": 300.00,     # WB commission
    "deliveryRub": 150.00,             # Logistics
    "storageFee": 50.00,               # Storage
    "penaltyAmount": 20.00,            # Penalties
    "ppvzForPay": 1480.00,             # Payout (revenue - commission)
}
```

**Optional Fields** (enable fuller calculations):
```python
{
    "costPrice": 800.00,               # Cost of goods
    "deduction": 30.00,                # Payment processor fees
    "profit": 500.00,                  # Explicit profit (overrides formula)
    "tax": 0.00,                       # VAT/tax
}
```

### 8.2 Financial KPI Contract

**Required for "confirmed" status**:
- Data source known (not "unknown")
- is_partial = false
- completeness_pct >= 99.99
- financial_date_aligned = true

**When confirmed = true**:
- margin_pct and profitability_pct are populated
- profit-based decisions enabled
- Report shows "Final financial data"

---

## 9. File Reference Map

### Core Loading
- [v3/ingestion/api_realization_loader.py](v3/ingestion/api_realization_loader.py) - Primary financial load with fallback logic
- [v3/ingestion/api_sales_loader.py](v3/ingestion/api_sales_loader.py) - Sales API (commerce-only)
- [v3/ingestion/api_orders_loader.py](v3/ingestion/api_orders_loader.py) - Orders API (commerce-only)

### Normalization & Validation
- [v3/wb_client.py](v3/wb_client.py) - Field extraction and profit calculation
- [v3/validation/data_integrity.py](v3/validation/data_integrity.py) - Financial completeness checks
- [v3/validation/sku_normalization.py](v3/validation/sku_normalization.py) - SKU mapping

### Metrics & Aggregation
- [v3/metrics/financial_kernel.py](v3/metrics/financial_kernel.py) - Account/SKU profit kernel
- [v3/metrics/financial_models.py](v3/metrics/financial_models.py) - Data structures and contracts
- [v3/pipeline/daily_metrics_stage.py](v3/pipeline/daily_metrics_stage.py) - Financial KPI assembly

### Analysis & Reporting
- [v3/analytics/profit_contribution.py](v3/analytics/profit_contribution.py) - Profit by SKU analysis
- [v3/domain/event_model.py](v3/domain/event_model.py) - Financial KPI contract builder
- [v3/validation/report_guardrails.py](v3/validation/report_guardrails.py) - Financial status constraints

### Orchestration
- [v3/pipeline/daily_input_stage.py](v3/pipeline/daily_input_stage.py) - Data loading coordination
- [v3/pipeline/daily_pipeline_runner.py](v3/pipeline/daily_pipeline_runner.py) - Pipeline execution

---

## 10. API Endpoints Reference

| Endpoint | Purpose | Type | Status |
|----------|---------|------|--------|
| `/api/finance/v1/sales-reports/detailed` | Primary financial data | Primary | Preferred |
| `/api/finance/v1/sales-reports/list` | Report list/metadata | Auxiliary | Meta only |
| `/api/v5/supplier/reportDetailByPeriod` | Legacy financial data | Fallback | For compatibility |
| `/api/v1/supplier/orders` | Orders (operational) | Commerce | Not financial |
| `/api/v1/supplier/sales` | Sales (operational) | Commerce | Not financial |
| `/api/v1/supplier/stocks` | Inventory | Inventory | Not financial |

---

## Notes & Observations

1. **Dual Financial Contours**: v3 supports both API-based and local report-based financial data
2. **Field Flexibility**: Schema allows multiple alias names for each financial component
3. **Graceful Degradation**: Missing fields default to 0.0 rather than erroring
4. **Status Tracking**: Financial data finality and completeness explicitly tracked
5. **Profit Primacy**: All analysis ultimately derived from profit/margin calculations
6. **SKU Attribution**: Critical for associating costs to products (impacts profit allocation)

---

**End of Analysis**
