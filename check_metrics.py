import json
from pathlib import Path

metrics_file = Path('cabinets/seller_001/history/daily/2026-04-01/metrics.json')
with open(metrics_file) as f:
    metrics = json.load(f)

print('Portfolio Summary (2026-04-01):')
print(f'Total SKUs: {len(metrics.get("sku_metrics", []))}')

total_orders = sum(int(m.get('orders', 0)) for m in metrics.get('sku_metrics', []))
total_revenue = sum(float(m.get('revenue', 0)) for m in metrics.get('sku_metrics', []))
total_profit = sum(float(m.get('profit', 0)) for m in metrics.get('sku_metrics', []))

print(f'Total Orders: {total_orders}')
print(f'Total Revenue: {total_revenue:.2f}')
print(f'Total Profit: {total_profit:.2f}')

# Check totals structure
if 'totals' in metrics:
    print('\nPortfolio Totals:')
    for k, v in metrics['totals'].items():
        print(f'  {k}: {v}')
