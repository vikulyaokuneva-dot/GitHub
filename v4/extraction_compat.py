"""Compatibility extraction helpers inspired by v2 metrics behavior.

Input: arbitrary raw payload (dict/list/json string/mixed nesting).
Output: normalized list[dict] rows + extraction diagnostics.
Does not call network and does not compute metrics.
"""

from __future__ import annotations

import json
from typing import Any, Iterable


DEFAULT_CONTAINER_KEYS: tuple[str, ...] = (
    "items",
    "products",
    "rows",
    "list",
    "result",
    "stocks",
    "data",
)


def payload_shape(payload: Any) -> str:
    if payload is None:
        return "none"
    if isinstance(payload, list):
        return "list"
    if isinstance(payload, dict):
        return "dict"
    if isinstance(payload, str):
        return "str"
    return type(payload).__name__


def try_json_loads(value: Any) -> Any:
    """Best-effort JSON parse for string payloads."""

    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return value

    if isinstance(value, str):
        text = value.strip()
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                return json.loads(text)
            except Exception:
                return value
    return value


def _row_like_dict(payload: dict[str, Any], row_like_keys: tuple[str, ...] | None) -> bool:
    if not payload:
        return False
    if row_like_keys:
        return any(key in payload for key in row_like_keys)
    return any(not isinstance(value, (dict, list, tuple, set)) for value in payload.values())


def _dict_rows_from_list(payload: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload:
        parsed = try_json_loads(item)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _find_first_list_recursive(
    payload: Any,
    *,
    preferred_keys: tuple[str, ...],
    max_depth: int,
    path: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], tuple[str, ...], bool] | None:
    parsed = try_json_loads(payload)
    if max_depth < 0:
        return None

    if isinstance(parsed, list):
        return _dict_rows_from_list(parsed), path, True

    if not isinstance(parsed, dict):
        return None

    for key in preferred_keys:
        if key in parsed:
            found = _find_first_list_recursive(
                parsed.get(key),
                preferred_keys=preferred_keys,
                max_depth=max_depth - 1,
                path=(*path, str(key)),
            )
            if found is not None:
                return found

    for key, value in parsed.items():
        if str(key) in preferred_keys:
            continue
        found = _find_first_list_recursive(
            value,
            preferred_keys=preferred_keys,
            max_depth=max_depth - 1,
            path=(*path, str(key)),
        )
        if found is not None:
            return found

    return None


def find_first_list(
    payload: Any,
    *,
    max_depth: int = 6,
    preferred_keys: Iterable[str] = DEFAULT_CONTAINER_KEYS,
) -> list[dict[str, Any]] | None:
    """Return first discovered list[dict] in payload tree, if any."""

    preferred = tuple(str(key) for key in preferred_keys)
    found = _find_first_list_recursive(
        payload,
        preferred_keys=preferred,
        max_depth=max_depth,
    )
    if found is None:
        return None
    rows, _, _ = found
    return rows or None


def normalize_items(
    raw: Any,
    *,
    max_depth: int = 6,
    preferred_keys: Iterable[str] = DEFAULT_CONTAINER_KEYS,
    allow_single_dict: bool = False,
    row_like_keys: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """V2-like permissive normalization into list[dict] rows."""

    rows, _ = extract_rows_with_meta(
        raw,
        max_depth=max_depth,
        preferred_keys=preferred_keys,
        allow_single_dict=allow_single_dict,
        row_like_keys=row_like_keys,
    )
    return rows


# Back-compat aliases to mirror v2 naming style.
_try_json_loads = try_json_loads
_find_first_list = find_first_list
_normalize_items = normalize_items


def extract_rows_with_meta(
    raw: Any,
    *,
    max_depth: int = 6,
    preferred_keys: Iterable[str] = DEFAULT_CONTAINER_KEYS,
    allow_single_dict: bool = False,
    row_like_keys: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract list[dict] rows with diagnostics describing extraction path."""

    preferred = tuple(str(key) for key in preferred_keys)
    row_keys = tuple(str(key) for key in row_like_keys) if row_like_keys is not None else None

    parsed = try_json_loads(raw)
    meta: dict[str, Any] = {
        "payload_shape": payload_shape(parsed),
        "mode": "none",
        "origin": None,
        "compat_used": False,
        "explicit_empty_list": False,
        "preferred_keys": list(preferred),
    }

    if isinstance(parsed, list):
        rows = _dict_rows_from_list(parsed)
        meta["mode"] = "top_list"
        meta["origin"] = "$"
        meta["explicit_empty_list"] = len(parsed) == 0
        return rows, meta

    if isinstance(parsed, dict):
        for key in preferred:
            if key not in parsed:
                continue
            candidate = try_json_loads(parsed.get(key))
            if isinstance(candidate, list):
                rows = _dict_rows_from_list(candidate)
                meta["mode"] = "preferred_key_list"
                meta["origin"] = str(key)
                meta["compat_used"] = str(key) != "rows"
                meta["explicit_empty_list"] = len(candidate) == 0
                return rows, meta

        found = _find_first_list_recursive(
            parsed,
            preferred_keys=preferred,
            max_depth=max_depth,
        )
        if found is not None:
            rows, path, list_found = found
            meta["mode"] = "recursive_list"
            meta["origin"] = ".".join(path) if path else "$"
            meta["compat_used"] = True
            meta["explicit_empty_list"] = bool(list_found and len(rows) == 0)
            return rows, meta

        if allow_single_dict and _row_like_dict(parsed, row_keys):
            meta["mode"] = "single_dict_fallback"
            meta["origin"] = "$"
            meta["compat_used"] = True
            return [parsed], meta

    return [], meta

