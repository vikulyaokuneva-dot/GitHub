# Getting Started with WB Analytics v5

## ✅ Setup Complete

Полная структура v5 создана и готова к разработке!

## 📦 Что создано

```
v5/
├── README.md (обзор проекта)
├── ARCHITECTURE.md (подробное описание архитектуры)
├── PLAN.md (дорожная карта 6 фаз)
├── GETTING_STARTED.md (этот файл)
├── requirements.txt
├── config.py (глобальная конфигурация)
├── entry.py (CLI entry point)
├── orchestrator.py (главный оркестратор)
│
├── domain/
│   ├── contracts.py ✅ (все data classes определены)
│   ├── cabinet.py ✅ (Cabinet, CabinetContext)
│   └── enums.py ✅ (RunMode, DataSource, etc.)
│
├── infrastructure/
│   ├── config/ (path management, cabinet setup)
│   ├── sources/ (DataSource ABC + 2 реализации)
│   │   ├── base.py ✅ (абстракция)
│   │   ├── wb_api_loader.py (skeleton)
│   │   └── file_report_loader.py (skeleton)
│   └── storage/ (CabinetStorage)
│
├── analytics/
│   ├── normalization.py (Normalizer)
│   ├── metrics_engine.py (MetricsEngine)
│   ├── facts_builder.py (FactsBuilder)
│   └── decisions_engine.py (DecisionsEngine)
│
├── outputs/
│   ├── report_generator.py (PDF, Excel)
│   └── json_exporter.py (JSON export)
│
├── memory/
│   └── state.py (ProcessingState, StateStorage)
│
└── tests/
    ├── fixtures/ (test data, mocks)
    └── conftest.py (pytest fixtures)
```

## 🚀 Как начать разработку

### Этап 1: Проверка структуры

```bash
cd d:\WB\Бот ИИ менеджер\GitHub\v5

# Убедитесь что все файлы создались
dir /s

# Проверьте что Python видит модули
python -c "from domain import Cabinet, CabinetContext; print('✓ Domain imports OK')"
```

### Этап 2: Установка зависимостей

```bash
# Активируем виртуальное окружение (если используется)
.venv\Scripts\activate

# Устанавливаем зависимости
pip install -r requirements.txt
```

### Этап 3: Начинаем с Фазы 1 (Контракты)

**Статус**: ✅ Контракты уже определены!

Проверьте [domain/contracts.py](./domain/contracts.py):
- `RawAdsData`, `RawOrdersData`, `RawMarginsData`, etc. – ✅
- `RawDataBundle` – ✅
- `NormalizedAds`, `NormalizedSKU`, `NormalizedDataBundle` – ✅
- `AdMetrics`, `SKUMetrics`, `MetricsBundle` – ✅
- `Fact`, `FactsBundle` – ✅

**Что делать дальше**: Если контракты нужно изменить, сделайте это **ДО** Фазы 2. Все остальные модули зависят от этих контрактов.

### Этап 4: Начинаем Фазу 2 (Data Loaders)

**Цель**: Реализовать `WBAPILoader` и `FileReportLoader`

**Входные данные**:
- `cabinet_ctx: CabinetContext` – контекст кабинета
- `target_date: date` – дата для载入 данных

**Выходные данные**:
- `RawDataBundle` – сырые данные

**Задачи**:
1. **WBAPILoader** (`infrastructure/sources/wb_api_loader.py`)
   - [ ] Использовать ВБ API (как в v2)
   - [ ] Загрузить ads, orders, margins, returns, ratings
   - [ ] Обработать ошибки (rate limit, timeout)
   - [ ] Вернуть RawDataBundle(source="api")

2. **FileReportLoader** (`infrastructure/sources/file_report_loader.py`)
   - [ ] Найти Excel/CSV файлы в `cabinet_ctx.inputs_dir`
   - [ ] Распарсить файлы
   - [ ] Валидировать данные
   - [ ] Вернуть RawDataBundle(source="report")

3. **CabinetStorage** (`infrastructure/storage/cabinet_storage.py`)
   - [ ] Реализовать save_raw(), load_raw()
   - [ ] Реализовать save_metrics(), save_facts()
   - [ ] Использовать JSON файлы для сохранения

**Тесты**:
- [x] Структура для тестов создана (`tests/fixtures/`)
- [ ] Напишите `test_wb_api_loader.py` – тестирование API loader
- [ ] Напишите `test_file_report_loader.py` – тестирование file loader

### Этап 5: Фаза 3 (Normalization)

**Цель**: Преобразовать RawDataBundle в NormalizedDataBundle

**Ключевой момент**: Результаты должны быть одинаковыми независимо от источника!

```python
raw_api = RawDataBundle(source="api", ...)
raw_file = RawDataBundle(source="report", ...)

norm_api = normalizer.normalize(raw_api)
norm_file = normalizer.normalize(raw_file)

# Проверяем что результаты идентичны
assert norm_api.ads[0].ctr == norm_file.ads[0].ctr  # ✓
```

**Задачи**:
- [ ] Реализовать `Normalizer.normalize()`
- [ ] Тест: `test_normalizer_same_result_from_api_and_file()`
- [ ] Тест: `test_normalizer_handles_division_by_zero()`

## 📝 Ключевые файлы для чтения

1. **[README.md](./README.md)** – Обзор проекта
2. **[ARCHITECTURE.md](./ARCHITECTURE.md)** – Подробный deep dive по архитектуре
3. **[PLAN.md](./PLAN.md)** – Дорожная карта с 6 фазами

## 🔍 Примеры использования контрактов

### Создание Cabinet и CabinetContext

```python
from domain import Cabinet, CabinetContext, CabinetConfig
from pathlib import Path

cabinet = Cabinet(
    id="seller_001",
    name="ООО РГК",
    api_key="...",
    wb_seller_id="..."
)

config = CabinetConfig(
    anomaly_ctr_change_percent=20.0,
    min_roas_opportunity=1.5
)

cabinet_ctx = CabinetContext(
    cabinet=cabinet,
    config=config,
    cabinet_root=Path("d:/cabinets/seller_001")
)

# Автоматические пути
print(cabinet_ctx.raw_data_dir)  # d:/cabinets/seller_001/data/raw
print(cabinet_ctx.reports_dir)   # d:/cabinets/seller_001/reports
```

### Создание RawDataBundle

```python
from domain import RawDataBundle, RawAdsData
from datetime import date

raw = RawDataBundle(
    cabinet_id="seller_001",
    period_date=date.today(),
    source="api",
    ads=[
        RawAdsData(
            ad_id="12345",
            name="Супер товар",
            sku_ids=["xyz"],
            budget_daily=1000.0,
            status="active",
            views=5000,
            clicks=250,
            spend=500.0,
            date=date.today()
        )
    ],
    orders=[...],
    margins=[...]
)
```

## 🧪 Тестирование структуры

Убедитесь что основные импорты работают:

```bash
# Проверить domain imports
python -c "
from domain import Cabinet, CabinetContext, RawDataBundle, NormalizedDataBundle
from domain import MetricsBundle, FactsBundle, ProcessingStatus
print('✓ All domain imports OK')
"

# Проверить infrastructure imports
python -c "
from infrastructure.sources import WBAPILoader, FileReportLoader
from infrastructure.storage import CabinetStorage
print('✓ All infrastructure imports OK')
"

# Проверить analytics imports
python -c "
from analytics.normalization import Normalizer
from analytics.metrics_engine import MetricsEngine
from analytics.facts_builder import FactsBuilder
from analytics.decisions_engine import DecisionsEngine
print('✓ All analytics imports OK')
"
```

## 📋 Checklist для начала

- [ ] Прочитали [README.md](./README.md) и [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ ] Прошли базовый импорт всех модулей (см. Тестирование выше)
- [ ] Проверили контракты в `domain/contracts.py`
- [ ] Готовы начать Фазу 2 (Data Loaders)
- [ ] Создана структура тестов

## ❓ Частые вопросы

**Q: Почему контракты в одном файле?**
A: Контракты стабильные и редко меняются. Одним файлом легче управлять зависимостями и видеть всю картину.

**Q: А что про v2/v3/v4 код?**
A: Не импортируйте его в v5. Используйте как эталон для тест-данных. v5 пишется с нуля.

**Q: Когда писать v4/v3 код в production?**
A: Пока v5 не готова (6+ недель). Продолжайте использовать v4 для produciton.

**Q: Есть примеры как использовать WB API?**
A: Смотрите `src/wb_client.py` в старых версиях. Скопируйте логику в `WBAPILoader`, но переписав под новые контракты.

## 🚨 Важные моменты

1. **Контракты стабильны** – Если их менять после Фазы 2, придётся переделывать остальное
2. **Cabinet isolation с самого начала** – Каждый кабинет = своя папка, свои данные, свой контекст
3. **Тесты параллельно** – Не оставляйте тесты на последнее
4. **Независимость модулей** – Normalizer не должен "знать" про API. Metrics не должна знать про storage.

---

**Следующий шаг**: Откройте [PLAN.md](./PLAN.md) и начните с Фазы 1 контрактов.

Успехов в разработке! 🚀
