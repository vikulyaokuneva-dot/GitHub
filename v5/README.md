# WB Analytics v5 – Новая архитектура

## 🎯 Видение

Единая, модульная платформа для управления данными Wildberries:
- **API Mode**: Daily pull от ВБ API (v2 функциональность)
- **Report Mode**: Аудит загруженных отчётов файловой системы (v3 функциональность)
- **Unified Analytics**: Единая кодовая база для аналитики независимо от источника данных
- **N Cabinet Support**: Полная поддержка изоляции данных для N кабинетов

## 📊 Ключевые отличия от v2/v3/v4

| Аспект | v2-v4 | v5 |
|--------|-------|-----|
| **Архитектура** | Монолит/Гибридная | Чистая слоистая (Clean Architecture) |
| **Контракты** | Определяются по ходу | Определяются в начале (`domain/contracts/`) |
| **Немного кабинетов** | Костыли, зависимости | Встроена с начала (Cabinet isolation) |
| **Размер кодовой базы** | ~20K строк (разброс) | ~5-7K строк (сфокусировано) |
| **Тестируемость** | Сложная | Легкая (DI, контракты) |
| **Код из старых версий** | Копируется (проблемы) | Переписывается (чистота) |

## 🏗️ Слои архитектуры

```
┌─────────────────────────────────┐
│      API / CLI / Schedule       │  ← Orchestrator, Entry Point
├─────────────────────────────────┤
│     Decisions & Facts Layer      │  ← Бизнес-логика (решения)
├─────────────────────────────────┤
│     Metrics & Analytics Layer    │  ← Вычисления метрик
├─────────────────────────────────┤
│     Normalization Layer          │  ← Унификация данных
├─────────────────────────────────┤
│     Domain Models (Contracts)    │  ← Структуры данных
├─────────────────────────────────┤
│  API Loaders │ Report Loaders    │  ← Источники данных (параллельно)
│  (ВБ API)    │ (File System)     │
└─────────────────────────────────┘
```

## 🗂️ Структура папок v5

```
v5/
├── README.md (этот файл)
├── ARCHITECTURE.md (подробное описание)
├── PLAN.md (дорожная карта по фазам)
├── requirements.txt
├── config.py (конфигурация)
├── __init__.py
├── entry.py (CLI entry point)
├── orchestrator.py (главный оркестратор)
│
├── domain/
│   ├── __init__.py
│   ├── contracts.py (RawData, NormalizedData, MetricsData, FactsData)
│   ├── cabinet.py (Cabinet, CabinetContext)
│   └── enums.py (Mode, Status, etc.)
│
├── infrastructure/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loaders.py (DataSourceConfig)
│   │   └── cabinet_paths.py (управление путями кабинетов)
│   │
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py (DataSource ABC)
│   │   ├── wb_api_loader.py (API pull от ВБ)
│   │   └── file_report_loader.py (аудит файлов)
│   │
│   └── storage/
│       ├── __init__.py
│       └── cabinet_storage.py (управление памятью, кэшем)
│
├── analytics/
│   ├── __init__.py
│   ├── normalization.py (сырые данные → нормализованные)
│   ├── metrics_engine.py (MetricsBuilder: metrics вычисления)
│   ├── facts_builder.py (Insights & Facts из метрик)
│   └── decisions_engine.py (Рекомендации на основе facts)
│
├── outputs/
│   ├── __init__.py
│   ├── report_generator.py (PDF, Excel)
│   └── json_exporter.py (JSON экспорт)
│
├── memory/
│   ├── __init__.py
│   ├── state.py (ProcessingState, cabinet state)
│   └── history.py (аудит лог)
│
└── tests/
    ├── __init__.py
    ├── fixtures/ (test data, mock API responses)
    ├── test_normalizer.py
    ├── test_metrics_engine.py
    └── test_facts_builder.py
```

## 🚀 Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Запустить daily API pull (как v2)
python -m v5 daily --cabinet seller_001

# 3. Запустить report audit (как v3)
python -m v5 audit --cabinet seller_001 --date 2024-03-30

# 4. Просмотр аналитики (unified для обоих режимов)
python -m v5 analytics --cabinet seller_001
```

## 📚 Документация

- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Подробное описание каждого слоя
- [**PLAN.md**](./PLAN.md) — Дорожная карта разработки (6 фаз)
- [**domain/contracts.py**](./domain/contracts.py) — Контракты (data classes)

## ⚙️ Ключевые принципы

1. **Dependency Injection** — Объекты конфигурируются при инициализации, не глобально
2. **Single Responsibility** — Каждый модуль делает одно и делает хорошо
3. **Testability** — Все слои имеют чётные интерфейсы, легко мокировать
4. **Separation of Concerns** — Бизнес-логика не зависит от инфра (API, файлы)
5. **Cabinet Isolation** — Данные каждого кабинета изолированы на каждом слое

## 📖 Статусы разработки

- [ ] Phase 1: Domain contracts + Cabinet isolation
- [ ] Phase 2: Data loaders (API, File)
- [ ] Phase 3: Normalization engine
- [ ] Phase 4: Metrics engine
- [ ] Phase 5: Facts + Decisions
- [ ] Phase 6: Outputs + CLI + Tests

---

**Следующий шаг**: Читайте [ARCHITECTURE.md](./ARCHITECTURE.md) для деталей каждого слоя.
