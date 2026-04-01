import json
from pathlib import Path

facts_file = Path('cabinets/seller_001/history/daily/2026-04-01/facts.json')
if facts_file.exists():
    with open(facts_file) as f:
        facts = json.load(f)
    
    print('Financial Facts (2026-04-01):')
    if 'financial_summary' in facts:
        for k, v in list(facts['financial_summary'].items())[:30]:
            print(f'  {k}: {v}')
    else:
        print('No financial_summary in facts')
        print('Available keys:', list(facts.keys())[:10])
else:
    print('Facts file not found')
