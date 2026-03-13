# Territorial Distribution Engine

This engine provides SKU-level territorial distribution analytics for daily management decisions.

## What it measures

- `localization_share` = `local_orders / total_orders * 100`
- distribution coefficients (`KTR`, `KRP`) based on WB localization intervals
- analytical IRP exposure estimate:
  - `irp_penalty_per_order = average_retail_price * krp`
  - `estimated_irp_penalty_total = total_orders * average_retail_price * krp`

## Important modeling note

`estimated_irp_penalty_total` is an analytical management estimate.
It is not intended to reconstruct exact WB account-level IRP billing.

## Effective date gating

IRP impact is applied only when `report_date >= wb_irp_effective_date` (default `2026-03-23`).
Before this date, penalty impact is forced to zero while localization/KTR/KRP are still computed for preview.

## Fallbacks

Price fallback order:
1. explicit retail price before WB discount fields (if present)
2. `revenue / total_orders`
3. snapshot price fields
4. otherwise price is missing and money impact remains zero/none with diagnostics

## Future extension

Reverse logistics (volume/liters based) is intentionally left as deferred extension.
The engine keeps a dedicated metadata block for future integration without interface breaks.