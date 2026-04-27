# Pytest triage after v5 legacy cleanup

## Current run status

- Command: `python -m pytest -q`
- Result: `23 failed, 383 passed, 6 errors`
- Collection status: OK. Previous `v5` import/`exit(1)` collection blocker is gone.
- `report_v2` status: green in dedicated run, `67 passed`.

Additional checks used for triage:

- `python -m pytest --collect-only -q` collected `412` tests successfully.
- `python -m pytest report_v2\tests -q` passed.
- Several failing v3 groups were rerun with `PDF_SOURCE_MODE=legacy` and `REPORT_VERSION=legacy` to distinguish real code regressions from env/config-sensitive failures.

## Failure groups

### 1. Env/config isolation: `.env` forces v2/core snapshot modes

Category: absent or incompatible test env/config isolation.

Observed behavior:

- Importing `v3` loads project `.env` through `v3.__init__`.
- In this environment, pytest runs with effective `PDF_SOURCE_MODE=core_snapshot` and `REPORT_VERSION=v2`.
- Many legacy-mode unit tests do not set these env vars explicitly, so they accidentally enter core-snapshot or v2 guard paths.

Representative errors:

- `CoreSnapshotBridgeFatalError: core_snapshot_context_missing: repo_root, seller_id, run_date`
- `RuntimeError: LEGACY_JOB_META_WRITE_FORBIDDEN_IN_REPORT_VERSION_V2`
- `_finalize_daily_delivery` takes v2 branch while a test expects legacy branch.

Tests in this group:

- `v3/tests/test_daily_output_health_payload.py::TestDailyOutputHealthPayload::test_reads_health_from_analytics_when_health_payload_missing`
- `v3/tests/test_daily_output_keyword_payload.py::TestDailyOutputKeywordPayload::test_reads_keyword_monitoring_from_analytics_when_payload_missing`
- `v3/tests/test_daily_output_profit_payload.py::TestDailyOutputProfitPayload::test_reads_profit_contribution_from_analytics_when_payload_missing`
- `v3/tests/test_daily_report_kpi_missing_labels.py::TestDailyReportKpiMissingLabels::test_funnel_upper_missing_shows_no_data_in_report_payload`
- `v3/tests/test_daily_report_kpi_missing_labels.py::TestDailyReportKpiMissingLabels::test_kpi_block_uses_human_labels_for_missing_values`
- `v3/tests/test_daily_report_kpi_missing_labels.py::TestDailyReportKpiMissingLabels::test_non_api_mode_keeps_partial_sections_and_business_reasons`
- `v3/tests/test_daily_report_territorial_section.py::TestDailyReportTerritorialSection::test_territorial_section_blocked_explains_reasons_without_raw_codes`
- `v3/tests/test_daily_report_territorial_section.py::TestDailyReportTerritorialSection::test_territorial_section_usable_has_recommendations_and_sku_rows`
- `v3/tests/test_report_meta_fields.py::TestReportMetaFields::test_report_meta_contains_email_and_dates`
- `v3/tests/test_report_version_mode.py::TestReportVersionMode::test_finalize_daily_delivery_uses_legacy_email_send_for_legacy_mode`

Triage result:

- These are not legacy tests and should not be moved to `scripts/legacy`.
- Most should be fixed by explicit env isolation in tests, for example setting `PDF_SOURCE_MODE=legacy` / `REPORT_VERSION=legacy` or deleting those env vars in setup.
- A global pytest fixture could isolate `.env`-driven report mode defaults, but it must preserve tests that intentionally assert v2/core-snapshot behavior.

### 2. Core snapshot/v2 writer compatibility

Category: incompatibility after project changes, uncovered by current `.env`.

Test:

- `v3/tests/test_core_snapshot_bridge_mode.py::TestCoreSnapshotBridgeMode::test_core_snapshot_stages_ignore_stale_legacy_fields`

Cause:

- The test intentionally runs `PDF_SOURCE_MODE=core_snapshot`.
- With effective `REPORT_VERSION=v2`, `run_daily_report_stage` still writes a legacy-sourced `report_meta.json`.
- `v3.storage.write_json` correctly blocks this with `LEGACY_JOB_META_WRITE_FORBIDDEN_IN_REPORT_VERSION_V2`.

Triage result:

- Do not skip as legacy.
- Needs a real compatibility fix: core-snapshot/v2 report-stage metadata should be written through the v2-safe path or carry the correct `report_version/source` metadata.

### 3. Financial snapshot alignment/status contract

Category: real regression or incomplete implementation.

Tests:

- `v3/tests/test_financial_snapshot_phase1.py::TestFinancialSnapshotContract::test_aligned_snapshot`
- `v3/tests/test_financial_snapshot_phase1.py::TestFinancialSnapshotContract::test_lagged_snapshot`
- `v3/tests/test_financial_snapshot_phase1.py::TestFinancialSnapshotBuilder::test_build_with_lagged_data`
- `v3/tests/test_financial_snapshot_phase1.py::TestFinancialSnapshotDownstreamParity::test_snapshot_alignment_visible_to_report`

Causes:

- Direct `FinancialSnapshot(...)` construction does not derive default alignment from `target_date/actual_date`.
- `FinancialSnapshot.is_aligned()` assumes `alignment` is not `None`.
- `build_financial_snapshot_from_kernel` treats a financial KPI payload with revenue but no row count as missing, so lagged data becomes `FinancialStatus.MISSING` instead of `LAGGED`.

Triage result:

- Real code fix needed in `v3/domain/financial_snapshot.py` and/or `v3/financial/snapshot_builder.py`.
- Do not move or skip; these are core v3 contract tests.

### 4. Financial kernel/API realization parity

Category: real regression or semantic mismatch in financial-kernel integration.

Tests:

- `v3/tests/test_api_realization_semantic_contract.py::TestApiRealizationSemanticContract::test_active_metrics_flow_uses_kernel_financials_for_api_rows`
- `v3/tests/test_api_realization_semantic_contract.py::TestApiRealizationSemanticContract::test_financial_status_degraded_when_semantic_groups_are_missing`
- `v3/tests/test_finance_realization_migration.py::TestFinanceRealizationMigration::test_downstream_financial_kernel_parity_for_new_finance_rows`
- `v3/tests/test_financial_kernel_pipeline_parity.py::TestFinancialKernelPipelineParity::test_gross_revenue_is_not_payout`
- `v3/tests/test_financial_kernel_pipeline_parity.py::TestFinancialKernelPipelineParity::test_regression_case_2026_04_13_reference_subset`

Symptoms:

- `financial_kpi.gross_revenue` is `0.0` where tests expect positive kernel totals.
- `financial_kpi.financial_status` is `missing` where semantic-contract tests expect `degraded`.
- In the full suite, the six `test_financial_kernel_pipeline_parity.py` tests appear as setup errors because `PDF_SOURCE_MODE=core_snapshot` is active. With legacy env override, four pass and the two real gross-revenue tests above still fail.

Likely causes to inspect:

- `v3/pipeline/daily_metrics_stage.py::_build_financial_kpi_from_kernel` and downstream snapshot conversion.
- `v3/metrics/financial_kernel.py` row classification/mapping for realization rows.
- Returned financial KPI appears to omit or lose row-count/source fields required by `FinancialSnapshotBuilder`, making non-empty financial data look missing.

Triage result:

- Real fix needed.
- Not legacy. Do not skip except possibly temporary xfail while financial-kernel migration is actively incomplete.

### 5. Daily financial lag rendering

Category: real regression, probably related to financial snapshot/date-alignment contract.

Tests:

- `v3/tests/test_daily_report_financial_lag_pdf.py::TestDailyReportFinancialLagPdf::test_finance_section_contains_lag_warning`
- `v3/tests/test_daily_report_financial_lag_pdf.py::TestDailyReportFinancialLagPdf::test_hero_kpi_does_not_treat_lagged_financials_as_same_day`
- `v3/tests/test_daily_report_financial_lag_pdf.py::TestDailyReportFinancialLagPdf::test_report_payload_marks_lagged_financials_for_pdf`

Symptoms:

- `financial_lagged` is false.
- Expected lag warning text is empty.
- Hero labels do not show the expected lagged-financial-slice wording.

Triage result:

- Real fix needed after or alongside the financial snapshot alignment fix.
- Not legacy and not external API/network.

### 6. API commerce funnel contract

Category: real regression or semantic mismatch.

Test:

- `v3/tests/test_api_commerce_contract.py::TestApiCommerceContract::test_sku_funnel_uses_api_lower_funnel_when_views_exist`

Symptom:

- SKU funnel row still has `issue_type == "insufficient_data"` when lower-funnel API data and views exist.

Triage result:

- Real fix needed in SKU funnel / API-commerce assembly.
- Not legacy, not env-only, not network.

### 7. Ozon audit smoke test mock is stale

Category: test incompatibility after function signature change.

Test:

- `src/tests/test_ozon_audit_smoke.py::test_ozon_audit_smoke`

Cause:

- `audit.run_audit.run_audit_mode` calls `markdown_to_simple_pdf(..., page_number_format=..., page_number_align=..., skip_first_page_numbering=True)`.
- The test's `_fake_pdf(markdown, out_path, title="")` mock does not accept these new keyword arguments.

Triage result:

- Safe test-only fix: update the fake to accept `**kwargs`.
- Do not move to legacy; this is a valid smoke test.

## Safe legacy/skip candidates

- Remaining failures do not look like obsolete standalone scripts.
- No remaining failing test should be moved to `scripts/legacy` based on current evidence.
- Safe cleanup already done for the old v5 standalone scripts.
- If a temporary unblock is needed, consider narrowly marking known in-progress financial-kernel migration tests as `xfail`, but the preferred next step is real fixes, not skips.

## What to fix next

Recommended order:

1. Add explicit pytest env isolation for `REPORT_VERSION` and `PDF_SOURCE_MODE`, while preserving tests that intentionally set them.
2. Fix `FinancialSnapshot` default alignment and `None` alignment handling.
3. Fix `FinancialSnapshotBuilder` / financial KPI row-count handling so non-empty financial KPI data is not marked missing.
4. Fix financial kernel/API realization gross-revenue propagation.
5. Fix daily financial lag rendering after snapshot alignment is correct.
6. Fix Ozon smoke mock signature with a test-only `**kwargs` change.
7. Fix API commerce SKU funnel issue-type semantics.
8. Fix core-snapshot/v2 metadata writer compatibility.

## Impact on AI Director / OpenRouter / report_v2

- AI Director: no failures point to `ai_director`.
- OpenRouter: no failures point to `src.openrouter_client` or LLM calls.
- report_v2: unaffected; `python -m pytest report_v2\tests -q` passed.
- External API/network: no current failures appear to depend on live network calls.
