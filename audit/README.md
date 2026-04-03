# Audit mode (offline)

Папка `audit/` добавляет отдельный режим аудита по файлам в `audit/input` без WB API.

## Куда положить файлы

```
audit/input/finance/  - финансы (обязательный)
audit/input/funnel/   - воронка (обязательный)
audit/input/stocks/   - остатки (обязательный)
audit/input/ads/      - реклама (опциональный)
audit/input/search/   - поисковые запросы (опциональный)
audit/input/cogs/     - себестоимость (опциональный)
```

## Запуск локально

```bash
PYTHONPATH=. python audit/run_audit.py --period 2026-02-23_2026-03-01
PYTHONPATH=. python run.py --mode audit --period 2026-02-23_2026-03-01
```

## Выход

`audit/output/`:
- `audit_<date>.pdf`
- `audit_<date>.md`
- `facts_audit_<date>.json`
- `actions_audit_<date>.json`
