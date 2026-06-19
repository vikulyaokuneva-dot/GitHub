# Audit mode (offline)

Папка `audit/` добавляет отдельный режим аудита по файлам без API.
Поддерживаются источники:
- `wb` (текущий режим Wildberries)
- `ozon` (MVP: отчет по товарам + cogs)

## Куда положить файлы (WB)

```
audit/input/finance/  - финансы (обязательный)
audit/input/funnel/   - воронка (обязательный)
audit/input/stocks/   - остатки (обязательный)
audit/input/ads/      - реклама (опциональный)
audit/input/search/   - поисковые запросы (опциональный)
audit/input/cogs/     - себестоимость (опциональный)
audit/input/orders/   - лента заказов (опциональный, нужна для геоданных)
```

## Куда положить файлы (Ozon MVP)

```
audit/input/ozon/products/   - отчет Ozon по товарам (обязательный)
audit/input/ozon/cogs/       - файл себестоимости (опциональный, но нужен для валовой прибыли)
```

## Локальный аудит (без cabinets)

Для запуска аудита из произвольной директории используйте `--audit-input-dir`:

```
local_audit/
├── input/
│   ├── finance/      - финансы (обязательный)
│   ├── funnel/       - воронка (обязательный)
│   ├── stocks/       - остатки (обязательный)
│   ├── ads/          - реклама (опциональный)
│   ├── search/       - поисковые запросы (опциональный)
│   ├── cogs/         - себестоимость (опциональный)
│   └── orders/       - лента заказов с геоданными (опциональный)
└── output/
    ├── audit_<date>.md
    ├── audit_<date>.pdf
    ├── facts_audit_<date>.json
    └── actions_audit_<date>.json
```

## Запуск локально

```bash
PYTHONPATH=. python run.py --mode audit --source wb --period 2026-02-23_2026-03-01
PYTHONPATH=. python run.py --mode audit --source ozon --audit-input-dir audit/input/ozon --period 2026-02-23_2026-03-01

# или напрямую
PYTHONPATH=. python audit/run_audit.py --source wb --input_dir audit/input
PYTHONPATH=. python audit/run_audit.py --source ozon --input_dir audit/input/ozon

# локальный аудит из произвольной директории
PYTHONPATH=. python audit/run_audit.py --source wb --input_dir local_audit/input --out_dir local_audit/output --period 2026-06-08_2026-06-14
```

## Выход

`audit/output/` (или `local_audit/output/`):
- `audit_<date>.pdf`
- `audit_<date>.md`
- `facts_audit_<date>.json`
- `actions_audit_<date>.json`
