# V4 Release Checklist

Минимальный checklist для release readiness `v4` в controlled adoption (`daily` / `audit`).

## 1. Tests
```bash
python -m unittest discover v4/tests
```
Критерий: все тесты проходят.

## 2. Compile
```bash
python -m compileall v4
```
Критерий: нет compile errors.

## 3. Smoke Daily
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_daily
```
Критерий: `exit code 0`.

## 4. Smoke Audit
```bash
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_audit
```
Критерий: `exit code 0`.

## 5. Artifact Verification
Проверить наличие и корректный JSON-формат:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`

## 6. Diagnostics Verification
Проверить в runtime result:
- `diagnostics.job`
- `diagnostics.summary`

Проверить в summary:
- `mode`
- `partial_flag`
- `warnings_count`
- `decision_counts_by_priority`

## 7. Output Dir Safety
Подтвердить, что pipeline не пишет файлы вне `output_dir`.

## 8. KPI Discipline
Подтвердить, что KPI не пересчитываются вне стадии `metrics`
(`source -> normalize -> metrics -> facts -> decisions -> outputs`).
