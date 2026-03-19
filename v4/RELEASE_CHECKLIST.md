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

## 5. Smoke Delivery PDF
```bash
python v4/scripts/smoke_render_pdf.py --mode daily --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_render_pdf
```
Критерий: `exit code 0`.

## 6. Smoke Delivery Email Preview
```bash
python v4/scripts/smoke_email_payload.py --mode daily --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_email_preview
```
Критерий: `exit code 0`.

## 7. Artifact Verification
Проверить наличие и корректный JSON-формат:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`
- `email_preview.json` (если delivery preview включен)
- `report.pdf` (если delivery PDF включен)

## 8. Diagnostics Verification
Проверить в runtime result:
- `diagnostics.job`
- `diagnostics.summary`
- `delivery.diagnostics` (если delivery включен)

Проверить в summary:
- `mode`
- `partial_flag`
- `warnings_count`
- `decision_counts_by_priority`

## 9. Output Dir Safety
Подтвердить, что pipeline не пишет файлы вне `output_dir`.

## 10. KPI Discipline
Подтвердить, что KPI не пересчитываются вне стадии `metrics`
(`source -> normalize -> metrics -> facts -> decisions -> outputs`).

## 11. Multi-Cabinet Sanity (Optional Gate)
For batch orchestration checks:
```bash
python -m v4.entry.cli daily --sellers seller_001,seller_002 --date 2026-03-15 --output-dir ./.tmp/v4_daily_multi
python -m v4.entry.cli audit --input-map seller_001=./input/a,seller_002=./input/b --sellers seller_001,seller_002 --date 2026-03-15 --output-dir ./.tmp/v4_audit_multi
```
Критерий:
- output dirs изолированы per seller/cabinet;
- batch summary содержит succeeded/partial/failed sellers;
- один failing seller не ломает остальных.

## 12. Production Switch & Rollback Safety
Проверить controlled switch path:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --production-mode legacy
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --production-mode v4
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --production-mode v4 --allow-fallback-to-legacy
```
Критерий:
- default production mode остаётся `legacy`;
- V4 активируется только явно/feature-gated;
- rollback/fallback никогда не silent и отражён в diagnostics.
