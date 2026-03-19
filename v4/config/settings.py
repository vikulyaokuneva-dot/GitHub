"""Application settings for v4 orchestration/runtime boundaries.

This layer is configuration-only and does not contain business/KPI logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_text(name: str, default: str) -> str:
    raw = str(os.getenv(name, default)).strip()
    return raw or default


@dataclass(frozen=True)
class AppSettings:
    """Deterministic runtime settings with environment-safe defaults."""

    output_root: str
    temp_root: str
    default_timezone: str
    wb_api_token_env: str
    default_daily_mode: str
    default_audit_mode: str


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    output_root = _env_text("V4_OUTPUT_ROOT", str(Path(".tmp") / "v4_outputs"))
    temp_root = _env_text("V4_TEMP_ROOT", str(Path(".tmp") / "v4_tmp"))
    default_timezone = _env_text("V4_DEFAULT_TIMEZONE", "Europe/Moscow")
    wb_api_token_env = _env_text("V4_WB_TOKEN_ENV", "WB_API_TOKEN")
    return AppSettings(
        output_root=output_root,
        temp_root=temp_root,
        default_timezone=default_timezone,
        wb_api_token_env=wb_api_token_env,
        default_daily_mode="daily",
        default_audit_mode="audit",
    )


def get_default_output_root() -> str:
    return get_settings().output_root


def get_temp_root() -> str:
    return get_settings().temp_root


__all__ = ["AppSettings", "get_settings", "get_default_output_root", "get_temp_root"]

