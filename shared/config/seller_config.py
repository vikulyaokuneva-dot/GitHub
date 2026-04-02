"""Per-seller runtime configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.io.json_io import read_json


DEFAULT_SETTINGS: dict[str, Any] = {
    "tax_rate": 0.06,
    "currency": "RUB",
    "timezone": "Europe/Berlin",
}

DEFAULT_COGS: dict[str, Any] = {
    "settings": {"tax_rate": 0.06},
    "sku_cogs": {},
}


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_dict_with_fallback(path: Path, default_value: dict[str, Any], label: str) -> dict[str, Any]:
    if not path.exists():
        print(f"[config] {label} missing at {path}, using defaults")
        return dict(default_value)
    try:
        payload = read_json(path)
    except Exception as exc:
        print(f"[config] {label} invalid at {path}, using defaults ({exc})")
        return dict(default_value)
    if not isinstance(payload, dict):
        print(f"[config] {label} is not an object at {path}, using defaults")
        return dict(default_value)
    return payload


def load_seller_config(seller: str) -> dict[str, Any]:
    """Load seller settings/cogs with safe defaults and no hard failures."""
    config_dir = Path("runtime") / "cabinets" / seller / "config"
    settings = _load_dict_with_fallback(
        config_dir / "settings.json",
        DEFAULT_SETTINGS,
        "settings.json",
    )
    cogs = _load_dict_with_fallback(
        config_dir / "cogs.json",
        DEFAULT_COGS,
        "cogs.json",
    )

    tax_rate = _to_float(settings.get("tax_rate"))
    if tax_rate <= 0:
        tax_rate = _to_float((cogs.get("settings") or {}).get("tax_rate"))
    if tax_rate <= 0:
        tax_rate = 0.06
        print(f"[config] tax_rate missing for {seller}, fallback to 0.06")

    return {
        "seller": seller,
        "config_dir": str(config_dir),
        "settings": settings,
        "cogs": cogs,
        "tax_rate": tax_rate,
    }

