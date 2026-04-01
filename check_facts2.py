import json
from pathlib import Path

facts_file = Path('cabinets/seller_001/history/daily/2026-04-01/facts.json')
with open(facts_file) as f:
    facts = json.load(f)

print('Daily Orders Info:')
print(f'  daily_orders_count: {facts.get("daily_orders_count")}')
print(f'  daily_orders_amount: {facts.get("daily_orders_amount")}')
print(f'  daily_buyouts_count: {facts.get("daily_buyouts_count")}')
print(f'  daily_buyouts_amount: {facts.get("daily_buyouts_amount")}')
