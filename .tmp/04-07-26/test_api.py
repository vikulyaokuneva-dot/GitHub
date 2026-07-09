import os, sys, json
sys.path.insert(0, r'D:\WB\Бот ИИ менеджер\GitHub')
os.chdir(r'D:\WB\Бот ИИ менеджер\GitHub')

from dotenv import load_dotenv
load_dotenv(r'D:\WB\Бот ИИ менеджер\GitHub\.env')

from wb_api_core.client import WBApiClient

client = WBApiClient()
target_date = "2026-07-04"

print("=" * 80)
print("  ТЕСТ 1: SALES FUNNEL API — показы карточки")
print("=" * 80)

# 1. Без nmIds (как сейчас)
print("\n--- Запрос БЕЗ nmIds (текущий режим) ---")
r1 = client.request_json(
    endpoint_name="funnel_no_filter",
    path="/api/analytics/v3/sales-funnel/products",
    method="POST",
    json_body={
        "selectedPeriod": {"start": target_date, "end": target_date},
        "nmIds": [],
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "skipDeletedNm": True,
        "limit": 100,
        "offset": 0,
    },
    base_url=client.analytics_base_url,
)
print(f"  Success: {r1.get('success')}")
print(f"  Status: {r1.get('status_code')}")
payload1 = r1.get("payload", {})
products1 = []
if isinstance(payload1, dict):
    data = payload1.get("data", {})
    if isinstance(data, dict):
        products1 = data.get("products", [])
print(f"  Products count: {len(products1)}")
for p in products1[:3]:
    stat = p.get("statistic", {}).get("selected", {}) if isinstance(p.get("statistic"), dict) else {}
    nm = p.get("product", {}).get("nmId") if isinstance(p.get("product"), dict) else p.get("nmId")
    views = stat.get("views") or stat.get("openCount")
    impressions = stat.get("impressions") or stat.get("shows") or stat.get("showCount")
    print(f"  nmId={nm}: views={views}, impressions={impressions}, stat_keys={list(stat.keys())[:8]}")

# 2. С конкретными nmIds
known_nmid = [333615320, 452102417, 590614192, 898642228, 551253854]
print(f"\n--- Запрос С nmIds={known_nmid} ---")
r2 = client.request_json(
    endpoint_name="funnel_with_nmids",
    path="/api/analytics/v3/sales-funnel/products",
    method="POST",
    json_body={
        "selectedPeriod": {"start": target_date, "end": target_date},
        "nmIds": known_nmid,
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "skipDeletedNm": True,
        "limit": 100,
        "offset": 0,
    },
    base_url=client.analytics_base_url,
)
print(f"  Success: {r2.get('success')}")
print(f"  Status: {r2.get('status_code')}")
payload2 = r2.get("payload", {})
products2 = []
if isinstance(payload2, dict):
    data = payload2.get("data", {})
    if isinstance(data, dict):
        products2 = data.get("products", [])
print(f"  Products count: {len(products2)}")
for p in products2[:5]:
    stat = p.get("statistic", {}).get("selected", {}) if isinstance(p.get("statistic"), dict) else {}
    prod = p.get("product", {}) if isinstance(p.get("product"), dict) else p
    nm = prod.get("nmId") or p.get("nmId")
    title = prod.get("title", "")[:40]
    views = stat.get("views") or stat.get("openCount")
    impressions = stat.get("impressions") or stat.get("shows") or stat.get("showCount")
    orders = stat.get("orders") or stat.get("orderCount")
    buys = stat.get("buys") or stat.get("buyoutCount")
    print(f"  nmId={nm} ({title}): views={views}, imp={impressions}, orders={orders}, buys={buys}")
    if stat:
        print(f"    all stat keys: {list(stat.keys())}")

# 3. С ProdnmIds (другой формат)
print(f"\n--- Запрос С prodnmIds ---")
r3 = client.request_json(
    endpoint_name="funnel_prodnmids",
    path="/api/analytics/v3/sales-funnel/products",
    method="POST",
    json_body={
        "selectedPeriod": {"start": target_date, "end": target_date},
        "prodnmIds": known_nmid,
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "skipDeletedNm": True,
        "limit": 100,
        "offset": 0,
    },
    base_url=client.analytics_base_url,
)
print(f"  Success: {r3.get('success')}")
print(f"  Status: {r3.get('status_code')}")
payload3 = r3.get("payload", {})
products3 = []
if isinstance(payload3, dict):
    data = payload3.get("data", {})
    if isinstance(data, dict):
        products3 = data.get("products", [])
print(f"  Products count: {len(products3)}")
for p in products3[:5]:
    stat = p.get("statistic", {}).get("selected", {}) if isinstance(p.get("statistic"), dict) else {}
    prod = p.get("product", {}) if isinstance(p.get("product"), dict) else p
    nm = prod.get("nmId") or p.get("nmId")
    views = stat.get("views") or stat.get("openCount")
    impressions = stat.get("impressions") or stat.get("shows") or stat.get("showCount")
    print(f"  nmId={nm}: views={views}, imp={impressions}")


print("\n\n" + "=" * 80)
print("  ТЕСТ 2: FINANCE API — логистика")
print("=" * 80)

# Finance detailed
r_finance = client.request_json(
    endpoint_name="finance_test",
    path="/api/finance/v1/sales-reports/detailed",
    method="POST",
    json_body={
        "dateFrom": target_date,
        "dateTo": target_date,
        "period": "daily",
        "limit": 100,
        "rrdId": 0,
    },
    base_url=client.finance_base_url,
)
print(f"\n  Success: {r_finance.get('success')}")
print(f"  Status: {r_finance.get('status_code')}")
fp = r_finance.get("payload", [])
if isinstance(fp, list):
    print(f"  Rows: {len(fp)}")
    for row in fp[:3]:
        keys_of_interest = ["nmId", "supplierArticle", "logistics", "delivery_rub", "logistics_amount",
                            "storage", "penalty", "ppvz_for_pay", "retailAmount"]
        vals = {k: row.get(k) for k in keys_of_interest if row.get(k) is not None}
        print(f"  Row: {vals}")
elif isinstance(fp, dict):
    print(f"  Payload keys: {list(fp.keys())[:10]}")
    data = fp.get("data", fp.get("rows", fp.get("items", [])))
    if isinstance(data, list):
        print(f"  Data rows: {len(data)}")
        for row in data[:3]:
            keys_of_interest = ["nmId", "logistics", "delivery_rub", "logistics_amount", "storage", "ppvz_for_pay"]
            vals = {k: row.get(k) for k in keys_of_interest if row.get(k) is not None}
            print(f"  Row: {vals}")
else:
    print(f"  Payload type: {type(fp)}, preview: {str(fp)[:300]}")

# Check if error
if not r_finance.get("success"):
    print(f"  Error: {r_finance.get('error_text', '')[:300]}")
