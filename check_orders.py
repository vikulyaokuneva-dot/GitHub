import json
from pathlib import Path

# Find the latest job.json
cabinet_path = Path('cabinets/seller_001')
jobs = list(cabinet_path.glob('**/job.json'))
if jobs:
    latest_job = sorted(jobs)[-1]
    print(f'Latest job file: {latest_job}')
    print()
    
    with open(latest_job) as f:
        job = json.load(f)
    
    # Print key fields related to orders
    daily_kpi = job.get('daily_kpi', {})
    print('Daily KPI Orders Data:')
    print(f'  daily_orders_count: {daily_kpi.get("daily_orders_count")}')
    print(f'  daily_buyouts_count: {daily_kpi.get("daily_buyouts_count")}')
    print(f'  orders_count_confirmed: {daily_kpi.get("orders_count_confirmed")}')
    print(f'  quantity_fallback_blocked: {daily_kpi.get("quantity_fallback_blocked")}')
    print(f'  data_source_orders_count: {daily_kpi.get("data_source_orders_count")}')
    print(f'  supplier_orders_count_raw: {daily_kpi.get("supplier_orders_count_raw")}')
    print(f'  sku_activity_orders_hint: {daily_kpi.get("sku_activity_orders_hint")}')
