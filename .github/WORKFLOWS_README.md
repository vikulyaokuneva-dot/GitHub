# GitHub Actions Workflows

## Overview

This repository has workflows for multiple project versions (v2, v3, v4, v5). Each workflow is independent and can be triggered separately.

---

## V5 Workflows (New Unified Architecture)

### `v5-daily-api.yml` - API Mode
**Purpose**: Daily automated data pull from WB API and analytics

- **Trigger**: Schedule at 06:00 Moscow time (03:00 UTC) daily
- **Manual Trigger**: Workflow dispatch with optional seller_id and run_date
- **Seller ID**: Default `seller_001`, customizable
- **Required Secrets**: 
  - `WB_API_TOKEN` (shared with v2/v3)
  - `YANDEX_SMTP_USER` (shared with v2/v3)
  - `YANDEX_SMTP_APP_PASS` (shared with v2/v3)
  - `EMAIL_TO` (shared with v2/v3)
  - `GIGACHAT_SCOPE` (shared with v2/v3)

**Variables** (optional, in GitHub repo settings):
- `V5_SCHEDULE_ENABLED` (default: `true`) - disable schedule to stop auto-runs
- `V5_SCHEDULE_SELLER` - default seller for scheduled runs
- `GIGACHAT_MODEL` (default: `GigaChat-2`)

**Outputs**: PDF reports, metrics, decisions in `cabinets/{seller_id}/outputs/`

---

### `v5-daily-audit.yml` - Audit Mode
**Purpose**: Historical analysis from uploaded WB report files (Excel/CSV)

- **Trigger**: Manual only (schedule can be enabled via variable)
- **Manual Trigger**: Workflow dispatch with optional seller_id and run_date
- **Seller ID**: Default `seller_001`, customizable
- **Required Secrets**: Same as API mode
- **Input Files**: Automatically collected from:
  - `input/` (root)
  - `.github/input/`
  - `data/input/`
  - `audit/input/`
  - `cabinets/{seller_id}/input/`
  - `cabinets/__missing_seller__/input/`

Supports: `.xlsx`, `.xls`, `.csv`, `.zip` (auto-unpacks)

**Outputs**: PDF reports, metrics, decisions in `cabinets/{seller_id}/outputs/`

---

## Legacy Workflows (Maintained for Backwards Compatibility)

### `v2-daily-manual.yml`
- Manual trigger only
- Uses: `WB_API_TOKEN`, `GIGACHAT_AUTH_KEY`, `YANDEX_SMTP_*`, `EMAIL_TO`
- Entry: `python -m src.main`
- Output: `./out/`

### `daily.yml` (V3)
- Schedule: 05:00 Moscow time (02:00 UTC)
- Uses: `WB_API_TOKEN`, `YANDEX_SMTP_*`, `EMAIL_TO`, `GIGACHAT_SCOPE`
- Entry: `python -m v3.entry daily --seller {seller_id}`
- Mode: Hybrid (API + Audit)

### `v4-daily-0600-msk.yml`
- Schedule: 06:00 Moscow time (03:00 UTC)
- Uses: `WB_API_TOKEN`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_TO`, `SMTP_*`
- Entry: `v4/scripts/schedules_daily_run.py`
- Modes: `legacy | v4 | shadow`

---

## Secrets Table (All Versions)

| Secret | Used By | Purpose |
|--------|---------|---------|
| `WB_API_TOKEN` | v2, v3, v4, v5 | WB API authentication |
| `GIGACHAT_AUTH_KEY` | v2 | GigaChat AI analysis (v2 only) |
| `GIGACHAT_SCOPE` | v3, v5 | GigaChat scope token |
| `YANDEX_SMTP_USER` | v2, v3, v5 | Yandex email sender |
| `YANDEX_SMTP_APP_PASS` | v2, v3, v5 | Yandex app password |
| `EMAIL_USERNAME` | v4 | Email sender (v4 only) |
| `EMAIL_PASSWORD` | v4 | Email password (v4 only) |
| `SMTP_HOST` | v4 | SMTP host (v4 only) |
| `SMTP_PORT` | v4 | SMTP port (v4 only) |
| `SMTP_SSL` | v4 | SMTP SSL flag (v4 only) |
| `EMAIL_TO` | v2, v3, v4, v5 | Recipient email |

---

## Setup Instructions

### 1. Add GitHub Secrets
Go to **Settings > Secrets and variables > Actions**:

```
WB_API_TOKEN = <your_wb_api_key>
YANDEX_SMTP_USER = <your_yandex_email>
YANDEX_SMTP_APP_PASS = <your_app_password>
EMAIL_TO = <recipient_email>
GIGACHAT_SCOPE = <your_gigachat_scope_token>
```

### 2. (Optional) Configure Variables
Go to **Settings > Secrets and variables > Variables**:

```
V5_SCHEDULE_ENABLED = true
V5_SCHEDULE_SELLER = seller_001
GIGACHAT_MODEL = GigaChat-2
```

### 3. Run Workflows

**Manual run**:
- Go to **Actions > [Workflow Name]**
- Click **Run workflow**
- Fill in `seller_id` and `run_date` (optional)

**Scheduled**:
- Enabled automatically after setup
- Check **Actions** tab for run history

---

## Troubleshooting

### Workflow fails with "secret not found"
**Solution**: Add missing secret to GitHub repo settings

### Manual workflow dispatch shows wrong input fields
**Solution**: Refresh page or clear browser cache

### PDF not generated
**Solution**: Check logs in **Actions > [Workflow Run] > Run V5 daily * pipeline**

### Schedule runs at wrong time
**Note**: GitHub cron is UTC. Moscow = UTC+3 year-round (no DST in Russia)
- 06:00 Moscow = 03:00 UTC → cron `"0 3 * * *"`

### Cabinet outputs not found
**Solution**: Check if `cabinets/{seller_id}/` directory was created, or examine workflow logs

---

## Next Steps

1. **Enable V5 workflows**: Set `V5_SCHEDULE_ENABLED = true` in Variables
2. **Test manually**: Run `v5-daily-api.yml` with default `seller_001`
3. **Monitor logs**: Check artifacts in Actions after each run
4. **Disable old workflows** if v5 becomes stable (set schedules to empty, or delete files)
