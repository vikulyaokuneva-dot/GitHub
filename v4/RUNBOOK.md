# V4 Daily-Core Runbook

## Назначение
Краткий operational runbook для controlled use `v4` daily-core без production switch и без migration logic.

Цепочка исполнения:
`source -> normalize -> metrics -> facts -> decisions -> outputs`

## Локальный запуск daily
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15
```

С указанием каталога для output artifacts:
```bash
python -m v4.entry.cli daily --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_daily_out
```

## Smoke-run (рекомендовано перед controlled use)
```bash
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke
```

Ожидаемый exit code:
- `0` = smoke OK
- `1` = pipeline execution error
- `2` = output sanity violation

## CI smoke helper
```bash
python v4/scripts/ci_smoke_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_ci_smoke
```

Минимальный CI-ready sanity sequence:
```bash
python -m unittest discover v4/tests
python -m compileall v4
python v4/scripts/smoke_run_daily.py --seller seller_001 --date 2026-03-15 --output-dir ./.tmp/v4_smoke
```

## Ожидаемые артефакты (если передан output_dir)
В каталоге `output_dir`:
- `facts.json`
- `decisions.json`
- `outputs_summary.json`

## Обязательные pre-release проверки
1. `unittest discover` проходит без ошибок.
2. `compileall v4` проходит без ошибок.
3. smoke-run возвращает `exit code 0`.
4. artifacts пишутся только в переданный `output_dir`.
5. diagnostics в финальном результате содержат `job` и `summary`.

## Где смотреть diagnostics
- В runtime result:
  - `result["diagnostics"]["job"]`
  - `result["diagnostics"]["summary"]`
- В artifacts:
  - `outputs_summary.json`

## Ограничения текущего этапа
- Нет SMTP sending.
- Нет production PDF renderer.
- Нет LLM narrative synthesis.
- Нет production switch и migration logic.

