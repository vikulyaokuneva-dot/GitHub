# WB Analytics v5 – Полный скелет проекта

## 📊 Статус: Готово к разработке

✅ **Все документы созданы**  
✅ **Вся структура папок готова**  
✅ **Все контракты определены**  
✅ **Все skeleton файлы созданы**

---

## 📚 Навигация по документам

### 🔴 **Начните отсюда** → [GETTING_STARTED.md](./GETTING_STARTED.md)
Инструкции как начать разработку, как запустить импорты, checklist перед началом.

### 🔵 **Базовое понимание** → [README.md](./README.md)
- Видение проекта
- Отличия от v2/v3/v4
- Слои архитектуры (диаграмма)
- Структура папок
- Быстрый старт (будущие команды)

### 🟢 **Подробная архитектура** → [ARCHITECTURE.md](./ARCHITECTURE.md)
Deep dive в каждый слой:
1. **Domain Layer** – контракты, кабинеты
2. **Infrastructure Layer** – loaders, storage
3. **Analytics Layer** – normalization, metrics, facts, decisions
4. **Outputs Layer** – reports, exports
5. **Memory Layer** – state management
6. **Orchestrator** – главный координатор
7. Data Flow диаграмма
8. Как писать тесты

### 🟡 **Дорожная карта** → [PLAN.md](./PLAN.md)
6-недельный план с 6 фазами:
- Фаза 1: Domain & Cabinet Isolation (Неделя 1)
- Фаза 2: Data Loaders (Неделя 2)
- Фаза 3: Normalization (Неделя 3)
- Фаза 4: Metrics Engine (Неделя 4)
- Фаза 5: Facts & Decisions (Неделя 5)
- Фаза 6: Orchestration & Outputs (Неделя 6)

---

## 🗂️ Структура файлов

```
v5/
├── 📘 README.md (обзор)
├── 📗 ARCHITECTURE.md (deep dive)
├── 📕 PLAN.md (дорожная карта)
├── 📙 GETTING_STARTED.md (инструкции)
├── 📓 INDEX.md (этот файл)
│
├── 🎯 entry.py (CLI entry point)
├── 🎯 orchestrator.py (главный процесс)
├── ⚙️ config.py (конфигурация)
├── 📦 requirements.txt (зависимости)
│
├── 📂 domain/ (бизнес-логика)
│   ├── contracts.py ✅ (все data classes)
│   ├── cabinet.py ✅ (Cabinet, CabinetContext)
│   └── enums.py ✅ (RunMode, DataSource)
│
├── 📂 infrastructure/ (реализация деталей)
│   ├── config/
│   │   └── __init__.py (path management)
│   ├── sources/
│   │   ├── base.py ✅ (DataSource ABC)
│   │   ├── wb_api_loader.py (skeleton)
│   │   └── file_report_loader.py (skeleton)
│   └── storage/
│       └── cabinet_storage.py (skeleton)
│
├── 📂 analytics/ (основная бизнес-логика)
│   ├── normalization.py (skeleton)
│   ├── metrics_engine.py (skeleton)
│   ├── facts_builder.py (skeleton)
│   └── decisions_engine.py (skeleton)
│
├── 📂 outputs/ (экспорт результатов)
│   ├── report_generator.py (skeleton)
│   └── json_exporter.py (skeleton)
│
├── 📂 memory/ (состояние)
│   └── state.py (skeleton)
│
└── 📂 tests/ (тесты)
    ├── fixtures/
    │   └── conftest.py (pytest fixtures)
    └── (test_*.py файлы будут добавлены)
```

---

## 🚀 Быстрый старт разработки

### 1. Прочитайте документацию (5-10 минут)
```
README.md → ARCHITECTURE.md → PLAN.md → GETTING_STARTED.md
```

### 2. Проверьте импорты (2 минуты)
```bash
python -c "from domain import Cabinet, RawDataBundle; print('✓ OK')"
```

### 3. Начните Фазу 1: Domain (статус: ✅ ГОТОВО)
Контракты уже определены, переходите на Фазу 2.

### 4. Начните Фазу 2: Data Loaders (Неделя 1-2)
- Реализуйте `WBAPILoader.load_data()`
- Реализуйте `FileReportLoader.load_data()`
- Реализуйте `CabinetStorage`

### 5. Продолжайте остальные фазы
Следуйте PLAN.md, одна фаза за раз.

---

## 🔍 Что искать где

**Контракты (data classes)?** → `domain/contracts.py`  
**Cabinet конфиг?** → `domain/cabinet.py`  
**WB API логика?** → `infrastructure/sources/wb_api_loader.py`  
**Файловый отчётный аудит?** → `infrastructure/sources/file_report_loader.py`  
**Нормализация данных?** → `analytics/normalization.py`  
**Вычисление метрик?** → `analytics/metrics_engine.py`  
**Generation of insights?** → `analytics/facts_builder.py`  
**Рекомендации?** → `analytics/decisions_engine.py`  
**PDF/Excel отчёты?** → `outputs/report_generator.py`  
**Главный процесс?** → `orchestrator.py`  
**CLI?** → `entry.py`  

---

## ✅ Чек-лист перед началом разработки

- [ ] Прочитали [GETTING_STARTED.md](./GETTING_STARTED.md)
- [ ] Прошли импорт всех модулей (команда в GETTING_STARTED)
- [ ] Посмотрели диаграммы в [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ ] Посмотрели дорожную карту в [PLAN.md](./PLAN.md)
- [ ] Понимаете что такое RawDataBundle, NormalizedDataBundle, MetricsBundle, FactsBundle
- [ ] Понимаете что такое Cabinet и CabinetContext
- [ ] Готовы начать Фазу 2 (Data Loaders)

---

## 📞 Если что-то непонятно

// Ссылка на FAQ или docs
Смотрите разделы "FAQ" в GETTING_STARTED.md или ARCHITECTURE.md

---

## 🎯 Основные принципы

1. **Clean Architecture** – Слои независимы, тесты легко писать
2. **Dependency Injection** – Объекты конфигурируются снаружи
3. **Contracts First** – Данные (контракты) определены до логики
4. **Cabinet Isolation** – Каждый кабинет в своей папке с своим контекстом
5. **No Legacy Code** – Переписываем всё с нуля, не копируем из v2/v3/v4

---

## 📈 Ожидаемый результат (конец 6 недель)

- ✅ Полная система v5 работает и tested
- ✅ Оба режима: daily API pull + report audit
- ✅ Unified analytics для обоих режимов
- ✅ N cabinets поддержаны с полной изоляцией
- ✅ PDF/Excel отчёты генерируются
- ✅ Код чистый, документирован, протестирован
- ✅ Готово в production

---

**Следующий шаг**: Откройте [GETTING_STARTED.md](./GETTING_STARTED.md)

Успехов! 🎉
