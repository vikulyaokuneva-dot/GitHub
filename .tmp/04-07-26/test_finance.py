import os, sys, json
sys.path.insert(0, r'D:\WB\Бот ИИ менеджер\GitHub')
os.chdir(r'D:\WB\Бот ИИ менеджер\GitHub')
from dotenv import load_dotenv
load_dotenv(r'D:\WB\Бот ИИ менеджер\GitHub\.env')

import requests, time
token = os.environ.get("WB_API_TOKEN", "")

# Finance API (different base URL, maybe different rate limit)
base = "https://finance-api.wildberries.ru"
path = "/api/finance/v1/sales-reports/detailed"
headers = {"Authorization": token, "Content-Type": "application/json"}

target = "2026-07-04"

print("Test: Finance Detailed API")
body = {
    "dateFrom": target,
    "dateTo": target,
    "period": "daily",
    "limit": 100,
    "rrdId": 0,
}
try:
    r = requests.post(f"{base}{path}", headers=headers, json=body, timeout=30)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("data", data.get("rows", data.get("items", [])))
        else:
            rows = []
        print(f"  Rows: {len(rows) if isinstance(rows, list) else type(rows)}")
        if isinstance(rows, list):
            for row in rows[:5]:
                keys = ["nmId", "supplierArticle", "logistics", "delivery_rub", "logistics_amount",
                        "storage", "penalty", "ppvz_for_pay", "retailAmount", "forPay",
                        "saleID", "date", "quantity"]
                vals = {k: row.get(k) for k in keys if row.get(k) is not None}
                print(f"  Row: {json.dumps(vals, ensure_ascii=False)[:200]}")
    elif r.status_code == 429:
        print(f"  Rate limited. Headers: {dict(r.headers)}")
    else:
        print(f"  Body: {r.text[:400]}")
except Exception as e:
    print(f"  Error: {e}")
