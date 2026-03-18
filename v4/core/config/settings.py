"""Global settings skeleton.

Input: env/config primitives.
Output: static settings object.
Does not read seller runtime data and does not resolve sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
    app_name: str = "wb-ai-agent-v4"
    default_timezone: str = "Europe/Moscow"
    default_mode: str = "daily_api_mode"
