import pandas as pd

# === PDF data (извлечено из report_v2 (18).pdf) ===
pdf_orders = 13
pdf_order_sum = 29120
pdf_purchases = 3
pdf_purchase_sum = 2040.20
pdf_profit = 1170.88
pdf_ads = -226.33
pdf_stock = 107
pdf_revenue = 2040.20
pdf_commission = -162.08
pdf_logistics = 0
pdf_storage = -28.84
pdf_acquiring = -48.40
pdf_cogs = -630
pdf_total_costs = -869.32
pdf_margin = 57.4
pdf_sku333_rev = 620
pdf_sku452_rev = 1420.20
pdf_sku333_profit = 272.24
pdf_sku452_profit = 833.64
pdf_sku333_ads = 200.52

# === Funnel data (из Воронка продаж, лист "Товары") ===
funnel_path = r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26\5-7-2026 Воронка продаж по дням с 04-07-2026 по 04-07-2026-2.xlsx'
ff = pd.read_excel(funnel_path, sheet_name='Товары', header=1)
funnel_orders_total = ff['Заказали товаров, шт'].sum()
funnel_order_sum_total = ff['Заказали на сумму, \u20bd'].sum()
funnel_purchases_total = ff['Выкупили, шт'].sum()
funnel_purchase_sum_total = ff['Выкупили на сумму, \u20bd'].sum()

# === WB detailed report ===
det_path = r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26' + '\\' + [f for f in __import__('os').listdir(r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26') if '4297720' in f][0]
dd = pd.read_excel(det_path, sheet_name=0, header=0)
sales = dd[dd['Тип документа'] == '\u041f\u0440\u043e\u0434\u0430\u0436\u0430']
det_qty = sales['\u041a\u043e\u043b-\u0432\u043e'].sum()
det_realized = sales['\u0412\u0430\u0439\u043b\u0434\u0431\u0435\u0440\u0440\u0438\u0437 \u0440\u0435\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043b \u0422\u043e\u0432\u0430\u0440 (\u041f\u0440)'].sum()
det_transfer = sales['\u041a \u043f\u0435\u0440\u0435\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044e \u041f\u0440\u043e\u0434\u0430\u0432\u0446\u0443 \u0437\u0430 \u0440\u0435\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0422\u043e\u0432\u0430\u0440'].sum()
det_vv = sales[[c for c in sales.columns if 'Вознаграждение Вайлдберриз (ВВ)' in str(c)][0]].sum()
det_voznag2 = sales[[c for c in sales.columns if 'Вознаграждение с продаж' in str(c)][0]].sum()
det_voznag = sales[[c for c in sales.columns if 'Вознаграждение с продаж' in str(c)][0]].sum()
det_delivery = sales[[c for c in sales.columns if 'доставке товара' in str(c)][0]].sum()
det_acquiring = sales[[c for c in sales.columns if 'платёжных услуг' in str(c)][0]].sum()

# Per-SKU from detailed report
sku_detail = {}
for _, row in sales.iterrows():
    sku = row['Код номенклатуры']
    if sku not in sku_detail:
        sku_detail[sku] = {'qty': 0, 'realized': 0, 'transfer': 0}
    sku_detail[sku]['qty'] += row['Кол-во']
    realized_col = [c for c in sales.columns if 'реализовал' in str(c).lower()][0]
    transfer_col = [c for c in sales.columns if 'перечислению' in str(c).lower()][0]
    sku_detail[sku]['realized'] += row[realized_col]
    sku_detail[sku]['transfer'] += row[transfer_col]

# Per-SKU from funnel
sku_funnel = {}
for _, row in ff.iterrows():
    sku = row['Артикул WB']
    if sku in [333615320, 590614192, 551253854, 898642228, 452102417]:
        sku_funnel[sku] = {
            'orders': row['Заказали товаров, шт'],
            'order_sum': row['Заказали на сумму, \u20bd'],
            'purchases': row['Выкупили, шт'],
            'purchase_sum': row['Выкупили на сумму, \u20bd'],
            'clicks': row['Переходы в карточку'],
            'cart': row['Положили в корзину'],
        }

# Stock data
stock_path = r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\04-07-26\report_2026_7_5.xlsx'
sd = pd.read_excel(stock_path, header=0)
stock_col = [c for c in sd.columns if 'находится на складах' in str(c)][0]
transit_col = [c for c in sd.columns if 'пути до' in str(c)][0]
returns_col = [c for c in sd.columns if 'пути возвраты' in str(c)][0]
stock_on_hand = sd.dropna(subset=[stock_col])[stock_col].sum()
stock_in_transit = sd[transit_col].sum()
stock_returns = sd[returns_col].sum()
stock_total_wb = stock_on_hand + stock_in_transit + stock_returns

# ========== OUTPUT ==========
out = []
def w(s=''):
    out.append(s)

w('=' * 80)
w('  СРАВНИТЕЛЬНАЯ ТАБЛИЦА: PDF-ОТЧЁТ vs ОТЧЁТЫ WILDBERRIES')
w('  Дата: 04.07.2026 (вчера)')
w('=' * 80)

w('')
w('--- БЛОК 1: СВОДНЫЕ ПОКАЗАТЕЛИ ---')
w(f'{"Показатель":<35} {"PDF":<18} {"WB":<18} {"Δ"}')
w('-' * 80)

def cmp(name, pv, wv, fmt='.2f'):
    d = wv - pv
    mark = 'OK' if abs(d) < 0.01 else 'DIFF'
    ps = format(pv, fmt) if isinstance(pv, (int, float)) else str(pv)
    ws = format(wv, fmt) if isinstance(wv, (int, float)) else str(wv)
    ds = format(d, '+' + fmt) if isinstance(d, (int, float)) else str(d)
    w(f'{name:<35} {ps:<18} {ws:<18} {ds:>15}  {mark}')

cmp('Заказы, шт', pdf_orders, int(funnel_orders_total), '.0f')
cmp('Сумма заказов, ₽', pdf_order_sum, funnel_order_sum_total, '.0f')
cmp('Выкупы, шт', pdf_purchases, int(funnel_purchases_total), '.0f')
cmp('Сумма выкупов, ₽', pdf_purchase_sum, funnel_purchase_sum_total, '.2f')
cmp('Сумма выкупов (реализация), ₽', pdf_purchase_sum, det_realized, '.2f')

w('')
w('--- БЛОК 2: ФИНАНСЫ ---')
cmp('Выручка от продаж, ₽', pdf_revenue, det_realized, '.2f')
cmp('Комиссия WB (ВВ без НДС), ₽', pdf_commission, det_voznag, '.2f')
cmp('Комиссия WB (итого ВВ), ₽', pdf_commission, det_vv, '.2f')
cmp('Логистика, ₽', pdf_logistics, det_delivery, '.2f')
cmp('Хранение, ₽', pdf_storage, 0, '.2f')
cmp('Эквайринг, ₽', pdf_acquiring, det_acquiring, '.2f')
w(f'{"Себестоимость, ₽":<35} {pdf_cogs:<18.2f} {"н/д":<18} —')
w(f'{"Чистая прибыль, ₽":<35} {pdf_profit:<18.2f} {"н/д":<18} —')
w(f'{"Маржа, %":<35} {pdf_margin:<18.1f} {"н/д":<18} —')

w('')
w('--- БЛОК 3: SKU-УРОВЕНЬ (выручка) ---')
sku_pdf_rev = {333615320: pdf_sku333_rev, 452102417: pdf_sku452_rev}
for sku in [333615320, 452102417]:
    pv = sku_pdf_rev[sku]
    wv = sku_detail.get(sku, {}).get('realized', 0)
    d = wv - pv
    mark = 'OK' if abs(d) < 0.01 else 'DIFF'
    w(f'  SKU {sku}: PDF={pv:.2f}  WB={wv:.2f}  Delta={d:+.2f}  {mark}')

w('')
w('--- БЛОК 4: ВОРОНКА ПО SKU ---')
hdr = '  {:<12} {:<12} {:<15} {:<12} {:<15} {}'.format('SKU', 'Zakazy PDF', 'Zakazy voronka', 'Summa PDF', 'Summa voronka', 'Vy kupy voronka')
w(hdr)
w('  ' + '-' * 75)
for sku in [333615320, 590614192, 551253854, 898642228, 452102417]:
    f = sku_funnel.get(sku, {})
    line = '  {:<12} {:<12} {:<15} {:<12} {:<15} {}'.format(
        sku, '-', f.get('orders', '-'), '-', f.get('order_sum', '-'), f.get('purchases', '-'))
    w(line)

w('')
w('--- БЛОК 5: ОСТАТКИ ---')
w(f'  PDF: {pdf_stock} шт (свободные остатки)')
w(f'  WB файл: {stock_on_hand:.0f} шт (на складах) + {stock_in_transit:.0f} (в пути) + {stock_returns:.0f} (возвраты) = {stock_total_wb:.0f} шт всего')
w(f'  Разница (только на складах): {stock_on_hand - pdf_stock:+.0f} шт')

w('')
w('--- БЛОК 6: РЕКЛАМА (только в PDF, WB не раскрывает) ---')
w(f'  Расход: {pdf_ads} ₽  |  Показы: 523  |  Клики: 56  |  CTR: 10.71%')
w(f'  CPC: 4.04 ₽  |  CPM: 432.75 ₽  |  ROAS: 0.00x  |  CPO: 22.63 ₽')
w(f'  Заказы из рекламы: 10  |  Выручка из рекламы: 0 ₽  |  Прибыль от рекламы: -226.33 ₽')

w('')
w('=' * 80)
w('  ИТОГОВЫЕ РАСХОЖДЕНИЯ')
w('=' * 80)
w(f'  1. Сумма выкупов: PDF 2 040,20 ₽ vs WB воронка 2 040,20 ₽ → СОВПАДАЕТ')
w(f'  2. Сумма выкупов: PDF 2 040,20 ₽ vs WB детализация 1 210 ₽ → РАСХОЖДЕНИЕ -830,20 ₽')
w(f'  3. SKU 333615320: PDF выручка 620 ₽ vs WB 350 ₽ → РАСХОЖДЕНИЕ -270 ₽')
w(f'  4. SKU 452102417: PDF выручка 1 420,20 ₽ vs WB 860 ₽ → РАСХОЖДЕНИЕ -560,20 ₽')
w(f'  5. SKU 452102417: в воронке 0 заказов, в WB детализации 2 продажи → НЕСОВПАДЕНИЕ')
w(f'  6. Хранение: PDF -28,84 ₽ vs WB детализация 0 ₽ → PDF считает отдельно')
w(f'  7. Остатки: PDF 107 шт vs WB на складах {stock_on_hand:.0f} шт → РАСХОЖДЕНИЕ {stock_on_hand - pdf_stock:+.0f} шт')
w(f'  8. WB комиссия (ВВ итого): PDF -162,08 ₽ vs WB -183,09 ₽ → РАСХОЖДЕНИЕ -21,01 ₽ (НДС)')

print('\n'.join(out))
