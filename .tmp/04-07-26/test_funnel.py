import os, sys, json
sys.path.insert(0, r'D:\WB\Бот ИИ менеджер\GitHub')
os.chdir(r'D:\WB\Бот ИИ менеджер\GitHub')
from dotenv import load_dotenv
load_dotenv(r'D:\WB\Бот ИИ менеджер\GitHub\.env')

import requests
token = os.environ.get("WB_API_TOKEN", "")
base = "https://seller-analytics-api.wildberries.ru"
path = "/api/analytics/v3/sales-funnel/products"
headers = {"Authorization": token, "Content-Type": "application/json"}

target = "2026-07-04"

# Test 1: without nmIds
print("Test 1: funnel WITHOUT nmIds")
body1 = {
    "selectedPeriod": {"start": target, "end": target},
    "nmIds": [], "brandNames": [], "subjectIds": [], "tagIds": [],
    "skipDeletedNm": True, "limit": 10, "offset": 0,
}
try:
    r = requests.post(f"{base}{path}", headers=headers, json=body1, timeout=30)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        products = data.get("data", {}).get("products", []) if isinstance(data, dict) else []
        print(f"  Products: {len(products)}")
        for p in products[:3]:
            stat = p.get("statistic", {}).get("selected", {}) if isinstance(p.get("statistic"), dict) else {}
            prod = p.get("product", {}) if isinstance(p.get("product"), dict) else {}
            nm = prod.get("nmId", "?")
            print(f"    nmId={nm}: views={stat.get('views')}, imp={stat.get('impressions')}, keys={list(stat.keys())[:6]}")
    else:
        print(f"  Body: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: with specific nmIds
print("\nTest 2: funnel WITH nmIds=[333615320,452102417,898642228]")
body2 = {
    "selectedPeriod": {"start": target, "end": target},
    "nmIds": [333615320, 452102417, 898642228],
    "brandNames": [], "subjectIds": [], "tagIds": [],
    "skipDeletedNm": True, "limit": 10, "offset": 0,
}
try:
    r = requests.post(f"{base}{path}", headers=headers, json=body2, timeout=30)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        products = data.get("data", {}).get("products", []) if isinstance(data, dict) else []
        print(f"  Products: {len(products)}")
        for p in products[:5]:
            stat = p.get("statistic", {}).get("selected", {}) if isinstance(p.get("statistic"), dict) else {}
            prod = p.get("product", {}) if isinstance(p.get("product"), dict) else {}
            nm = prod.get("nmId", "?")
            title = str(prod.get("title", ""))[:35]
            print(f"    nmId={nm} ({title}): views={stat.get('views')}, imp={stat.get('impressions')}, orders={stat.get('orders')}")
    else:
        print(f"  Body: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")
