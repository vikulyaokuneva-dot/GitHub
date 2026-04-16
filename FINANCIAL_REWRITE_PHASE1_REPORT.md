# Financial Layer Rewrite - PHASE 1 Completion Report

## Overview

This document summarizes **PHASE 1: ISOLATION AND NEW INTERNAL FINANCIAL CONTRACT** completion and provides roadmap for PHASE 2 and PHASE 3.

---

## PHASE 1: COMPLETED ✅

### Artifacts Created

| Component | File | Purpose |
|-----------|------|---------|
| **FinancialSnapshot Contract** | `v3/domain/financial_snapshot.py` | Core contract defining financial data semantics, status, alignment, completeness |
| **Snapshot Builder** | `v3/financial/snapshot_builder.py` | Converts kernel financial_kpi → FinancialSnapshot |
| **Pipeline Integration** | `v3/pipeline/daily_metrics_stage.py` | Creates snapshot in pipeline after kernel run |
| **Event Model Extension** | `v3/domain/event_model.py` | New function `build_financial_kpi_from_snapshot()` |
| **Tests** | `v3/tests/test_financial_snapshot_phase1.py` | Basic snapshot contract and builder tests |

### Key Accomplishments

1. **Isolated Financial Semantics**
   - Separated operational KPI (orders/buyouts) from financial data
   - Created explicit status tracking (FULL | LAGGED | PARTIAL | MISSING)
   - Enforced date alignment semantics

2. **New Internal Contract**
   ```python
   FinancialSnapshot:
     - target_date: str
     - actual_date: str
     - status: FinancialStatus
     - source: DataSource
     - components: FinancialComponents (14 fields)
     - component_status: ComponentStatus (14 bool flags)
     - alignment: FinancialAlignment (date semantics)
     - completeness_pct: float
     - diagnostics: FinancialDiagnostics
   ```

3. **Data Flow Integration**
   ```
   financial_kpi (from kernel) 
   → build_financial_snapshot_from_kernel()
   → FinancialSnapshot (isolated contract)
   → downstream (facts/metrics/report_meta)
   ```

4. **Backward Compatibility**
   - Old `financial_kpi` still exists (for gradual migration)
   - New snapshot available alongside legacy data
   - No breaking changes to downstream yet

---

## PHASE 2: UNIFIED LOADER + NORMALIZER (Not Started)

### Tasks

#### 2.1 Create New Finance Loader Layer
**File**: `v3/financial/finance_loader.py`

```python
class FinanceLoader:
    """
    Unified loader for both new and legacy finance API.
    """
    def load(self, target_date: str) -> FinancialLoadResult:
        """
        Try new API first, fallback to legacy if needed.
        Returns normalized raw result contract.
        """
        # 1. Try new: /api/finance/v1/sales-reports/detailed
        # 2. Fallback: /api/v5/supplier/reportDetailByPeriod
        # 3. Mark which was used
        # 4. Return unified RawFinancialResult
```

**Responsibilities**:
- Attempt new finance API endpoint
- Fall back to legacy with diagnostics
- Return unified result type
- Track errors, timeouts, incompatibilities
- No transformation (raw load only)

#### 2.2 Create Normalizer Layer
**File**: `v3/financial/finance_normalizer.py`

```python
class FinanceNormalizer:
    """
    Normalize raw API responses to unified financial rows.
    """
    def normalize_new_api(rows: List[Dict]) -> List[FinancialRow]:
        """New API response → FinancialRow list"""
        
    def normalize_legacy_api(rows: List[Dict]) -> List[FinancialRow]:
        """Legacy API response → FinancialRow list (same format)"""
```

**Handles**:
- Field alias mapping (15+ field variants)
- Safe money parsing (Decimal → float)
- Validation and error tracking
- Component status calculation per row

#### 2.3 Update Snapshot Builder
**File**: `v3/financial/snapshot_builder.py` (enhancement)

Add method:
```python
def load_from_api_result(
    self, 
    raw_result: FinancialLoadResult,
    normalized_rows: List[FinancialRow]
) -> FinancialSnapshot:
    """Build snapshot from loaded and normalized API data"""
```

---

## PHASE 3: DOWNSTREAM RECONNECTION (Not Started)

### Tasks

#### 3.1 Update Facts Layer
**File**: `v3/analytics/daily_facts.py`

Change:
```python
# OLD: Read scattered financial data from financial_kpi
financial_status = financial_kpi.get("financial_status")
net_profit = financial_kpi.get("net_profit")

# NEW: Read from FinancialSnapshot
financial_status = financial_snapshot.status.value
net_profit = financial_snapshot.components.net_profit
```

#### 3.2 Update Metrics Layer
**File**: `v3/metrics/report_metrics.py`

- Use `snapshot.component_status` instead of manual checks
- Use `snapshot.completeness_pct` for data quality
- Use `snapshot.diagnostics` for source tracking

#### 3.3 Update Report/PDF Layer
**File**: `v3/report/pdf_report.py`

- Remove financial_date_misaligned cosmetics
- Use `snapshot.alignment.reason` directly
- Show warning when `snapshot.is_lagged()`
- Don't hide `snapshot.status == PARTIAL`

#### 3.4 Remove Legacy Assembly
**Files affected**:
- `v3/pipeline/daily_metrics_stage.py` - remove old fallback logic
- `v3/metrics/financial_kernel.py` - no changes (stays as is)
- Remove scattered `financial_date_aligned` checks

---

## Operational Changes After Phases 2-3

### Before (Current - PHASE 1 state)
```
Orders/Buyouts (operational) ━┓
                              ┃
Financial kernel ━━━━━━━━━━━━╋→ financial_kpi dict ━→ downstream
                              ┃
Old fallback logic ━━━━━━━━━━┛
```

### After (PHASE 2-3 state)
```
Orders/Buyouts (operational) ━━━━━━━━━━→ independent metrics

Finance API (new) ━┓
                   ┃→ FinanceLoader ━→ FinanceNormalizer ━→ normalized rows ┓
Finance API (legacy) ━┛                                                       ┃
                                                                             ┃
                                                              FinancialSnapshot ━→ downstream
                                                                             ┃
                                                            Financial kernel ━┛
```

---

## Testing Strategy

### PHASE 1 Tests (Implemented)
- [x] `test_aligned_snapshot` - dates match
- [x] `test_lagged_snapshot` - dates differ
- [x] `test_partial_snapshot` - incomplete components
- [x] `test_missing_snapshot` - no data
- [x] `test_snapshot_serialization` - to_dict works
- [x] `test_build_from_financial_kpi` - kernel conversion
- [x] `test_build_with_lagged_data` - lagged case
- [x] `test_build_missing_data` - missing case

### PHASE 2-3 Tests (TODO)
1. **Finance Loader Tests**
   - [ ] new API success path
   - [ ] new API failure → legacy fallback
   - [ ] both APIs fail → missing
   - [ ] timeout handling
   - [ ] incompatible payload detection

2. **Normalizer Tests**
   - [ ] new API field mapping
   - [ ] legacy API field mapping
   - [ ] safe decimal parsing
   - [ ] missing required fields
   - [ ] unmapped fields tracking

3. **Downstream Integration Tests**
   - [ ] Facts layer reads snapshot
   - [ ] Metrics layer uses completeness
   - [ ] Report detects lagged without cosmetics
   - [ ] PDF shows warnings for partial/missing

4. **Full Pipeline Tests**
   - [ ] new API end-to-end
   - [ ] legacy API end-to-end
   - [ ] fallback scenario
   - [ ] completeness preserved through layers

---

## Data Completeness Guarantees

### PHASE 1
- ✅ Snapshot available alongside legacy financial_kpi
- ✅ status/alignment/completeness explicitly tracked
- ⚠️  Legacy financial_kpi still used by downstream

### PHASE 2
- ✅ Unified loader consolidates API access
- ✅ Normalizer ensures schema consistency
- ⚠️  Still depends on kernel as primary source

### PHASE 3
- ✅ Downstream exclusively reads from snapshot
- ✅ No hidden fallbacks or cosmetics
- ✅ Single source of truth established

---

## Risk Mitigation

### Risk 1: API Endpoint Changes
- **Mitigation**: Normalizer abstracts field mapping
- **Fallback**: Legacy endpoint always available
- **Detection**: Load diagnostics track incompatibilities

### Risk 2: Date Misalignment Not Visible
- **Mitigation**: Explicit alignment_status in snapshot
- **Fallback**: Report layer checks snapshot.is_aligned()
- **Detection**: Tests verify lagged scenarios

### Risk 3: Data Quality Degradation
- **Mitigation**: component_status tracks per-field availability
- **Fallback**: completeness_pct shows overall coverage
- **Detection**: Partial/missing statuses explicit

---

## Next Steps (PHASE 2-3)

1. **Review PHASE 1 contracts** with team
2. **Design Finance Loader** + error handling strategy
3. **Implement Normalizer** with comprehensive field mapping
4. **Add loader tests** before touching downstream
5. **Gradually reconnect downstream** layer by layer
6. **Deprecate old assembly logic** after verification

---

## PHASE 1 Summary

**Status**: ✅ COMPLETE

**What Changed**:
- Added `v3/domain/financial_snapshot.py` (500+ lines)
- Added `v3/financial/snapshot_builder.py` (200+ lines)
- Updated `v3/domain/event_model.py` (50+ lines)
- Updated `v3/pipeline/daily_metrics_stage.py` (integration points)
- Added `v3/tests/test_financial_snapshot_phase1.py` (tests)

**What Did NOT Change**:
- Orders/Buyouts logic - untouched
- Funnel/Territorial/Recommendations - untouched
- Kernel financial calculations - untouched
- Report PDF generation - untouched (will update in PHASE 3)

**Quality Metrics**:
- ✅ No breaking changes
- ✅ Backward compatible
- ✅ All new contracts explicit and testable
- ✅ Isolated financial semantics
- ✅ Source of truth prepared for PHASE 2-3
