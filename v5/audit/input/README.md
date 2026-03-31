# V5 Audit Input Files

Входные файлы для audit режима (загрузка из файлов вместо API).

## 📁 Структура папок

```
v5/audit/input/
├── finance/          # Отчёты по смете, маржинальности, себестоимости
├── funnel/           # Воронка продаж, статистика товаров
├── ads/              # Реклама, статистика объявлений
└── warehouse/        # Остатки, товары на складе
```

## 📄 Форматы файлов

### **finance/**
- `report_detail_by_period_{seller_id}_{date}.csv` – Детальный отчёт по периодам (комиссии, себестоимость)
- `margin_report_{seller_id}_{date}.xlsx` – Маржинальность по товарам

**Источник v3:** `src/analysis/` и `cabinets/{seller_id}/input/`

### **funnel/**
- `sales_funnel_{seller_id}_{date}.csv` – Воронка: показы → клики → заказы → исполнено
- `product_stats_{seller_id}_{date}.xlsx` – Статистика по товарам

**Источник v3:** `src/analytics/` и `cabinets/{seller_id}/input/`

### **ads/**
- `ads_stats_{seller_id}_{date}.csv` – Статистика объявлений (views, clicks, spend)
- `full_stats_{seller_id}_{date}.xlsx` – Полная статистика ad campaigns

**Источник v3:** `src/analysis/` и `cabinets/{seller_id}/input/`

### **warehouse/**
- `stocks_{seller_id}_{date}.csv` – Остатки товаров по складам
- `warehouse_info_{seller_id}_{date}.xlsx` – Информация о складах

**Источник v3:** `cabinets/{seller_id}/input/`

## 🔄 Workflow использования

1. **Вручную:**
   - Скопировать файлы отчётов из ВБ личного кабинета в нужные папки
   - Явно указать `seller_id` в фильтре

2. **Automated (GitHub Actions):**
   - Upload ZIP архив в release
   - GitHub Actions распаковывает в `v5/audit/input/`
   - Запускает `FileReportLoader`

## 📦 Архивирование для production

Когда проект готов, архивируются все старые версии:

```bash
# Архивируем не нужные версии
7z a -tzip v2_archive.zip src/ -xr!.git
7z a -tzip v3_archive.zip v3/ -xr!.git
7z a -tzip v4_archive.zip v4/ -xr!.git

# Оставляем только v5
rm -r src/ v3/ v4/
```

В production останется:
- `v5/` – рабочая версия
- `audit/` – входные файлы (если нужен режим аудита)
- `cabinets/` – результаты по кабинетам
- `venv/` – окружение
