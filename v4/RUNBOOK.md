# V4 Daily + Audit Runbook

## Назначение
Operational runbook для controlled adoption `v4` в `daily` и `audit` режимах,
без production switch и без migration logic.

Цепочка исполнения (фиксированный порядок):
`source -> normalize -> metrics -> facts -> decisions -> outputs`

## Режимы
- `daily_api_mode`: API-first daily pipeline.
- `audit_file_mode`: file-only offline pipeline.

Ограничения режима:
- daily и audit запускаются отдельно;
- audit не использует API ingestion;
- partial/unavailable данные отображаются явно (без «подмены»);
- `None` не превращается в `0`.

## Local Run: Daily
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15
```

С артефактами в каталог:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_daily_out
```

## Local Run: Audit
```bash
python -m v4.entry.cli audit --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15
```

С артефактами в каталог:
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

## Smoke Commands
Daily smoke:
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_daily
```

Audit smoke:
```bash
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_audit
```

Ожидаемый exit code:
- `0` = smoke OK
- `1` = pipeline execution error
- `2` = output/diagnostics sanity violation

## CI Smoke Commands
Daily CI helper:
```bash
python v4/scripts/ci_smoke_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_ci_smoke_daily
```

Audit CI helper:
```bash
python v4/scripts/ci_smoke_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_ci_smoke_audit
```

Если `--input-path` не передан в `ci_smoke_audit.py`, создается минимальный временный audit input.

Минимальная CI sanity последовательность:
```bash
python -m unittest discover v4/tests
python -m compileall v4
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_daily
python v4/scripts/smoke_run_audit.py --input-path ./path/to/audit_input --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke_audit
```

## Expected Artifacts
Если передан `output_dir`, должны быть созданы:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`

Где искать:
- `result["outputs"]["artifacts"]["saved_files"]`

## Diagnostics Interpretation
Runtime diagnostics:
- `result["diagnostics"]["job"]`: полный job-level diagnostics.
- `result["diagnostics"]["summary"]`: компактный summary для мониторинга.

Ключевые поля summary:
- `mode`
- `partial_flag`
- `warnings_count`
- `decision_counts_by_priority`
- `artifacts_written`

Audit summary дополнительно:
- `files_detected_count`
- `files_missing_expected`
- `input_path_label`
- `audit_disclaimer`

Artifacts diagnostics:
- `outputs_summary.json` содержит deterministic summary (`build_timestamp=None` по design).

## Audit Disclaimer
В `audit_file_mode` обязательно присутствует пометка:

`Отчет построен в audit_file_mode; выводы ограничены доступными файлами.`

## Mode Limitations
- Нет production switch.
- Нет migration logic `v3 -> v4`.
- Нет SMTP sending.
- Нет production PDF renderer.
- Нет LLM narrative summaries.
- Нет новых KPI в `outputs`; KPI собираются только на стадии `metrics`.

## Known Constraints
- До передачи `output_dir` артефакты не пишутся на диск.
- При `output_dir` запись разрешена только внутри указанного каталога.
- В partial/unavailable сценариях decisions и summaries остаются прозрачными и консервативными.

## Release Gate
Проверочный список перед controlled adoption: [v4/RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md)
