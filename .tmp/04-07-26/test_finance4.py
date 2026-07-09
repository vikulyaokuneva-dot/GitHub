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
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type')}")
resp = r.json()
print(f"Type: {type(resp)}")
if isinstance(resp, dict):
    print(f"Keys: {list(resp.keys())[:10]}")
    data = resp.get("data", resp.get("rows", resp.get("items", [])))
    print(f"Data type: {type(data)}, len: {len(data) if isinstance(data, list) else 'N/A'}")
    if isinstance(data, list) and data:
        print(f"First row keys: {list(data[0].keys())[:15]}")
        print(f"First row: {json.dumps(data[0], ensure_ascii=False)[:300]}")
elif isinstance(resp, list):
    print(f"Rows: {len(resp)}")
    if resp:
        print(f"First row keys: {list(resp[0].keys())[:15]}")
