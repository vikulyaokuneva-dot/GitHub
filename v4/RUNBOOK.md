# V4 Daily + Audit Runbook

## Назначение
Краткий operational runbook для controlled use `v4` без production switch и без migration logic.

Цепочка исполнения:
`source -> normalize -> metrics -> facts -> decisions -> outputs`

## Режимы
- `daily_api_mode`: API-first daily pipeline.
- `audit_file_mode`: file-only offline pipeline.

Важно:
- daily и audit запускаются отдельно;
- audit не использует API ingestion;
- partial/unavailable данные отображаются честно;
- `None` не превращается в `0`.

## Локальный запуск daily
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15
```

С указанием каталога для output artifacts:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_daily_out
```

## Локальный запуск audit
```bash
python -m v4.entry.cli audit --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15
```

С указанием каталога для output artifacts:
```bash
python -m v4.entry.cli audit --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_audit_out
```

Поддерживаемые audit input варианты:
- директория с файлами (`csv/tsv/json/xlsx/xlsm`),
- zip-архив (распаковывается во временную контролируемую директорию).

Минимально ожидаемый файл для audit:
- `daily_report.*`

Опциональные файлы:
- `funnel_report.*`
- `ads_report.*`

## Smoke-run (рекомендовано перед controlled use)
Daily:
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_daily
```

Audit:
```bash
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_audit
```

Ожидаемый exit code:
- `0` = smoke OK
- `1` = pipeline execution error
- `2` = output/diagnostics sanity violation

## CI smoke helpers
Daily:
```bash
python v4/scripts/ci_smoke_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_ci_smoke_daily
```

Audit:
```bash
python v4/scripts/ci_smoke_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_ci_smoke_audit
```

Если `--input-path` не передан в `ci_smoke_audit.py`, создается минимальный временный audit input.

Минимальный CI-ready sanity sequence:
```bash
python -m unittest discover v4/tests
python -m compileall v4
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_daily
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_audit
```

## Ожидаемые артефакты (если передан output_dir)
В каталоге `output_dir`:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`

## Где смотреть diagnostics
В runtime result:
- `result["diagnostics"]["job"]`
- `result["diagnostics"]["summary"]`

В artifacts:
- `outputs_summary.json`

## Audit mode disclaimer
В `audit_file_mode` обязательно добавляется пометка:

`Отчет построен в audit_file_mode; выводы ограничены доступными файлами.`

## Обязательные pre-release проверки
1. `python -m unittest discover v4/tests` проходит без ошибок.
2. `python -m compileall v4` проходит без ошибок.
3. smoke-run для daily возвращает `exit code 0`.
4. smoke-run для audit возвращает `exit code 0`.
5. artifacts пишутся только в переданный `output_dir`.
6. diagnostics в финальном результате содержат `job` и `summary`.

## Ограничения текущего этапа
- Нет production switch.
- Нет migration logic v3 -> v4.
- Нет SMTP sending.
- Нет production PDF renderer.
- Нет LLM narrative synthesis.
