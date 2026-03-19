# V4 Release Checklist

Минимальный checklist для controlled adoption V4.

## 1. Tests
```bash
python -m unittest discover v4/tests
```

## 2. Compile
```bash
python -m compileall v4
```

## 3. Operator preflight
```bash
python -m v4.entry.cli preflight --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```
Критерий: `PREFLIGHT SUCCESS`.

## 4. Operator smoke (dry-run)
```bash
python -m v4.entry.cli smoke --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```
Критерий: `SMOKE SUCCESS`.

## 5. Manual daily run
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```

## 6. Smoke Daily (legacy-compatible)
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_daily
```

## 7. Smoke Audit (legacy-compatible)
```bash
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_audit
```

## 8. Smoke Delivery PDF
```bash
python v4/scripts/smoke_render_pdf.py --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_render_pdf
```

## 9. Smoke Delivery Email Preview
```bash
python v4/scripts/smoke_email_payload.py --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_email_preview
```

## 10. Artifact verification
Проверить:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`
- `email_preview.json` (если delivery preview включен)
- `report.pdf` (если delivery PDF включен)

## 11. Diagnostics verification
Проверить:
- `diagnostics.job`
- `diagnostics.summary`
- `production.diagnostics` (если production switch path)
- `delivery.diagnostics` (если delivery включен)

Должны быть видимы:
- selected mode;
- reason/source;
- rollback_happened/fallback_used;
- dry_run;
- seller/cabinet labels;
- output_dir label.

## 12. Output path safety
Подтвердить, что runtime-artifacts не пишутся вне `output_dir`.

## 13. KPI discipline
Подтвердить, что KPI не пересчитываются вне `metrics`
(`source -> normalize -> metrics -> facts -> decisions -> outputs`).

## 14. Scheduler sanity (06:00 MSK)
Проверить workflow:
- `.github/workflows/v4-daily-0600-msk.yml`
- cron: `"0 3 * * *"` (UTC) = 06:00 Europe/Moscow
- есть `workflow_dispatch`
- есть preflight step перед run step.

## 15. Controlled rollback safety
Проверить, что rollback на legacy возможен и не silent:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --production-mode legacy
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --production-mode v4 --allow-fallback-to-legacy
```

