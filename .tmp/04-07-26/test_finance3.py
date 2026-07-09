import os, sys, json
sys.path.insert(0, r'D:\WB\Бот ИИ менеджер\GitHub')
os.chdir(r'D:\WB\Бот ИИ менеджер\GitHub')
from dotenv import load_dotenv
load_dotenv(r'D:\WB\Бот ИИ менеджер\GitHub\.env')

import requests
token = os.environ.get("WB_API_TOKEN", "")
base = "https://finance-api.wildberries.ru"
path = "/api/finance/v1/sales-reports/detailed"
headers = {"Authorization": token, "Content-Type": "application/json"}

body = {
    "dateFrom": "2026-07-04",
    "dateTo": "2026-07-04",
    "period": "daily",
    "limit": 100,
    "rrdId": 0,
}
r = requests.post(f"{base}{path}", headers=headers, json=body, timeout=30)
resp = r.json()
rows = resp if isinstance(resp, list) else resp.get("data", [])

def sf(v):
    try: return float(str(v).replace(" ","").replace(",",".") or 0)
    except: return 0.0

print("=" * 80)
print("  FINANCE API: полный разбор логистики и комиссий")
print("=" * 80)

# Group by sellerOperName
from collections import defaultdict
by_op = defaultdict(lambda: {"count": 0, "deliveryService": 0, "rebillLogisticCost": 0,
                             "paidStorage": 0, "acquiringFee": 0, "ppvzSalesCommission": 0,
                             "forPay": 0, "retailAmount": 0, "quantity": 0, "penalty": 0, "deduction": 0})
for row in rows:
    op = row.get("sellerOperName", "unknown")
    by_op[op]["count"] += 1
    by_op[op]["deliveryService"] += sf(row.get("deliveryService"))
    by_op[op]["rebillLogisticCost"] += sf(row.get("rebillLogisticCost"))
    by_op[op]["paidStorage"] += sf(row.get("paidStorage"))
    by_op[op]["acquiringFee"] += sf(row.get("acquiringFee"))
    by_op[op]["ppvzSalesCommission"] += sf(row.get("ppvzSalesCommission"))
    by_op[op]["forPay"] += sf(row.get("forPay"))
    by_op[op]["retailAmount"] += sf(row.get("retailAmount"))
    by_op[op]["quantity"] += sf(row.get("quantity"))
    by_op[op]["penalty"] += sf(row.get("penalty"))
    by_op[op]["deduction"] += sf(row.get("deduction"))

print(f"\n{'Операция':<35} {'Строк':<7} {'Доставка':<12} {'Ребиллинг':<12} {'Хранение':<10} {'Эквайринг':<12} {'Комиссия':<12} {'К переч.':<12}")
print("-" * 115)
totals = {k: 0 for k in ["deliveryService", "rebillLogisticCost", "paidStorage", "acquiringFee", "ppvzSalesCommission", "forPay"]}
for op, d in sorted(by_op.items()):
    print(f"{op:<35} {d['count']:<7} {d['deliveryService']:<12.2f} {d['rebillLogisticCost']:<12.2f} {d['paidStorage']:<10.2f} {d['acquiringFee']:<12.2f} {d['ppvzSalesCommission']:<12.2f} {d['forPay']:<12.2f}")
    for k in totals:
        totals[k] += d[k]
print("-" * 115)
print(f"{'ИТОГО':<35} {len(rows):<7} {totals['deliveryService']:<12.2f} {totals['rebillLogisticCost']:<12.2f} {totals['paidStorage']:<10.2f} {totals['acquiringFee']:<12.2f} {totals['ppvzSalesCommission']:<12.2f} {totals['forPay']:<12.2f}")

# Per-SKU breakdown (only Продажа)
print(f"\n--- По SKU (только продажи) ---")
sku_data = defaultdict(lambda: {"deliveryService": 0, "rebillLogisticCost": 0, "paidStorage": 0,
                                "acquiringFee": 0, "ppvzSalesCommission": 0, "forPay": 0, "retailAmount": 0, "qty": 0})
for row in rows:
    if row.get("sellerOperName") == "Логистика":
        continue
    nm = row.get("nmId", 0)
    sku_data[nm]["deliveryService"] += sf(row.get("deliveryService"))
    sku_data[nm]["rebillLogisticCost"] += sf(row.get("rebillLogisticCost"))
    sku_data[nm]["paidStorage"] += sf(row.get("paidStorage"))
    sku_data[nm]["acquiringFee"] += sf(row.get("acquiringFee"))
    sku_data[nm]["ppvzSalesCommission"] += sf(row.get("ppvzSalesCommission"))
    sku_data[nm]["forPay"] += sf(row.get("forPay"))
    sku_data[nm]["retailAmount"] += sf(row.get("retailAmount"))
    sku_data[nm]["qty"] += sf(row.get("quantity"))

print(f"  {'SKU':<12} {'Кол-во':<8} {'Выручка':<12} {'Доставка':<12} {'Ребиллинг':<12} {'Хранение':<10} {'Эквайринг':<12} {'Комиссия':<12} {'К переч.':<12}")
print(f"  {'-'*105}")
for nm, d in sorted(sku_data.items()):
    if d["qty"] > 0 or d["retailAmount"] > 0:
        print(f"  {nm:<12} {d['qty']:<8.0f} {d['retailAmount']:<12.2f} {d['deliveryService']:<12.2f} {d['rebillLogisticCost']:<12.2f} {d['paidStorage']:<10.2f} {d['acquiringFee']:<12.2f} {d['ppvzSalesCommission']:<12.2f} {d['forPay']:<12.2f}")

print(f"\n--- PDF vs Finance API ---")
print(f"  {'Показатель':<30} {'PDF':<15} {'Finance API':<15} {'Разница'}")
print(f"  {'-'*75}")
print(f"  {'Логистика (доставка)':<30} {'0.00':<15} {totals['deliveryService']:<15.2f} {totals['deliveryService']:+.2f}")
print(f"  {'Ребиллинг логистики':<30} {'н/д':<15} {totals['rebillLogisticCost']:<15.2f}")
print(f"  {'Хранение':<30} {'-28.84':<15} {totals['paidStorage']:<15.2f} {totals['paidStorage'] - 28.84:+.2f}")
print(f"  {'Эквайринг':<30} {'-48.40':<15} {totals['acquiringFee']:<15.2f} {totals['acquiringFee'] - 48.40:+.2f}")
print(f"  {'Комиссия WB':<30} {'-162.08':<15} {totals['ppvzSalesCommission']:<15.2f} {totals['ppvzSalesCommission'] - 162.08:+.2f}")
print(f"  {'К перечислению':<30} {'н/д':<15} {totals['forPay']:<15.2f}")
