import pandas as pd
import os

DIR = r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26'

# ===== 1. ВОРОНКА ПРОДАЖ — detailed comparison =====
print('=' * 90)
print('  ВОРОНКА ПРОДАЖ: PDF vs WB Воронка (по SKU)')
print('=' * 90)

funnel_file = [f for f in os.listdir(DIR) if 'Воронка' in f and '-2.xlsx' in f][0]
ff = pd.read_excel(os.path.join(DIR, funnel_file), sheet_name='Товары', header=1)

# All SKUs with activity
active = ff[ff['Заказали товаров, шт'] > 0].copy()

print(f'\n{"Артикул":<12} {"Название":<35} {"Показы":<8} {"Переходы":<10} {"Корзина":<8} {"Заказы":<8} {"Выкупы":<8} {"Сумма зак":<12} {"Сумма вык":<12}')
print('-' * 125)
for _, r in active.iterrows():
    print(f'{int(r["Артикул WB"]):<12} {str(r["Название"])[:33]:<35} {int(r["Показы"]):<8} {int(r["Переходы в карточку"]):<10} {int(r["Положили в корзину"]):<8} {int(r["Заказали товаров, шт"]):<8} {int(r["Выкупили, шт"]):<8} {int(r["Заказали на сумму, \u20bd"]):<12} {int(r["Выкупили на сумму, \u20bd"]):<12}')

# Totals
print('-' * 125)
print(f'{"ИТОГО":<12} {"":<35} {int(ff["Показы"].sum()):<8} {int(ff["Переходы в карточку"].sum()):<10} {int(ff["Положили в корзину"].sum()):<8} {int(ff["Заказали товаров, шт"].sum()):<8} {int(ff["Выкупили, шт"].sum()):<8} {int(ff["Заказали на сумму, \u20bd"].sum()):<12} {int(ff["Выкупили на сумму, \u20bd"].sum()):<12}')

# PDF funnel values
print(f'\n--- PDF воронка ---')
pdf_funnel = {
    'Показы': 'нет данных',
    'Клики': 318,
    'Корзина': 39,
    'Заказы': 13,
    'Выкупы': 3,
    'Клики->Корзина': '12.26%',
    'Корзина->Заказ': '33.33%',
    'Заказ->Выкуп': '23.08%',
}
for k, v in pdf_funnel.items():
    print(f'  {k}: {v}')

# WB funnel computed
wb_clicks = int(ff['Переходы в карточку'].sum())
wb_cart = int(ff['Положили в корзину'].sum())
wb_orders = int(ff['Заказали товаров, шт'].sum())
wb_purchases = int(ff['Выкупили, шт'].sum())
wb_order_sum = int(ff['Заказали на сумму, \u20bd'].sum())
wb_purchase_sum = int(ff['Выкупили на сумму, \u20bd'].sum())

print(f'\n--- WB воронка (итого) ---')
print(f'  Переходы: {wb_clicks}')
print(f'  Корзина: {wb_cart}')
print(f'  Заказы: {wb_orders}')
print(f'  Выкупы: {wb_purchases}')
print(f'  Сумма заказов: {wb_order_sum}')
print(f'  Сумма выкупов: {wb_purchase_sum}')
print(f'  Клики->Корзина: {wb_cart/wb_clicks*100:.2f}%' if wb_clicks else '  Клики->Корзина: N/A')
print(f'  Корзина->Заказ: {wb_orders/wb_cart*100:.2f}%' if wb_cart else '  Корзина->Заказ: N/A')
print(f'  Заказ->Выкуп: {wb_purchases/wb_orders*100:.2f}%' if wb_orders else '  Заказ->Выкуп: N/A')

print(f'\n--- РАСХОЖДЕНИЯ ВОРОНКИ ---')
print(f'  {"Показатель":<25} {"PDF":<15} {"WB воронка":<15} {"Разница"}')
print(f'  {"-"*70}')
print(f'  {"Переходы/клики":<25} {"318":<15} {str(wb_clicks):<15} {wb_clicks - 318:+d}')
print(f'  {"Корзина":<25} {"39":<15} {str(wb_cart):<15} {wb_cart - 39:+d}')
print(f'  {"Заказы":<25} {"13":<15} {str(wb_orders):<15} {wb_orders - 13:+d}')
print(f'  {"Выкупы":<25} {"3":<15} {str(wb_purchases):<15} {wb_purchases - 3:+d}')
print(f'  {"Сумма заказов":<25} {"29 120":<15} {str(wb_order_sum):<15} {wb_order_sum - 29120:+d}')
print(f'  {"Сумма выкупов":<25} {"2 040.20":<15} {str(wb_purchase_sum):<15} {wb_purchase_sum - 2040:+d}')
pdf_c2c = 12.26
wb_c2c = wb_cart/wb_clicks*100 if wb_clicks else 0
print(f'  {"Клики->Корзина %":<25} {"12.26%":<15} {f"{wb_c2c:.2f}%":<15} {wb_c2c - pdf_c2c:+.2f}pp')
pdf_c2o = 33.33
wb_c2o = wb_orders/wb_cart*100 if wb_cart else 0
print(f'  {"Корзина->Заказ %":<25} {"33.33%":<15} {f"{wb_c2o:.2f}%":<15} {wb_c2o - pdf_c2o:+.2f}pp')
pdf_o2p = 23.08
wb_o2p = wb_purchases/wb_orders*100 if wb_orders else 0
print(f'  {"Заказ->Выкуп %":<25} {"23.08%":<15} {f"{wb_o2p:.2f}%":<15} {wb_o2p - pdf_o2p:+.2f}pp')


# ===== 2. ЛОГИСТИКА И КОМИССИЯ WB — detail from financial report =====
print('\n\n' + '=' * 90)
print('  ЛОГИСТИКА И КОМИССИЯ WB: подробный разбор')
print('=' * 90)

det_file = [f for f in os.listdir(DIR) if '4297720' in f][0]
dd = pd.read_excel(os.path.join(DIR, det_file), header=0)

# All document types
print(f'\n--- Типы документов в файле ---')
print(dd['Тип документа'].value_counts(dropna=False).to_string())

# ALL rows (not just sales)
print(f'\n--- Все строки: итоги по столбцам ---')

# Find columns dynamically
cols = {}
for c in dd.columns:
    cl = str(c).lower()
    if 'количество доставок' == str(c).lower() or 'кол-во доставок' in cl:
        cols['deliveries'] = c
    if 'услуги по доставке' in cl:
        cols['delivery_fee'] = c
    if 'вознаграждение вайлдберриз' in cl and 'н/д' not in cl and 'корректировк' not in cl and 'ндс' not in cl:
        cols['vv'] = c
    if 'ндс с вознаграждения' in cl:
        cols['vv_nds'] = c
    if 'вознаграждение с продаж' in cl:
        cols['voznag'] = c
    if 'компенсация платёжных' in cl or 'комиссия за интеграцию' in cl:
        cols['acquiring'] = c
    if 'хранение' == str(c).strip().lower():
        cols['storage'] = c
    if 'общая сумма штрафов' in cl:
        cols['fines'] = c
    if 'корректировка вознаграждения' in cl:
        cols['vv_corr'] = c
    if 'возмещение издержек' in cl:
        cols['compensation'] = c
    if 'удержания' == str(c).strip().lower():
        cols['deductions'] = c
    if 'операции на приемке' in cl:
        cols['acceptance'] = c

print(f'\nНайденные столбцы: {list(cols.keys())}')

# Sum by document type
for dtype in dd['Тип документа'].dropna().unique():
    subset = dd[dd['Тип документа'] == dtype]
    print(f'\n--- Тип: {dtype} ({len(subset)} строк) ---')
    for key, col in cols.items():
        val = subset[col].sum()
        if val != 0:
            try:
                print(f'  {key}: {float(val):.2f}')
            except:
                print(f'  {key}: {val}')

# Also check NaN type rows (storage, logistics adjustments)
nan_rows = dd[dd['Тип документа'].isna()]
print(f'\n--- Строки без типа документа ({len(nan_rows)} строк) ---')
for key, col in cols.items():
    val = nan_rows[col].sum()
    if val != 0:
        try:
            print(f'  {key}: {float(val):.2f}')
        except:
            print(f'  {key}: {val}')

# Breakdown of logistics-related columns for ALL rows
print(f'\n--- СВОДКА ПО ВСЕМУ ФАЙЛУ ---')
def safe_num(series):
    """Sum numeric values, skip strings"""
    return pd.to_numeric(series, errors='coerce').sum()

print(f'  Доставок (кол-во): {safe_num(dd["Количество доставок"]):.0f}')
print(f'  Возвратов (кол-во): {safe_num(dd["Количество возврата"]):.0f}')
print(f'  Услуги доставки: {safe_num(dd[cols.get("delivery_fee", dd.columns[36])]):.2f}')
print(f'  ВВ (без НДС): {safe_num(dd[cols.get("vv", dd.columns[31])]):.2f}')
print(f'  НДС с ВВ: {safe_num(dd[cols.get("vv_nds", dd.columns[32])]):.2f}')
print(f'  Вознаграждение с продаж: {safe_num(dd[cols.get("voznag", dd.columns[26])]):.2f}')
print(f'  Эквайринг: {safe_num(dd[cols.get("acquiring", dd.columns[28])]):.2f}')
print(f'  Хранение: {safe_num(dd[cols.get("storage", dd.columns[59])]):.2f}')
print(f'  Штрафы: {safe_num(dd[cols.get("fines", dd.columns[40])]):.2f}')
print(f'  Корректировка ВВ: {safe_num(dd[cols.get("vv_corr", dd.columns[41])]):.2f}')
print(f'  Возмещение издержек: {safe_num(dd[cols.get("compensation", dd.columns[57])]):.2f}')
print(f'  Удержания: {safe_num(dd[cols.get("deductions", dd.columns[60])]):.2f}')
print(f'  Операции на приемке: {safe_num(dd[cols.get("acceptance", dd.columns[61])]):.2f}')

# Detailed per-SKU logistics
print(f'\n--- ЛОГИСТИКА ПО SKU (все строки) ---')
print(f'  {"SKU":<12} {"Доставки шт":<12} {"Стоимость дост":<15} {"ВВ без НДС":<15} {"НДС ВВ":<12} {"Эквайринг":<12} {"Хранение":<10} {"Штрафы":<10} {"Возмещение":<12}')
print(f'  {"-"*110}')
for sku in dd['Код номенклатуры'].dropna().unique():
    subset = dd[dd['Код номенклатуры'] == sku]
    d_del = safe_num(subset['Количество доставок'])
    d_fee = safe_num(subset[cols.get('delivery_fee', dd.columns[36])])
    d_vv = safe_num(subset[cols.get('vv', dd.columns[31])])
    d_vnds = safe_num(subset[cols.get('vv_nds', dd.columns[32])])
    d_acq = safe_num(subset[cols.get('acquiring', dd.columns[28])])
    d_stor = safe_num(subset[cols.get('storage', dd.columns[59])])
    d_fine = safe_num(subset[cols.get('fines', dd.columns[40])])
    d_comp = safe_num(subset[cols.get('compensation', dd.columns[57])])
    print(f'  {int(sku):<12} {d_del:<12.0f} {d_fee:<15.2f} {d_vv:<15.2f} {d_vnds:<12.2f} {d_acq:<12.2f} {d_stor:<10.2f} {d_fine:<10.2f} {d_comp:<12.2f}')


# ===== 3. ЛОГИСТИКА — PDF vs WB =====
print('\n\n' + '=' * 90)
print('  ЛОГИСТИКА: PDF vs WB')
print('=' * 90)

# PDF logistics
pdf_logistics = 0  # PDF says 0
pdf_storage = -28.84
pdf_acquiring = -48.40

# WB logistics (from sales only)
sales = dd[dd['Тип документа'] == 'Продажа']
wb_delivery_sales = safe_num(sales[cols.get('delivery_fee', dd.columns[36])])
wb_delivery_all = safe_num(dd[cols.get('delivery_fee', dd.columns[36])])
wb_storage_sales = safe_num(sales[cols.get('storage', dd.columns[59])])
wb_storage_all = safe_num(dd[cols.get('storage', dd.columns[59])])
wb_acquiring_sales = safe_num(sales[cols.get('acquiring', dd.columns[28])])
wb_acquiring_all = safe_num(dd[cols.get('acquiring', dd.columns[28])])
wb_fines_all = safe_num(dd[cols.get('fines', dd.columns[40])])
wb_compensation_all = safe_num(dd[cols.get('compensation', dd.columns[57])])
wb_deductions_all = safe_num(dd[cols.get('deductions', dd.columns[60])])
wb_acceptance_all = safe_num(dd[cols.get('acceptance', dd.columns[61])])
wb_corr_vv_all = safe_num(dd[cols.get('vv_corr', dd.columns[41])])
wb_deliveries_count = safe_num(dd['Количество доставок'])
wb_returns_count = safe_num(dd['Количество возврата'])

print(f'\n  {"Показатель":<35} {"PDF":<15} {"WB (продажи)":<15} {"WB (всё)":<15} {"Разница PDF vs WB(продажи)"}')
print(f'  {"-"*95}')
print(f'  {"Логистика (доставка), ₽":<35} {pdf_logistics:<15.2f} {wb_delivery_sales:<15.2f} {wb_delivery_all:<15.2f} {wb_delivery_sales - pdf_logistics:+.2f}')
print(f'  {"Хранение, ₽":<35} {pdf_storage:<15.2f} {wb_storage_sales:<15.2f} {wb_storage_all:<15.2f} {wb_storage_sales - pdf_storage:+.2f}')
print(f'  {"Эквайринг, ₽":<35} {pdf_acquiring:<15.2f} {wb_acquiring_sales:<15.2f} {wb_acquiring_all:<15.2f} {wb_acquiring_sales - pdf_acquiring:+.2f}')
print(f'  {"Штрафы, ₽":<35} {"0":<15} {"0":<15} {wb_fines_all:<15.2f} 0')
print(f'  {"Возмещение издержек, ₽":<35} {"н/д":<15} {"н/д":<15} {wb_compensation_all:<15.2f}')
print(f'  {"Удержания, ₽":<35} {"н/д":<15} {"н/д":<15} {wb_deductions_all:<15.2f}')
print(f'  {"Операции на приемке, ₽":<35} {"н/д":<15} {"н/д":<15} {wb_acceptance_all:<15.2f}')
print(f'  {"Корректировка ВВ, ₽":<35} {"н/д":<15} {"н/д":<15} {wb_corr_vv_all:<15.2f}')
print(f'  {"Кол-во доставок":<35} {"н/д":<15} {"н/д":<15} {wb_deliveries_count:<15.0f}')
print(f'  {"Кол-во возвратов":<35} {"н/д":<15} {"н/д":<15} {wb_returns_count:<15.0f}')


# ===== 4. КОМИССИЯ WB — detail =====
print('\n\n' + '=' * 90)
print('  КОМИССИЯ WB (ВОЗНАГРАЖДЕНИЕ): подробный разбор')
print('=' * 90)

# Sales-only commission
sv = safe_num(sales[cols.get('vv', dd.columns[31])])
sn = safe_num(sales[cols.get('vv_nds', dd.columns[32])])
svk = safe_num(sales[cols.get('voznag', dd.columns[26])])

# All rows commission
av = safe_num(dd[cols.get('vv', dd.columns[31])])
an_ = safe_num(dd[cols.get('vv_nds', dd.columns[32])])
avk = safe_num(dd[cols.get('voznag', dd.columns[26])])

print(f'\n  PDF "Комиссия WB": -162.08 ₽ (Вознаграждение с продаж, без НДС)')
print(f'\n  WB детализация:')
print(f'    ВВ без НДС (продажи):     {sv:.2f}')
print(f'    НДС с ВВ (продажи):       {sn:.2f}')
print(f'    ВВ итого (с НДС, продажи): {sv + sn:.2f}')
print(f'    Вознаграждение с продаж:   {svk:.2f}')
print(f'')
print(f'    ВВ без НДС (всё):         {av:.2f}')
print(f'    НДС с ВВ (всё):           {an_:.2f}')
print(f'    ВВ итого (с НДС, всё):    {av + an_:.2f}')
print(f'    Вознаграждение с продаж:   {avk:.2f}')
print(f'    Корректировка ВВ:          {wb_corr_vv_all:.2f}')

print(f'\n  PDF vs WB (по модулю ВВ):')
print(f'    PDF (-162.08) vs WB "Вознагр.с продаж" ({svk:.2f}) = {svk - (-162.08):+.2f}')
print(f'    PDF (-162.08) vs WB "ВВ без НДС" ({sv:.2f}) = {sv - (-162.08):+.2f}')
print(f'    PDF (-162.08) vs WB "ВВ итого" ({sv+sn:.2f}) = {sv+sn - (-162.08):+.2f}')

# Per-SKU commission
print(f'\n  Комиссия WB по SKU (все строки):')
print(f'  {"SKU":<12} {"ВВ без НДС":<15} {"НДС ВВ":<12} {"ВВ итого":<12} {"Вознагр.с продаж":<18} {"Коррект.ВВ":<12}')
print(f'  {"-"*80}')
for sku in dd['Код номенклатуры'].dropna().unique():
    subset = dd[dd['Код номенклатуры'] == sku]
    vv = safe_num(subset[cols.get('vv', dd.columns[31])])
    vnds = safe_num(subset[cols.get('vv_nds', dd.columns[32])])
    vvk = safe_num(subset[cols.get('voznag', dd.columns[26])])
    vcorr = safe_num(subset[cols.get('vv_corr', dd.columns[41])])
    print(f'  {int(sku):<12} {vv:<15.2f} {vnds:<12.2f} {vv+vnds:<12.2f} {vvk:<18.2f} {vcorr:<12.2f}')


# ===== 5. РЕКЛАМА =====
print('\n\n' + '=' * 90)
print('  РЕКЛАМА: данные из PDF (WB не предоставляет отдельный рекламный отчёт)')
print('=' * 90)

print(f'''
  PDF-данные по рекламе:
    Расход:              226.33 ₽
    Показы:              523 шт
    Клики:               56 шт
    CTR:                 10.71%
    CPC:                 4.04 ₽
    CPM:                 432.75 ₽
    Заказы из рекламы:   10
    Выручка из рекламы:  0 ₽
    Выкупы из рекламы:   0
    ROAS:                0.00x
    ROMI:                -100%
    CPO:                 22.63 ₽
    Прибыль от рекламы:  -226.33 ₽

  Сравнение с воронкой WB:
    Всего заказов (воронка):        13
    Заказов из рекламы (PDF):       10
    Заказов НЕ из рекламы:          3
    Доля рекламных заказов:         76.9%

    Выручка из рекламы (PDF):       0 ₽
    Сумма всех заказов:             29,120 ₽
    Сумма выкупов (реализация WB):  1,210 ₽
    --> Рекламные 10 заказов = 0₽ выручки = 100% убыток

  Ключевые проблемы рекламы:
    1. 10 из 13 заказов пришли из рекламы, но НИ ОДИН не выкуплен
    2. Все 3 выкупа — органические (не из рекламы)
    3. ROAS = 0 (ноль выручки на 226.33₽ расходов)
    4. CPO = 22.63₽ за каждый заказ (все невыкупленные)
    5. Реклама = чистый убыток -226.33₽

  Потенциальная экономия: 226.33 ₽/день при отключении рекламы
  (рекомендация из PDF: "Отключить убыточные запросы")
''')
