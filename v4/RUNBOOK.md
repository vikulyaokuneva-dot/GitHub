# V4 Operator Runbook

## Назначение
Runbook для безопасной эксплуатации V4 без hard switch.

Базовая цепочка не меняется:
`source -> normalize -> metrics -> facts -> decisions -> outputs -> delivery`

## Режимы
- `daily_api_mode`: daily pipeline.
- `audit_file_mode`: offline file-only pipeline.

Ограничения:
- без пересчета KPI вне `metrics`;
- без silent fallback;
- partial/unavailable отображаются явно;
- `None` не превращается в `0`.

## Одна основная команда ручного daily запуска
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```

Если `--seller` не указан:
- при одном enabled seller он выбирается автоматически;
- при нескольких seller CLI просит указать seller явно.

## Operator flow (рекомендуемый путь)
1. Проверка готовности (preflight):
```bash
python -m v4.entry.cli preflight --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```

2. Безопасный smoke dry-run:
```bash
python -m v4.entry.cli smoke --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```

3. Реальный manual run:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
```

Дополнительные helper scripts:
```bash
python v4/scripts/preflight_daily.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
python v4/scripts/smoke_daily_operator.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4
python v4/scripts/scheduled_daily_run.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_outputs --production-mode v4 --dry-run
```

## Dry-run semantics
`--dry-run`:
- pipeline проходит все стадии;
- diagnostics и artifacts сохраняются;
- delivery side effects помечаются как skipped;
- production mode и rollback diagnostics сохраняются.

## Local Run: Audit
```bash
python -m v4.entry.cli audit --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_audit_out
```

## Smoke команды (legacy-compatible)
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_daily
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_audit
python v4/scripts/smoke_render_pdf.py --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_render_pdf
python v4/scripts/smoke_email_payload.py --mode daily --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_smoke_email_preview
```

CI smoke helpers:
```bash
python v4/scripts/ci_smoke_daily.py --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_ci_smoke_daily
python v4/scripts/ci_smoke_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-19 --output-dir ./.tmp/v4_ci_smoke_audit
```

## Артефакты и где смотреть
При `--output-dir` ожидаются:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`

Если включен delivery:
- `report.pdf`
- `email_preview.json`

Сводка артефактов:
- `result["outputs"]["artifacts"]["saved_files"]`

## Diagnostics interpretation
Ключевые места:
- `result["diagnostics"]["job"]`
- `result["diagnostics"]["summary"]`
- `result["diagnostics"]["operator"]` (для direct v4 path)
- `result["production"]["diagnostics"]` (для production switch path)
- `result["delivery"]["diagnostics"]` (если delivery включен)

Ключевые поля наблюдаемости:
- selected production mode;
- reason/source of decision;
- rollback happened / not happened;
- dry_run true/false;
- seller/cabinet context;
- run_date (requested/resolved);
- artifact/output labels.

## Controlled production switch + rollback
Примеры:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --production-mode legacy
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --production-mode v4
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --production-mode v4 --allow-fallback-to-legacy
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-19 --shadow-mode
```

Rollback на legacy:
- явный запуск с `--production-mode legacy`;
- fallback никогда не silent и отражается в diagnostics.

## Scheduled run 06:00 MSK
Основной path: GitHub Actions workflow
`/.github/workflows/v4-daily-0600-msk.yml`

Настройка времени:
- cron в GitHub Actions идет в UTC;
- `06:00 Europe/Moscow = 03:00 UTC`;
- в workflow используется `cron: "0 3 * * *"`.

Workflow содержит:
- `workflow_dispatch` для ручного запуска из UI;
- preflight step;
- scheduled daily step;
- upload artifacts.

Временное отключение schedule:
- установить repository variable `V4_SCHEDULE_ENABLED=false`.

## Validation gate перед запуском
```bash
python -m unittest discover v4/tests
python -m compileall v4
```

## Release Gate
Чеклист релиза: [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md)

