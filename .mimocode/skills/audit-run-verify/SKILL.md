---
name: audit-run-verify
description: >
  Run the WB audit pipeline from local_audit/input, verify output report sections
  (KPI, TOP-5, finance, efficiency, sales_dynamic), and iterate on bugs.
  Use when the user asks to generate, regenerate, test, or verify an audit report.
---

# Audit Run & Verify

Workflow for running the WB audit pipeline and systematically verifying the output.
Replaces the ad-hoc "run audit → read md → check section → fix → repeat" loop.

## When to use

- User asks to generate or regenerate an audit report
- User asks to verify audit output data accuracy
- Debugging audit report bugs (wrong KPI, missing sections, data mismatches)
- After code changes to `audit/` — regression testing

## Prerequisites

- Input files in `local_audit/input/` (finance/, funnel/, ads/, stocks/, sales_dynamic/, logist/)
- Python 3.12 with project dependencies installed
- Working directory = project root (`D:\WB\Бот ИИ менеджер\GitHub`)

## Step 1 — Run the audit

Use the `run-audit` command or run directly:

```python
import sys; sys.stdout.reconfigure(encoding='utf-8')
from audit.run_audit import run_audit_mode
run_audit_mode(
    input_dir='local_audit/input',
    out_dir='local_audit/output',
    source='wb',
    period='<YYYY-MM-DD>_<YYYY-MM-DD>',  # or omit for auto-detect
    send_email=False
)
```

**Key params:**
- `period` — format `YYYY-MM-DD_YYYY-MM-DD`, e.g. `2026-06-08_2026-06-14`. If omitted, auto-detected from input files.
- `send_email` — set `True` only when explicitly requested.
- Output goes to `local_audit/output/audit_<date>.md` + `audit_<date>.pdf`.

**Common issues:**
- `UnicodeEncodeError` → always add `sys.stdout.reconfigure(encoding='utf-8')` first
- `ModuleNotFoundError` → ensure `PYTHONPATH=.` or run from project root
- `FileNotFoundError` → check input files exist in correct subfolders

## Step 2 — Read and verify output

After running, read `local_audit/output/audit_<date>.md` and check sections systematically.

### Verification checklist (check each in order):

1. **KPI section** (lines ~86-95):
   - `Заказы:` matches expected count
   - `Выкупы:` matches expected count
   - `CR к заказу:` is `(выкупы/заказы)*100` — can exceed 100% (normal for WB)
   - `Выручка:` matches finance total

2. **Finance section** (section 2):
   - `Валовая прибыль:` present and positive
   - `Комиссия WB:` negative (cost)
   - `Логистика:` present
   - `Возвраты (от拒绝ы):` — shows count and percentage
   - If `DRR=0` → text must say "реклама не включена" (NOT "реклама эффективна")

3. **Funnel section** (section 3):
   - `Заказали товаров, шт:` matches orders count
   - `Конверсия в корзину:` present

4. **TOP-5 SKU** (section ~7):
   - Each SKU shows `Заказы:` / `Выкупы:` / `Выручка:`
   - No duplicate conclusions between items
   - If ads disabled for SKU → conclusion mentions margin/overpay, NOT "Товар прибыльный" generically
   - ROI present only when full COGS coverage available

5. **Efficiency table** (section "Эффективность по SKU"):
   - All columns populated: Заказы, Выкупы, Выручка, Себестоимость, Прибыль, ROI, Остатки
   - `Остатки (шт)` comes from stocks data
   - ROI values consistent with TOP-5 section for same SKU

6. **Sales dynamic override** (if sales_dynamic file present):
   - Buyouts should be from sales_dynamic (e.g. 63 not 37)
   - Revenue should match sales_dynamic total
   - Per-SKU buyouts/orders overridden correctly

7. **Consistency checks:**
   - KPI `Заказы` = Funnel `Заказали товаров`
   - Finance `Выручка` = TOP-5 sum of `Выручка`
   - `Валовая отдача` label used (NOT "оценка прибыли")
   - Executive summary matches detailed finance section
   - English text absent (no "Executive Summary", "What to do")

### Quick verification script pattern:

```python
import sys; sys.stdout.reconfigure(encoding='utf-8')
with open('local_audit/output/audit_<date>.md', encoding='utf-8') as f:
    content = f.read()

# Check specific values
checks = {
    'Заказы=N': 'Заказы: **N**' in content,  # replace N
    'DRR=0 text': 'реклама не включена' in content,  # if no ads
    'No English': 'Executive Summary' not in content,
}
for name, ok in checks.items():
    print(f"{'✓' if ok else '✗'} {name}")
```

## Step 3 — Inspect intermediate data (when debugging)

Read facts JSON for data flow debugging:

```python
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json

f = json.load(open('local_audit/output/facts_audit_<date>.json', 'r', encoding='utf-8'))

# Financial summary
fs = f.get('financial_summary', {})
print(f"revenue: {fs.get('total_revenue')}")
print(f"profit: {fs.get('gross_profit')}")

# Per-SKU financials
sf = f.get('sku_financials', {})
for sku, data in list(sf.items())[:5]:
    print(f"  SKU {sku}: revenue={data.get('revenue')}, orders={data.get('orders')}")

# Funnel
ff = f.get('funnel_summary', {})
print(f"orders: {ff.get('orderCount')}, buyouts: {ff.get('buyoutCount')}")
```

## Step 4 — Iterate

After verifying, if bugs found:
1. Fix the code in `audit/` files
2. Re-run step 1
3. Re-verify step 2
4. Repeat until all checks pass

**Common fix locations:**
- `audit/audit_loader.py` — data parsing, column aliases, file detection
- `audit/audit_facts_builder.py` — facts construction, per-SKU calculations
- `audit/audit_report.py` — markdown report generation, section formatting
- `audit/lib/metrics.py` — financial calculations (isolated copy)

## Files touched

- `audit/run_audit.py` — entry point
- `audit/audit_loader.py` — data parsing
- `audit/audit_facts_builder.py` — facts construction
- `audit/audit_report.py` — report generation
- `local_audit/input/` — input files
- `local_audit/output/` — generated reports

## Findings worth promoting

- Always use `sys.stdout.reconfigure(encoding='utf-8')` in inline Python on Windows (cp1251 default)
- `PYTHONPATH=.` required when running audit from project root
- Audit output date is derived from input file dates, not current date
- Sales_dynamic override happens AFTER funnel parsing, can change buyouts 37→63
- CR > 100% is normal for WB (buyouts can exceed orders in same period)
