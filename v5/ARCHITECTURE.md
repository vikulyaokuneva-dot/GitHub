# WB Analytics v5 – Архитектура (Deep Dive)

## 1️⃣ Domain Layer (`domain/`)

Самый важный слой – контракты и структуры данных. **Нулевых зависимостей от фреймворков**.

### `contracts.py` – Основные структуры

```python
# RawData (из API или отчётов)
@dataclass
class RawAdsData:
    ad_id: str
    name: str
    price: int
    views: int
    clicks: int
    # ... etc
    source: str  # "api" или "report"

@dataclass
class RawOrdersData:
    order_id: str
    sku_id: str
    quantity: int
    revenue: float
    date: datetime.date
    # ... etc

# Bundle – группа сырых данных за период
@dataclass
class RawDataBundle:
    cabinet_id: str
    period_date: datetime.date
    ads: list[RawAdsData]
    orders: list[RawOrdersData]
    margins: list[...] 
    # ... и др. таблицы из ВБ
    source: Literal["api", "report"]  # Отслеживаем источник


# NormalizedData (унифицированный формат)
@dataclass
class NormalizedAds:
    ad_id: str
    sku_ids: list[str]  # На один адс может быть N SKU
    spend: float
    impressions: int
    clicks: int
    # Нормализованные метрики

@dataclass
class NormalizedDataBundle:
    cabinet_id: str
    period_date: datetime.date
    ads: list[NormalizedAds]
    skus: list[NormalizedSKU]
    # ... нормализованные данные


# MetricsData (вычисленные метрики)
@dataclass
class AdMetrics:
    ad_id: str
    ctr: float  # click-through rate
    cpc: float  # cost per click
    roas: float  # return on ad spend
    efficiency_score: float
    # ... 10-15 вычисленных метрик

@dataclass
class MetricsBundle:
    cabinet_id: str
    period_date: datetime.date
    ad_metrics: list[AdMetrics]
    sku_metrics: list[SKUMetrics]
    portfolio_metrics: PortfolioMetrics


# FactsData (insights & anomalies)
@dataclass
class Fact:
    type: Literal["opportunity", "risk", "anomaly", "trend"]
    title: str
    description: str
    severity: int  # 1-10
    affected_ids: list[str]  # ad_ids или sku_ids

@dataclass
class FactsBundle:
    cabinet_id: str
    period_date: datetime.date
    facts: list[Fact]
    recommendations: list[str]
```

### `cabinet.py` – Управление кабинетами

```python
@dataclass
class Cabinet:
    id: str  # "seller_001"
    name: str  # "ООО Рога и копыта"
    api_key: str
    wb_seller_id: str
    
@dataclass
class CabinetContext:
    cabinet: Cabinet
    data_root: Path  # d:/...../cabinets/seller_001/
    config: CabinetConfig
```

### `enums.py`

```python
class RunMode(Enum):
    DAILY_API = "daily"      # Pull от ВБ API
    REPORT_AUDIT = "audit"   # Аудит файлов
    
class DataSource(Enum):
    WB_API = "api"
    FILE_REPORT = "report"
    
class FactType(Enum):
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    ANOMALY = "anomaly"
    TREND = "trend"
```

**Почему это важно:**
- Контракты – это соглашение между модулями
- Если контракты определены, остальное легче писать
- Тесты можно писать на основе контрактов

---

## 2️⃣ Infrastructure Layer (`infrastructure/`)

Реализация деталей: как загружать, где хранить данные.

### `sources/base.py` – Абстракция

```python
class DataSource(ABC):
    @abstractmethod
    async def load_data(
        self, 
        cabinet_ctx: CabinetContext,
        date: datetime.date
    ) -> RawDataBundle:
        """Загрузить сырые данные из источника"""
        pass
```

### `sources/wb_api_loader.py`

- Вызывает ВБ API (как в v2)
- Загружает: ads, orders, margins, returns, ratings...
- Возвращает: `RawDataBundle` с `source="api"`

### `sources/file_report_loader.py`

- Читает Excel/CSV из папки кабинета (как в v3)  
- Парсит отчёты в сырые данные
- Возвращает: `RawDataBundle` с `source="report"`

### `storage/cabinet_storage.py`

```python
class CabinetStorage:
    def __init__(self, cabinet_ctx: CabinetContext): ...
    
    def save_raw(self, bundle: RawDataBundle) -> None:
    def load_raw(self, date: datetime.date) -> RawDataBundle | None:
    
    def save_normalized(self, bundle: NormalizedDataBundle) -> None:
    def load_normalized(self, date: datetime.date) -> NormalizedDataBundle | None:
    
    def save_metrics(self, bundle: MetricsBundle) -> None:
    def save_facts(self, bundle: FactsBundle) -> None:
```

---

## 3️⃣ Domain Models (Contracts) – вторая часть

Это **не** слой, а часть `domain/`. Но так важна, что выделю отдельно.

Все контракты лежат в одном файле: `domain/contracts.py`

**Почему в одном файле?**
- Легко видеть все зависимости между сущностями
- Контракты должны быть стабильными
- Остальной код импортирует оттуда

---

## 4️⃣ Analytics Layer (`analytics/`)

Здесь живёт вся бизнес-логика.

### `normalization.py`

```python
class Normalizer:
    def normalize(self, raw: RawDataBundle) -> NormalizedDataBundle:
        """
        RawDataBundle (может быть из API или отчётов)
        →
        NormalizedDataBundle (однородный формат)
        """
        # Логика унификации для API и файлов одинакова
        # Например: RawAdsData + RawOrdersData → NormalizedAds с unified metrics
```

**Ключевой момент**: Normalization **не знает** откуда пришли данные (API или report). 
Она только преобразует контракты.

### `metrics_engine.py`

```python
class MetricsEngine:
    def calculate(self, normalized: NormalizedDataBundle) -> MetricsBundle:
        """
        NormalizedDataBundle
        →
        calculate CTR, CPC, ROAS, efficiency scores, anomalies
        →
        MetricsBundle
        """
```

Вычисляет all 15-20 основных метрик.

### `facts_builder.py`

```python
class FactsBuilder:
    def build(
        self,
        normalized: NormalizedDataBundle,
        metrics: MetricsBundle,
        historical_metrics: dict[str, MetricsBundle]  # история за месяц
    ) -> FactsBundle:
        """
        Сравнивает текущие метрики с историей:
        - Найти opportunity (низкие CPC, высокие ROAS)
        - Найти risks (падение CTR, рост CPC)
        - Найти anomalies (аномальные скачки)
        - Найти trends (долгосрочные тренды)
        """
```

### `decisions_engine.py`

```python
class DecisionsEngine:
    def generate_recommendations(
        self,
        facts: FactsBundle,
        cabinet_config: CabinetConfig
    ) -> list[str]:
        """
        Facts → Actionable recommendations
        
        Примеры:
        - "Увеличить бюджет на ad_123 (возможность)"
        - "Снизить ставку на ad_456 (риск падения)"
        - "Проверить ad_789 (аномалия)"
        """
```

---

## 5️⃣ Outputs Layer (`outputs/`)

Интеграция и экспорт результатов.

### `report_generator.py`

- PDF отчёт (как в v2)
- Excel файл с таблицами
- Использует `FactsBundle` + `MetricsBundle`

### `json_exporter.py`

- JSON с полным состоянием
- Для архивирования и анализа

---

## 6️⃣ Memory Layer (`memory/`)

Сохранение состояния между запусками.

### `state.py`

```python
@dataclass
class ProcessingState:
    cabinet_id: str
    last_successful_api_pull: datetime.datetime | None
    last_successful_report_audit: datetime.datetime | None
    current_phase: Literal["loading", "normalizing", "computing", "decided"]
    
class StateStorage:
    def save_state(self, state: ProcessingState) -> None:
    def load_state(self, cabinet_id: str) -> ProcessingState:
```

### `history.py`

- Каждый запуск логируется
- Отслеживаем ошибки, сбои
- Для debug и аудита

---

## 7️⃣ Orchestrator (`orchestrator.py`)

Главный оркестратор, который:

1. Загружает Cabinet config
2. Создаёт CabinetContext
3. Выбирает DataSource (API или File)
4. Вызывает слои по цепочке: load → normalize → metrics → facts → decisions → output

```python
class Orchestrator:
    def run_daily(self, cabinet_id: str):
        cabinet_ctx = self.load_cabinet(cabinet_id)
        
        # Выбираем источник
        source = WBAPILoader(cabinet_ctx)
        
        # Цепочка
        raw = await source.load_data(cabinet_ctx, date.today())
        normalized = self.normalizer.normalize(raw)
        metrics = self.metrics_engine.calculate(normalized)
        facts = self.facts_builder.build(normalized, metrics, history)
        decisions = self.decisions_engine.generate(facts)
        
        # Сохраняем
        storage.save_all(raw, normalized, metrics, facts)
        
        # Рендерим отчёт
        self.report_generator.generate(metrics, facts, decisions)
    
    def run_audit(self, cabinet_id: str, date: datetime.date):
        # То же, но с FileReportLoader вместо APILoader
        source = FileReportLoader(cabinet_ctx)
        # ... остальное идентично
```

**Красота**: `run_daily` и `run_audit` отличаются **только** выбором источника.
Остальная логика – одна и та же.

---

## 🔄 Data Flow (пример: Daily API pull)

```
User: python -m v5 daily --cabinet seller_001
            ↓
     Orchestrator.run_daily(cabinet_id)
            ↓
     Load Cabinet Config
            ↓
     WBAPILoader.load_data()  ← API call
            ↓
     RawDataBundle (API source)
            ↓
     Normalizer.normalize()
            ↓
     NormalizedDataBundle (single format)
            ↓
     MetricsEngine.calculate()
            ↓
     MetricsBundle
            ↓
     FactsBuilder.build() + HistoryDB
            ↓
     FactsBundle (insights, opportunities, risks)
            ↓
     DecisionsEngine.generate()
            ↓
     Recommendations
            ↓
     ReportGenerator.generate()
            ↓
     PDF/Excel/JSON output
            ↓
     CabinetStorage.save_all()
```

---

## 🧪 Как это тестировать

Каждый слой имеет чёткий интерфейс → легко мокировать:

```python
# Тест Normalizer: мок RawDataBundle → проверить NormalizedDataBundle
def test_normalizer_unifies_data():
    raw_api = RawDataBundle(source="api", ...)
    raw_report = RawDataBundle(source="report", ...)
    
    normalized_from_api = normalizer.normalize(raw_api)
    normalized_from_report = normalizer.normalize(raw_report)
    
    # Проверяем, что результаты одинаковые (независимо от источника)
    assert normalized_from_api.ads[0].cpc == normalized_from_report.ads[0].cpc

# Тест MetricsEngine: мок NormalizedDataBundle → проверить MetricsBundle
def test_metrics_cpc_calculation():
    normalized = NormalizedDataBundle(...)
    metrics = engine.calculate(normalized)
    
    expected_cpc = 100 / 50  # spend / clicks
    assert metrics.ad_metrics[0].cpc == expected_cpc
```

---

## 📋 Checklist внедрения

- [ ] Определить все контракты в `domain/contracts.py`
- [ ] Реализовать `DataSource` ABC и два наследника (API, File)
- [ ] Реализовать `Normalizer`
- [ ] Реализовать `MetricsEngine`
- [ ] Реализовать `FactsBuilder`  
- [ ] Реализовать `DecisionsEngine`
- [ ] Реализовать `Orchestrator`
- [ ] Добавить `cabinet_storage` для сохранения
- [ ] Добавить CLI entry point
- [ ] Написать тесты для каждого слоя

---

**Следующий шаг**: [PLAN.md](./PLAN.md) – дорожная карта по фазам.
