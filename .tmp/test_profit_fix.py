import sys, json
sys.path.insert(0, r'D:\WB\Бот ИИ менеджер\GitHub')

from report_v2.builders.report_payload_builder import build_report_payload_v2

snapshot = json.load(open(r'D:\WB\Бот ИИ менеджер\GitHub\.tmp\wb-report-seller_001 (75)\wb_api_core\2026-07-01\snapshot.json', encoding='utf-8-sig'))

payload = build_report_payload_v2(snapshot)
profit = payload.get('profit_section', {})
print('=== Profit Section (FIXED) ===')
for row in profit.get('rows', []):
    print(f"  {row['label']}: {row['value']}")
print(f"  net_profit: {profit.get('net_profit')}")
print(f"  margin: {profit.get('margin')}%")
