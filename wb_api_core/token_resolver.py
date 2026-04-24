from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


WB_API_TOKEN_ENV_NAME = "WB_API_TOKEN"


def _clean_token(value: Any) -> str:
    return str(value or "").strip()


def resolve_wb_api_token(
    explicit_token: Any = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    token = _clean_token(explicit_token)
    if token:
        return token, WB_API_TOKEN_ENV_NAME

    source_env = os.environ if env is None else env
    token = _clean_token(source_env.get(WB_API_TOKEN_ENV_NAME, ""))
    return token, WB_API_TOKEN_ENV_NAME
