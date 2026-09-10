"""Endpoint-specific raw payload rules. No global array relaxation."""
from __future__ import annotations

# /api/v2/list/goods/filter returns a top-level array. It is admitted only
# for this endpoint via an explicit endpoint-specific policy, not globally.
# All other endpoints must supply payloads matching their EndpointMetadata
# expected_payload_kind (object or array explicitly declared per endpoint).
ENDPOINT_ARRAY_POLICY = {
    "sales_funnel_products": "object",
    "finance_detail": "array",
    # Stage 19 endpoint addition — must declare array explicitly:
    "/api/v2/list/goods/filter": "array",
}
