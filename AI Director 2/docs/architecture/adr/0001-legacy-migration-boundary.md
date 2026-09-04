# ADR 0001: Migrate legacy code through adapters

## Status

Accepted.

## Context

The repository-root project contains working WB ingestion, finance, analytics,
decision and reporting code. Its modules are not tenant-aware services and
some pipeline stages dynamically import `v3.entry`.

## Decision

New packages must not import legacy modules directly. `packages/compat` will
contain explicit adapters that translate between legacy artifacts and new typed
contracts. A legacy component moves only after golden-fixture parity and a
dependency map show no hidden consumer.

## Consequences

- `wb_api_core` is the first adapter candidate.
- `v3/core_report_bridge.py` remains transitional and is not a new domain API.
- Legacy modules are deleted only after every production caller uses a new
  interface and parity tests pass.
