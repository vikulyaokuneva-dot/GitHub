"""Explain a failed WB source request without losing its proof.

``wb_api_core.client`` builds one failure reason string::

    [retry_window_exhausted: ]{status}: {official WB error body}; rate_limit_headers: ...

Both raise sites used to keep only ``reason[:200]``, and with a real WB error
body (300+ characters) that cut landed *inside* the JSON: the official
``origin`` / ``requestId`` and the whole ``rate_limit_headers`` block were
dropped. A ``source_unavailable`` diagnostic then carried a bare status code
plus a truncated body fragment, so the audit could no longer show **why** a
source is unavailable — a WB permission refusal (403 + the refusing zone in
``origin``) and a rate limit (429 + ``X-RateLimit-Retry``) are different
problems with different owners, and both must stay provable.

This module rebuilds one bounded message from the response/debug mapping the
transport already produced (``status_code``, ``method``, ``base_url``,
``path``, ``final_failure_reason`` / ``error_text`` plus the structured
rate-limit fields), so the loaders path and the compat transports state the
same reason.

Invariants:

* the endpoint name and ``WB request failed with status {code}`` prefix stay
  first, so existing ``startswith`` assertions keep holding;
* the request line (method + base URL + path) is stated, which is what tells
  a reader whether the endpoint itself was right;
* official WB fields (``detail``, ``origin``, ``requestId``, ...) are taken
  from the parsed body — an unparsed body is only excerpted, never dumped,
  so unknown/credential-shaped fields cannot leak into diagnostics;
* the rate-limit header block is never truncated away: the body is shrunk
  first, then the whole message is bounded.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["describe_source_failure"]

_MAX_MESSAGE_CHARS = 900
_MAX_HEADERS_CHARS = 400
_MAX_EXTRA_CHARS = 200
_ELLIPSIS = "…"

_RATE_LIMIT_TAIL_MARKER = "; rate_limit_headers:"
_FAILURE_KIND_PREFIX = "retry_window_exhausted:"
_RATE_LIMIT_FIELDS = (
    "retry_after",
    "x_ratelimit_retry",
    "x_ratelimit_reset",
    "x_ratelimit_remaining",
    "rate_limit_delay_seconds",
)
# WB error bodies are documented as status/statusText/title/detail/requestId/
# origin/timestamp; anything else is kept as a bounded ``extra`` blob instead
# of being silently dropped.
_OFFICIAL_FIELDS = frozenset({"status", "statusText", "title", "detail", "requestId", "origin", "timestamp"})
_STATUS_TEXT_FIELDS = ("statusText", "title")
# Unknown body fields may still be forwarded (bounded), but never a field whose
# name looks credential-shaped: diagnostics are part of the audit output.
_CREDENTIAL_FIELD_MARKERS = (
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "secret",
    "password",
    "cookie",
    "credential",
)


def describe_source_failure(
    *,
    endpoint_name: str,
    response: Mapping[str, Any] | None,
    fallback: str = "",
) -> str:
    """Build the audit-facing failure reason for one WB source request.

    ``response`` is the mapping ``request_json`` returns (or the ``debug``
    mapping a loader rebuilds from it); missing fields are tolerated because
    hand-built transports in tests only carry part of them. ``fallback`` is
    used when the mapping carries no reason at all, so the message never
    degrades to a bare status code.
    """

    data: Mapping[str, Any] = response if isinstance(response, Mapping) else {}
    head = f"{endpoint_name} WB request failed with status {data.get('status_code')}"
    location = _request_location(data)
    if location:
        head = f"{head} ({location})"

    reason = str(data.get("final_failure_reason") or data.get("error_text") or "").strip()
    reason, headers_text = _split_rate_limit_tail(reason)
    if not headers_text:
        headers_text = _structured_rate_limit_text(data)

    kind, body = _split_kind(reason)
    explanation = _explain(body, kind=kind)
    if not explanation and fallback:
        explanation = fallback.strip()
    return _compose(head=head, explanation=explanation, headers_text=headers_text)


def _request_location(data: Mapping[str, Any]) -> str:
    method = str(data.get("method") or "").strip().upper()
    base_url = str(data.get("base_url") or "").strip().rstrip("/")
    path = str(data.get("path") or "").strip()
    if not path:
        return ""
    target = f"{base_url}{path}" if base_url else path
    return f"{method} {target}" if method else target


def _split_rate_limit_tail(reason: str) -> tuple[str, str]:
    """Detach ``; rate_limit_headers: ...`` so the tail survives any body cut."""

    if not reason:
        return "", ""
    index = reason.rfind(_RATE_LIMIT_TAIL_MARKER)
    if index >= 0:
        tail = reason[index + len(_RATE_LIMIT_TAIL_MARKER) :].strip().strip(";").strip()
        head = reason[:index].rstrip()
        if not tail:
            return head, "rate_limit_headers"
        return head, f"rate_limit_headers: {tail}"
    if reason.startswith("rate_limit_headers:"):
        return "", reason.strip()
    return reason, ""


def _split_kind(reason: str) -> tuple[str, str]:
    if reason.startswith(_FAILURE_KIND_PREFIX):
        return _FAILURE_KIND_PREFIX, reason[len(_FAILURE_KIND_PREFIX) :].strip()
    return "", reason


def _explain(body: str, *, kind: str) -> str:
    prefix, official = _parse_official_body(body)
    summary = _official_summary(prefix, official) if official else body.strip()
    if not summary:
        return kind.rstrip()
    if kind:
        return f"{kind} {summary}"
    return summary


def _parse_official_body(body: str) -> tuple[str, dict[str, Any]]:
    start = body.find("{")
    end = body.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(body[start : end + 1])
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return body[:start].strip(), parsed
    return "", {}


def _official_summary(prefix: str, official: Mapping[str, Any]) -> str:
    status_text = _first_text(official, _STATUS_TEXT_FIELDS)
    detail = _first_text(official, ("detail",))
    core = ": ".join(part for part in (status_text, detail) if part)
    if prefix:
        core = f"{prefix} {core}" if core else prefix

    provenance: list[str] = []
    origin = _first_text(official, ("origin",))
    request_id = _first_text(official, ("requestId",))
    if origin:
        provenance.append(f"origin={origin}")
    if request_id:
        provenance.append(f"requestId={request_id}")
    if provenance:
        core = f"{core} ({', '.join(provenance)})" if core else ", ".join(provenance)

    extra = _unknown_fields(official)
    if extra:
        blob = json.dumps(extra, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(blob) > _MAX_EXTRA_CHARS:
            blob = blob[: _MAX_EXTRA_CHARS - 1] + _ELLIPSIS
        core = f"{core}; extra={blob}" if core else f"extra={blob}"
    return core


def _first_text(data: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _unknown_fields(official: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: official[key]
        for key in sorted(official)
        if key not in _OFFICIAL_FIELDS and not _credential_shaped(key)
    }


def _credential_shaped(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _CREDENTIAL_FIELD_MARKERS)


def _structured_rate_limit_text(data: Mapping[str, Any]) -> str:
    """Fallback proof when the reason string carries no header tail."""

    parts = []
    for key in _RATE_LIMIT_FIELDS:
        value = data.get(key)
        if value is None or str(value).strip() == "":
            continue
        parts.append(f"{key}={value}")
    if not parts:
        return ""
    return f"rate_limit_headers: {', '.join(parts)}"


def _compose(*, head: str, explanation: str, headers_text: str) -> str:
    tail = ""
    if headers_text:
        tail = f"; {headers_text}"
        if len(tail) > _MAX_HEADERS_CHARS:
            tail = f"; {headers_text[: _MAX_HEADERS_CHARS - 1]}{_ELLIPSIS}"

    # The body (least unique part) is shrunk first: head and the rate-limit
    # headers are the proof, the body text is the filler.
    budget = _MAX_MESSAGE_CHARS - len(head) - len(tail) - 2
    if len(explanation) > budget:
        explanation = explanation[: budget - 1] + _ELLIPSIS if budget > 1 else ""

    if explanation and tail:
        return f"{head}: {explanation}{tail}"
    if explanation:
        return f"{head}: {explanation}"
    return f"{head}{tail}"
