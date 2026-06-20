"""Сверка данных ТОП-5 SKU с данными из ежедневной динамики продаж (sales_dynamic)."""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from audit.audit_loader import find_sales_dynamic_file, parse_sales_dynamic_file

# 1. Загрузить facts
with open("cabinets/seller_001/artifacts/facts_audit_2026-06-19.json", "r", encoding="utf-8") as f:
    facts = json.load(f)

# 2. Данные ТОП-5 SKU
top5 = facts.get("top5_sku_unit_economics", {})
top5_items = top5.get("items", [])

print("=" * 80)
print("ДАННЫЕ ТОП-5 SKU (из facts JSON)")
print("=" * 80)
for item in top5_items:
    sku = item.get("sku")
    orders = item.get("orders")
    buyouts = item.get("buyouts")
    revenue = item.get("revenue")
    profit = item.get("profit")
    print(f"  SKU={sku}: orders={orders}, buyouts={buyouts}, revenue={revenue}, profit={profit}")

# 3. Данные sales_dynamic (по артикулам)
sd_path = find_sales_dynamic_file("local_audit/input")
sd = parse_sales_dynamic_file(sd_path) if sd_path else {}

print(f"\n{'=' * 80}")
print("ДАННЫЕ SALES_DYNAMIC (общие)")
print(f"{'=' * 80}")
print(f"  total_buyouts={sd.get('buyouts')}, total_orders={sd.get('orders')}, total_payout={sd.get('payout')}")

by_article = sd.get("by_article", {})
print(f"\n  by_article ({len(by_article)} артикулов):")
for article, data in by_article.items():
    print(f"    {article}: buyouts={data.get('buyouts')}, orders={data.get('orders')}, payout={data.get('payout')}")

# 4. Сопоставить артикулы с SKU через orders_rows
from audit.audit_loader import parse_orders_file_with_diagnostics, scan_input_files, group_detected_files

detected = scan_input_files("local_audit/input")
grouped = group_detected_files(detected)
orders_files = [x.path for x in (grouped.get("orders") or [])]

if orders_files:
    from audit.audit_facts_builder import _build_article_sku_mapping
    orders_rows, _ = parse_orders_file_with_diagnostics(orders_files[0])
    article_to_sku = _build_article_sku_mapping(orders_rows)
    
    print(f"\n{'=' * 80}")
    print("СОПОСТАВЛЕНИЕ АРТИКУЛОВ С SKU (из orders_rows)")
    print(f"{'=' * 80}")
    for art, sku_id in sorted(article_to_sku.items()):
        sd_data = by_article.get(art, {})
        print(f"  {art} -> SKU {sku_id}")
        print(f"    sales_dynamic: buyouts={sd_data.get('buyouts', 'N/A')}, orders={sd_data.get('orders', 'N/A')}, payout={sd_data.get('payout', 'N/A')}")
        
        # Найти соответствующий SKU в ТОП-5
        for item in top5_items:
            if item.get("sku") == sku_id:
                print(f"    ТОП-5:     buyouts={item.get('buyouts')}, orders={item.get('orders')}, revenue={item.get('revenue')}")
                
                # Проверка совпадения
                sd_buyouts = sd_data.get("buyouts", 0)
                top5_buyouts = item.get("buyouts", 0)
                sd_orders = sd_data.get("orders", 0)
                top5_orders = item.get("orders", 0)
                
                if sd_buyouts != top5_buyouts:
                    print(f"    [X] РАСХОЖДЕНИЕ: buyouts sd={sd_buyouts} != top5={top5_buyouts}")
                else:
                    print(f"    [OK] buyouts совпадают: {sd_buyouts}")
                    
                if sd_orders != top5_orders:
                    print(f"    [X] РАСХОЖДЕНИЕ: orders sd={sd_orders} != top5={top5_orders}")
                else:
                    print(f"    [OK] orders совпадают: {sd_orders}")
                break
        else:
            print(f"    SKU {sku_id} не найден в ТОП-5")
else:
    print("\n[!] orders файлы не найдены")

# 5. Сверка общих сумм выкупов
print(f"\n{'=' * 80}")
print("СВЕРКА ОБЩИХ СУММ")
print(f"{'=' * 80}")
sd_total_buyouts = sd.get("buyouts", 0)
sd_total_payout = sd.get("payout", 0)
sd_total_orders = sd.get("orders", 0)

# Сумма buyouts по артикулам из ТОП-5
top5_total_buyouts = sum(item.get("buyouts", 0) for item in top5_items)
top5_total_orders = sum(item.get("orders", 0) for item in top5_items)
top5_total_revenue = sum(item.get("revenue", 0) for item in top5_items)

print(f"  sales_dynamic: buyouts={sd_total_buyouts}, orders={sd_total_orders}, payout={sd_total_payout}")
print(f"  ТОП-5 (только 5 SKU): buyouts={top5_total_buyouts}, orders={top5_total_orders}, revenue={top5_total_revenue}")

# Сверка по каждому SKU из sales_dynamic с sku_profit
sku_profit = facts.get("sku_profit", [])
print(f"\n{'=' * 80}")
print("СВЕРКА ПО ВСЕМ SKU: sales_dynamic vs sku_profit")
print(f"{'=' * 80}")
sku_by_id = {row.get("sku"): row for row in sku_profit}
for art, sd_data in by_article.items():
    # Найти SKU по артикулу
    sku_id = article_to_sku.get(art)
    if sku_id and sku_id in sku_by_id:
        sp = sku_by_id[sku_id]
        print(f"  {art} (SKU {sku_id}):")
        print(f"    sd:      buyouts={sd_data.get('buyouts')}, orders={sd_data.get('orders')}, payout={sd_data.get('payout')}")
        print(f"    sku_p:   buyouts={sp.get('buyouts')}, orders={sp.get('orders')}, revenue={sp.get('revenue')}")
        
        sd_b = sd_data.get("buyouts", 0)
        sp_b = sp.get("buyouts", 0)
        sd_o = sd_data.get("orders", 0)
        sp_o = sp.get("orders", 0)
        
        if sd_b != sp_b:
            print(f"    ❌ buyouts: sd={sd_b} != sku_p={sp_b}")
        else:
            print(f"    ✅ buyouts совпадают: {sd_b}")
        if sd_o != sp_o:
            print(f"    ❌ orders: sd={sd_o} != sku_p={sp_o}")
        else:
            print(f"    ✅ orders совпадают: {sd_o}")
    else:
        print(f"  {art}: SKU не найден в sku_profit (или не сопоставлен)")
