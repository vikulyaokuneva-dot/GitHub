# WB Autopilot — Initial Codex Backlog

Use these as GitHub Issues/Epics. Keep each implementation issue small and testable.

## EPIC 0 — Repository & architecture
- [ ] 001 Create repository skeleton
- [ ] 002 Add architecture ADRs
- [ ] 003 Add AGENTS.md and contribution rules
- [ ] 004 Configure Python, linting, typing, test tooling
- [ ] 005 Docker Compose: Postgres, Redis, RabbitMQ
- [ ] 006 FastAPI application shell
- [ ] 007 Worker/Celery application shell
- [ ] 008 GitHub Actions CI
- [ ] 009 Environment/config management
- [ ] 010 Health/readiness endpoints

## EPIC 1 — Identity & tenancy
- [ ] 011 User model
- [ ] 012 Tenant/Organization model
- [ ] 013 Membership/RBAC
- [ ] 014 Subscription/Plan skeleton
- [ ] 015 Tenant-scoped repository pattern
- [ ] 016 Auth/session flow
- [ ] 017 Audit log base

## EPIC 2 — WB Core
- [ ] 018 WB account model
- [ ] 019 Encrypted credential storage
- [ ] 020 WB service registry
- [ ] 021 Typed HTTP client base
- [ ] 022 Retry/error taxonomy
- [ ] 023 Per-account/per-endpoint rate limiting
- [ ] 024 Sync job model
- [ ] 025 Watermark/cursor state
- [ ] 026 Raw response storage
- [ ] 027 Data freshness model
- [ ] 028 Initial sync orchestration

## EPIC 3 — Existing AI Director migration
- [ ] 029 Inventory current repository
- [ ] 030 Dependency map
- [ ] 031 Freeze legacy writes
- [ ] 032 Build golden fixtures
- [ ] 033 Regression suite for finance
- [ ] 034 Regression suite for funnel
- [ ] 035 Extract wb_api_core adapter
- [ ] 036 Extract report_v2 package
- [ ] 037 Migrate core_report_bridge behind interface
- [ ] 038 Remove only proven-dead legacy paths

## EPIC 4 — Core domains
- [ ] 039 Product domain
- [ ] 040 Sales/orders domain
- [ ] 041 Returns/cancellations
- [ ] 042 Inventory domain
- [ ] 043 Advertising domain
- [ ] 044 Finance domain
- [ ] 045 Unit economics
- [ ] 046 Product cost history
- [ ] 047 Price history

## EPIC 5 — Analytics
- [ ] 048 Funnel metrics
- [ ] 049 Search metrics
- [ ] 050 Product performance
- [ ] 051 Period comparison
- [ ] 052 Dashboard read models
- [ ] 053 Anomaly engine
- [ ] 054 Finance reconciliation
- [ ] 055 Data-quality status

## EPIC 6 — Frontend
- [ ] 056 App shell
- [ ] 057 Auth screens
- [ ] 058 Connect WB account
- [ ] 059 Dashboard
- [ ] 060 Finance
- [ ] 061 Products
- [ ] 062 Advertising
- [ ] 063 Inventory
- [ ] 064 Alerts
- [ ] 065 Recommendations

## EPIC 7 — AI Director
- [ ] 066 AI Gateway
- [ ] 067 Tool registry
- [ ] 068 Structured output schemas
- [ ] 069 Daily brief
- [ ] 070 Product analysis
- [ ] 071 Finance analysis
- [ ] 072 Advertising analysis
- [ ] 073 Inventory analysis
- [ ] 074 Scenario engine integration
- [ ] 075 Conversation history
- [ ] 076 AI cost/usage telemetry

## EPIC 8 — Reporting
- [ ] 077 Reusable report payload model
- [ ] 078 PDF renderer integration
- [ ] 079 CSV/XLSX exports
- [ ] 080 Daily report
- [ ] 081 Weekly report
- [ ] 082 Product report
- [ ] 083 Finance report
- [ ] 084 Scheduled reports

## EPIC 9 — Automation
- [ ] 085 Domain event model
- [ ] 086 Rule model
- [ ] 087 Rule evaluator
- [ ] 088 Recommendation object
- [ ] 089 Approval policies
- [ ] 090 Action registry
- [ ] 091 Dry-run mode
- [ ] 092 Automation executor
- [ ] 093 Action audit
- [ ] 094 Safety limits
- [ ] 095 Rollback strategy where supported

## EPIC 10 — Notifications
- [ ] 096 Notification service
- [ ] 097 Telegram integration
- [ ] 098 Email integration
- [ ] 099 Daily digest
- [ ] 100 Approval notifications

## EPIC 11 — Multi-account / Agency
- [ ] 101 Multi-account dashboard
- [ ] 102 Client hierarchy
- [ ] 103 Manager assignments
- [ ] 104 Agency permissions
- [ ] 105 Usage metering
- [ ] 106 Billing skeleton
- [ ] 107 Admin operations panel

## EPIC 12 — Production
- [ ] 108 Monitoring
- [ ] 109 Error tracking
- [ ] 110 Database backups
- [ ] 111 Restore test
- [ ] 112 Security scan
- [ ] 113 Dependency scanning
- [ ] 114 Load tests
- [ ] 115 Production deployment
- [ ] 116 Incident runbooks

## Vertical-slice milestone
After issue 075 the first commercially meaningful slice should work:

Connect WB -> sync -> calculate economics -> dashboard -> ask AI -> get grounded answer.

After issue 095:

Connect -> monitor -> recommend -> approve -> execute -> audit.

## Codex execution rule
Do not close an issue because code "looks right". Close it only when acceptance criteria and tests pass.
