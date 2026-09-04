# ADR 0002: Preserve metric provenance and semantics

## Status

Accepted.

## Decision

Each business metric has one owner, a source contract and deterministic tests.
AI receives derived facts and their data-quality status, never raw credentials
or an authority to calculate financial metrics itself.

For the first migration domains:

- `card_opens` means WB sales-funnel `openCount`; it is not advertising
  impressions and must not be exposed as an ambiguous `views` metric.
- Finance detailed data uses the Finance API contract. Direct logistics and
  `rebillLogisticCost` remain separate components so they cannot be omitted or
  subtracted twice.
- Monetary values in new code use `Decimal` at domain and persistence
  boundaries. Timestamps are UTC; WB business-day calculations use
  `Europe/Moscow`.

## Consequences

Changing a formula requires updating the legacy metric passport, this ADR when
needed, and the relevant golden fixtures.
