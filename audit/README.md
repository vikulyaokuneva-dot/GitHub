# Audit mode (offline)

Папка `audit/` добавляет отдельный режим "быстрого аудита" без WB API и без LLM.

## Куда положить файлы

```
audit/input/finance/  - финансовый детализированный отчет (xlsx)
audit/input/funnel/   - воронка продаж по товарам (xlsx, лист "Товары")
audit/input/ads/      - реклама (xlsx, лист "Статистика")
audit/input/stocks/   - остатки (xlsx)
```

## Запуск локально

```bash
PYTHONPATH=. python audit/run_audit.py --period 2026-02-23_2026-03-01
```

## Выход

`audit/artifacts/`:
- audit_<period>.pdf
- audit_<period>.md
- facts_audit_<period>.json
- actions_audit_<period>.json

## GitHub Actions
Workflow: `.github/workflows/audit.yml` (ручной запуск workflow_dispatch).
