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
data = r.json()
rows = data if isinstance(data, list) else data.get("data", data.get("rows", []))

# Show ALL keys from first row
if rows:
    print("=== ALL KEYS in first row ===")
    for k, v in sorted(rows[0].items()):
        print(f"  {k}: {v}")

    # Find rows with non-zero logistics/delivery
    print("\n=== Rows with delivery/logistics ===")
    for row in rows:
        logist = row.get("logistics") or row.get("delivery_rub") or row.get("deliveryAmount") or row.get("logistics_amount")
        delivery_qty = row.get("delivery_qty") or row.get("deliveryCount")
        if logist and float(str(logist).replace(" ", "").replace(",", ".") or 0) != 0:
            print(f"  nmId={row.get('nmId')}: logistics={logist}, delivery_qty={delivery_qty}")
        if delivery_qty and float(str(delivery_qty).replace(" ", "").replace(",", ".") or 0) != 0:
            print(f"  nmId={row.get('nmId')}: delivery_qty={delivery_qty}")

    # Check for ANY field with "deliver" or "logist" in name
    print("\n=== Fields containing 'deliver' or 'logist' ===")
    for k in sorted(rows[0].keys()):
        kl = k.lower()
        if "deliver" in kl or "logist" in kl or "storage" in kl or "penalt" in kl or "fines" in kl or "acqui" in kl or "deduct" in kl:
            vals = [row.get(k) for row in rows if row.get(k) is not None and str(row.get(k)).strip() not in ("0", "0.0", "")]
            if vals:
                print(f"  {k}: non-zero values = {vals[:5]}")
            else:
                print(f"  {k}: all zero/empty")
