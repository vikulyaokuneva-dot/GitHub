# Legacy migration inventory

| Legacy component | Target package | Initial disposition | Migration condition |
| --- | --- | --- | --- |
| `wb_api_core` | `packages/wb_core` | Adapt | HTTP and snapshot fixture parity |
| `v3/core_report_bridge.py` | `packages/compat` | Adapt | Replace filesystem bridge with repository interface |
| `v3/financial`, financial kernel | `packages/finance` | Adapt | Decimal contract and finance reconciliation parity |
| `v3/metrics`, `v3/analytics` | Domain packages | Adapt | One owner per metric and golden tests |
| `v3/validation` | `packages/common` | Keep logic | Data-quality policy contract covered |
| `v3/decisions`, `src/analysis/ai_director.py` | `packages/recommendations` | Adapt | Recommendation persistence and evidence schema |
| `v3/memory` | Recommendations/outcomes persistence | Adapt | Tenant-scoped immutable audit model |
| `report_v2` | `packages/reports` | Adapt | Read-model report payload parity |
| `src/action_orchestrator.py` | `packages/automation` | Reuse candidates only | Policy, approval, dry-run and audit exist |
| `v3/api/wb_client.py`, `v3/wb_client.py`, `src/wb_client.py` | None | Deprecate | All callers use `packages/wb_core` |

## First migration gate

Do not import or move any legacy business calculation before the current
finance parity and report-v2 finalization regressions are green.
