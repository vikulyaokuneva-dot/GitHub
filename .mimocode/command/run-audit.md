---
description: >
  Run the WB audit pipeline with correct encoding and standard parameters.
  Use: /run-audit [period] — e.g. /run-audit 2026-06-08_2026-06-14
  If no period given, auto-detects from input files.
---

Run the audit pipeline:

```python
import sys; sys.stdout.reconfigure(encoding='utf-8')
from audit.run_audit import run_audit_mode

run_audit_mode(
    input_dir='local_audit/input',
    out_dir='local_audit/output',
    source='wb',
    period='$ARGUMENTS' if '$ARGUMENTS' else None,
    send_email=False
)
```

If the period argument is empty, omit the `period` parameter to auto-detect.
After running, read `local_audit/output/audit_*.md` and report the KPI section (orders, buyouts, revenue, profit).
