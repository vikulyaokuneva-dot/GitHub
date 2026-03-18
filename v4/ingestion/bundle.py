"""Raw bundle assembly skeleton.

Input: RunContext + per-source payload/status maps.
Output: RawBundle.
Does not validate business rules and does not normalize.
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.contracts import RawBundle, RunContext, SourceStatus


def build_raw_bundle(
    context: RunContext,
    payloads: Dict[str, Any],
    source_status: Dict[str, SourceStatus],
    diagnostics: Dict[str, Any] | None = None,
) -> RawBundle:
    return RawBundle(
        context=context,
        payloads=dict(payloads or {}),
        source_status=dict(source_status or {}),
        diagnostics=dict(diagnostics or {}),
    )
