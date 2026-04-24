from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any


WB_TOKEN_ENV_NAMES: tuple[str, ...] = (
    "WB_API_TOKEN",
    "WB_TOKEN",
    "WILDBERRIES_API_TOKEN",
    "WB_STATISTICS_TOKEN",
    "WB_ANALYTICS_TOKEN",
    "WB_FINANCE_TOKEN",
)


def _clean_token(value: Any) -> str:
    return str(value or "").strip()


def _candidate_names(extra_env_names: Iterable[str] | None = None) -> tuple[str, ...]:
    names: list[str] = list(WB_TOKEN_ENV_NAMES)
    for raw_name in list(extra_env_names or ()):
        name = str(raw_name or "").strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def resolve_wb_api_token(
    explicit_token: Any = None,
    *,
    env: Mapping[str, str] | None = None,
    extra_env_names: Iterable[str] | None = None,
) -> tuple[str, str]:
    token = _clean_token(explicit_token)
    if token:
        return token, "argument"

    source_env = os.environ if env is None else env
    for name in _candidate_names(extra_env_names):
        token = _clean_token(source_env.get(name, ""))
        if token:
            return token, name
    return "", ""
