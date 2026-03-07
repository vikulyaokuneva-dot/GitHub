# v3 (platform-ready) — скелет архитектуры

v3 — это новый контур (платформенный), который **не трогает** текущий рабочий вход `src/main.py` (v2-5 остаётся как есть).

Цель v3: подготовить архитектуру под ведение **N кабинетов** (multi-cabinet), с изоляцией данных и единым пайплайном.

## Директории

- `cabinets/<seller_id>/config.yaml` — конфиг кабинета (что собирать, куда слать, таймзона, налог и т.п.)
- `cabinets/<seller_id>/secrets.env` — локальные секреты (НЕ коммитятся)
- `cabinets/<seller_id>/data/...` — входные файлы (например, audit uploads / manual ads)
- `cabinets/<seller_id>/reports/<YYYY-MM-DD>/...` — выходные артефакты (facts/metrics/pdf)

## Запуск

### Daily (один кабинет)
```bash
python -m v3.entry daily --seller seller_001 --date 2026-03-05
```

### Daily (все кабинеты в `cabinets/*`)
```bash
python -m v3.entry daily --date 2026-03-05
```

### Audit (Excel офлайн)
```bash
python -m v3.entry audit --seller seller_001 --input cabinets/seller_001/data/audit_uploads/audit.xlsx --date 2026-03-05
```

## Как добавлять новый кабинет
1) Скопируй папку `cabinets/seller_001` как шаблон → `cabinets/seller_002`
2) Отредактируй `cabinets/seller_002/config.yaml`
3) Создай `cabinets/seller_002/secrets.env` (локально или через GitHub Secrets)
4) Запусти пайплайн для нового `--seller seller_002`

## Где менять логику
- источники данных: `v3/sources/*`
- этапы пайплайна: `v3/pipeline/*`
- оркестрация (что и в каком порядке): `v3/orchestrator.py`
- storage/пути/артефакты: `v3/storage.py`
- quality gate (проверки входов/выходов): `v3/quality_gate.py`

