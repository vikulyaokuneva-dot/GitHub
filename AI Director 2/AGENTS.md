# AGENTS.md — WB Autopilot

## Mission
Build a production-grade multi-tenant SaaS platform for Wildberries sellers:
WB API -> normalized data -> finance/unit economics -> analytics -> AI Director -> recommendations -> controlled automation.

## Non-negotiable architecture rules
1. One metric = one owner.
2. AI is never the source of truth for financial/business metrics.
3. Raw -> normalized -> derived -> AI is a strict pipeline.
4. All WB API access goes through `packages/wb_core`.
5. Domain code must not make arbitrary HTTP requests to WB.
6. All write actions go through Automation Engine + Policy + Audit.
7. All tenant-owned data is tenant-scoped.
8. All important calculations have deterministic tests.
9. Do not rewrite working legacy code before regression coverage exists.
10. Prefer modular monolith + workers over premature microservices.
11. Do not introduce Kubernetes until a documented need exists.
12. Do not introduce ML/vector DB/browser automation in MVP without a concrete requirement.
13. Never log secrets or full WB API tokens.
14. Every sync/job/action must be idempotent.
15. Every external API client must implement timeout, retry policy, rate limiting, structured errors, and observability.

## Current legacy project
The existing `ИИ Директор ВБ` codebase contains proven logic such as:
- `wb_api_core`
- `report_v2`
- `core_report_bridge`
- finance normalization
- sales funnel logic
- date alignment/operational date handling
- diagnostic artifacts

Preserve working behavior. Migrate behind interfaces and adapters.

## Required task style
Every Codex task should include:
- Goal
- Context
- Files/modules
- Acceptance criteria
- Non-goals
- Tests
- Migration impact
- Security impact when applicable

Do not take a broad vague task when it can be split into independent vertical slices.

## Definition of Done
- implementation complete
- type checks pass
- relevant tests pass
- regression tests added/updated
- migration reviewed
- logs/metrics considered
- docs updated
- no unrelated refactor
- no secrets
- no duplicated business rule
- diff reviewed

## Required validation
Before changing domain behavior:
1. Identify current owner of the metric/business rule.
2. Find existing tests/fixtures.
3. Add or run a regression fixture.
4. Implement.
5. Compare before/after where possible.

## Security
- never expose credentials to AI prompts
- encrypt credentials at rest
- mask secrets in UI/logs
- enforce tenant scope server-side
- require policy checks for write actions
- keep audit records for security-sensitive changes
