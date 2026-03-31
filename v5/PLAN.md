# WB Analytics v5 – Дорожная карта (Roadmap)

## 📅 6-недельный план разработки

Каждая фаза строит на результатах предыдущей. Между фазами интеграционное тестирование.

---

## 🔵 Фаза 1: Domain & Cabinet Isolation (Неделя 1)

**Цель**: Определить контракты, настроить структуру изоляции кабинетов.

### Задачи:

1. **`domain/contracts.py`** – Все data classes
   - `RawAdsData`, `RawOrdersData`, `RawMarginsData`, `RawReturnsData`...
   - `RawDataBundle`
   - `NormalizedAds`, `NormalizedSKU`, `NormalizedDataBundle`
   - `AdMetrics`, `SKUMetrics`, `PortfolioMetrics`, `MetricsBundle`
   - `Fact`, `FactsBundle`
   - `Recommendation`

2. **`domain/cabinet.py`** – Cabinet & CabinetContext
   - Cabinet: id, name, api_key, wb_seller_id
   - CabinetContext: cabinet, data_root, config
   - CabinetConfig: thresholds, anomaly_settings, etc.

3. **`domain/enums.py`** – Перечисления
   - RunMode: DAILY_API, REPORT_AUDIT
   - DataSource: WB_API, FILE_REPORT
   - FactType: OPPORTUNITY, RISK, ANOMALY, TREND
   - Status: SUCCESS, FAILED, PARTIAL

4. **`infrastructure/config/cabinet_paths.py`**
   - Функции для вычисления путей кабинета
   - Пример: `get_cabinet_root(cabinet_id) → Path`
   - Пример: `get_raw_data_dir(cabinet_ctx) → Path`

### Результат:
- ✅ Все контракты определены и документированы
- ✅ Cabinet isolation работает (разные папки для разных кабинетов)
- ✅ Можно писать другие модули, не боясь ломать контракты

### Тесты:
```python
# test_contracts.py
def test_cabinet_context_isolation():
    ctx1 = CabinetContext(cabinet=Cabinet(id="seller_001"), ...)
    ctx2 = CabinetContext(cabinet=Cabinet(id="seller_002"), ...)
    
    assert ctx1.data_root != ctx2.data_root
```

---

## 🟠 Фаза 2: Data Loaders (Неделя 2)

**Цель**: Загружать данные из двух источников (API и файлы), преобразовать в `RawDataBundle`.

### Задачи:

1. **`infrastructure/sources/base.py`** – Абстракция
   ```python
   class DataSource(ABC):
       async def load_data(cabinet_ctx, date) -> RawDataBundle
   ```

2. **`infrastructure/sources/wb_api_loader.py`** – WB API
   - Эффективно использовать ВБ API (batch queries)
   - Загружать: ads, orders, margins, returns, ratings
   - Обработка ошибок (rate limit, timeout)
   - Логирование
   - Результат: `RawDataBundle(source="api")`

3. **`infrastructure/sources/file_report_loader.py`** – Excel/CSV
   - Читать отчёты из папки кабинета
   - Парсить Excel в сырые данные
   - Валидация (проверка обязательных полей)
   - Результат: `RawDataBundle(source="report")`

4. **`infrastructure/storage/cabinet_storage.py`** – Сохранение
   - Интерфейсы: save_raw, load_raw, save_metrics, save_facts
   - Реализация: JSON файлы в папке кабинета
   - Path: `cabinets/{id}/raw/{date}.json`

### Результат:
- ✅ Можно загружать данные из обоих источников
- ✅ Данные преобразуются в `RawDataBundle`
- ✅ Можно сохранять и загружать данные

### Тесты:
```python
# test_wb_api_loader.py
def test_api_loader_returns_raw_bundle(mock_api):
    loader = WBAPILoader(mock_api)
    raw = await loader.load_data(cabinet_ctx, datetime.date.today())
    
    assert isinstance(raw, RawDataBundle)
    assert raw.source == "api"
    assert len(raw.ads) > 0

# test_file_report_loader.py
def test_file_loader_parses_excel(sample_excel):
    loader = FileReportLoader()
    raw = loader.load_data(cabinet_ctx, datetime.date.today())
    
    assert isinstance(raw, RawDataBundle)
    assert raw.source == "report"
    assert raw.ads[0].name == expected_name
```

---

## 🟡 Фаза 3: Normalization (Неделя 3)

**Цель**: Преобразовать `RawDataBundle` (может быть из API или файла) в `NormalizedDataBundle`.

### Задачи:

1. **`analytics/normalization.py`** – Normalizer
   - Объединить ads + orders → unified metrics
   - Вычислить базовые метрики:
     - Impressions (views), clicks, spend
     - CTR = clicks / impressions
     - Spend per impression
   - Обработка edge cases (деление на 0, missing data)
   - **Важно**: Нормализация **не знает** откуда пришли данные
     - `RawDataBundle(source="api")` и `RawDataBundle(source="report")` → одинаковые результаты

2. **Cabinet isolation**: Каждый кабинет – свои normalized данные

### Результат:
- ✅ Сырые данные унифицированы
- ✅ API и file sources дают одинаковые результаты
- ✅ Можно писать метрики-engine, не беспокоясь об источнике

### Тесты:
```python
# test_normalizer.py
def test_normalizer_produces_same_result_from_api_and_file():
    # Создаём одинаковые сырые данные из API и файла
    raw_api = RawDataBundle(source="api", ads=[...], orders=[...])
    raw_file = RawDataBundle(source="report", ads=[...], orders=[...])
    
    norm_api = normalizer.normalize(raw_api)
    norm_file = normalizer.normalize(raw_file)
    
    # Проверяем, что результаты одинаковые
    assert norm_api.ads[0].ctr == norm_file.ads[0].ctr

def test_normalizer_handles_division_by_zero():
    raw = RawDataBundle(ads=[RawAdsData(..., views=0, clicks=0)], ...)
    normalized = normalizer.normalize(raw)
    
    # CTR должен быть 0, а не ошибка
    assert normalized.ads[0].ctr == 0
```

---

## 🟢 Фаза 4: Metrics Engine (Неделя 4)

**Цель**: Вычислить все KPI метрики из нормализованных данных.

### Задачи:

1. **`analytics/metrics_engine.py`** – MetricsEngine
   - Вычислить ~15-20 метрик:
     - CTR, CPC, ROAS, efficiency score
     - Revenue per ad, profit per ad
     - Segment performance (by category, by price)
     - Anomaly detection (sudden changes)
   - Использовать historical data (последние 30 дней)
   - Вычисления параллельно для разных SKU/ads

2. **Cabinet isolation**: Каждый кабинет – свои metricsBundle

### Результат:
- ✅ Полный набор метрик для каждого ad и sku
- ✅ Можно анализировать performance
- ✅ Historical comparison готов для facts

### Тесты:
```python
# test_metrics_engine.py
def test_cpc_calculation():
    normalized = NormalizedDataBundle(
        ads=[NormalizedAds(ad_id="1", spend=100.0, clicks=50)]
    )
    metrics = engine.calculate(normalized)
    
    assert metrics.ad_metrics[0].cpc == 100.0 / 50

def test_anomaly_detection():
    # 29 дней нормальных CTR, вдруг скачок в 30-й день
    normalized = NormalizedDataBundle(...)
    metrics = engine.calculate(normalized, historical=[...])
    
    assert metrics.ad_metrics[0].has_anomaly == True
```

---

## 🔵 Фаза 5: Facts & Decisions (Неделя 5)

**Цель**: Извлечь insights, найти opportunity и risks, сгенерировать recommendations.

### Задачи:

1. **`analytics/facts_builder.py`** – FactsBuilder
   - Сравнить текущие метрики с историей
   - Найти:
     - **Opportunities**: низкий CPC + высокий ROAS
     - **Risks**: падение CTR, рост CPC
     - **Anomalies**: аномальные скачки в данных
     - **Trends**: долгосрочные тренды (вверх/вниз)
   - Severity score (1-10)

2. **`analytics/decisions_engine.py`** – DecisionsEngine
   - На основе facts → actionable recommendations
   - Примеры:
     - "ad_123 имеет высокий ROAS (1.5x), увеличить бюджет"
     - "ad_456 падает в CTR (-20% за неделю), проверить"
     - "sku_789 продаётся лучше, перенести бюджет"

3. **Cabinet isolation**: Каждый кабинет – свои facts и recommendations

### Результат:
- ✅ Система может рекомендовать действия
- ✅ Menager может видеть opportunities и risks
- ✅ Полный цикл: data → metrics → facts → decisions

### Тесты:
```python
# test_facts_builder.py
def test_detects_opportunity():
    normalized = ...
    metrics = MetricsBundle(ad_metrics=[
        AdMetrics(ad_id="1", cpc=10, roas=2.0)  # opportunity
    ])
    historical = [...]  # metrics за прошлые дни
    
    facts = builder.build(normalized, metrics, historical)
    
    assert len(facts.facts) > 0
    assert facts.facts[0].type == FactType.OPPORTUNITY

def test_detects_risk():
    # Если CTR упал на 50% за день
    metrics = MetricsBundle(ad_metrics=[
        AdMetrics(ad_id="1", ctr=0.005)  # was 0.01
    ])
    historical = [AdMetrics(ad_id="1", ctr=0.01)]
    
    facts = builder.build(..., metrics, historical)
    
    assert facts.facts[0].type == FactType.RISK
```

---

## 🟣 Фаза 6: Orchestration & Outputs (Неделя 6)

**Цель**: Собрать всё вместе, создать CLI, тесты и deployment.

### Задачи:

1. **`orchestrator.py`** – Главный оркестратор
   ```python
   class Orchestrator:
       def run_daily(self, cabinet_id: str)
       def run_audit(self, cabinet_id: str, date)
   ```

2. **`entry.py`** – CLI entry point
   ```bash
   python -m v5 daily --cabinet seller_001
   python -m v5 audit --cabinet seller_001 --date 2024-03-30
   python -m v5 analytics --cabinet seller_001
   ```

3. **`outputs/report_generator.py`** – PDF/Excel отчёты
   - PDF с графиками, таблицами (как в v2)
   - Excel с детальными данными

4. **`outputs/json_exporter.py`** – JSON экспорт
   - Полное состояние для архивирования

5. **`memory/state.py`** – Сохранение состояния
   - Последние успешные запуски
   - Ошибки и сбои

6. **Тесты интеграции**
   ```python
   # test_orchestrator_daily.py
   def test_daily_workflow_end_to_end(mock_api):
       orch = Orchestrator(mock_api, ...)
       result = orch.run_daily("seller_001")
       
       # Проверяем что всё прошло
       assert result.status == Status.SUCCESS
       assert Path("cabinets/seller_001/outputs/report.pdf").exists()
   
   # test_orchestrator_audit.py
   def test_audit_workflow_end_to_end(sample_reports):
       orch = Orchestrator(file_loader, ...)
       result = orch.run_audit("seller_001", date.today())
       
       assert result.status == Status.SUCCESS
   ```

### Результат:
- ✅ Полная система работает end-to-end
- ✅ Можно запустить `python -m v5 daily`
- ✅ Отчёты генерируются
- ✅ Тесты покрывают весь flow

---

## 📊 Итоговый статус

| Фаза | Неделя | Статус | Блокеры |
|------|--------|--------|---------|
| 1: Domain | Неделя 1 | 📝 Готово планировать | Нет |
| 2: Loaders | Неделя 2 | Ждёт Фазы 1 | Контракты должны быть стабильны |
| 3: Normalization | Неделя 3 | Ждёт Фазы 2 | Data loaders работают |
| 4: Metrics | Неделя 4 | Ждёт Фазы 3 | Normalized data готова |
| 5: Facts/Decisions | Неделя 5 | Ждёт Фазы 4 | Metrics рассчитаны |
| 6: Orchestration | Неделя 6 | Ждёт Фазы 5 | Все компоненты готовы |

---

## 🚨 Важные моменты

### 1. Контракты должны быть стабильны
- Фаза 1 критическая. Если контракты меняются потом, придётся переделывать всё.
- Перед Фазой 2: review контрактов с требованиями.

### 2. Тесты пишите параллельно
- Не оставляйте тесты на последний момент.
- По окончании каждой фазы – полное тестовое покрытие.

### 3. Cabinet isolation от начала
- Если забыть про изоляцию в Фазе 1, потом будут серьёзные проблемы.
- Каждый cabinet должен иметь свой контекст, свои данные.

### 4. Не импортируйте из v2/v3/v4
- Если нужна логика из старых версий – переписать в v5.
- v2/v3/v4 – эталоны для тест-данных, не для копипасты.

---

## ✅ Definition of Done

После каждой фазы:
- [ ] Код написан и компилится
- [ ] Тесты написаны и проходят
- [ ] Документированы интерфейсы
- [ ] Нет hard-to-understand хаков
- [ ] Ready для code review

---

**Следующие шаги**:
1. Начните с Фазы 1: определите контракты
2. Создавайте файлы в `v5/domain/contracts.py`, `cabinet.py`, `enums.py`
3. Когда контракты готовы → переходите на Фазу 2
