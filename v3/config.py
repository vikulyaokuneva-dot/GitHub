from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Dict


def _default_config(seller_id: str) -> Dict[str, Any]:
    return {
        "seller_id": seller_id,
        "seller_name": seller_id,
        "timezone": "Europe/Moscow",
        "tax_rate": 0.06,
        "email_reports_to": [],
        "wb": {"token_ref": ""},
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_seller_config(repo_root: str, seller_id: str) -> Dict[str, Any]:
    """
    Load cabinets/<seller_id>/config.json.
    If file does not exist or cannot be parsed, return defaults.
    """
    defaults = _default_config(seller_id)
    path = os.path.join(repo_root, "cabinets", seller_id, "config.json")
    if not os.path.exists(path):
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return defaults

    if not isinstance(payload, dict):
        return defaults
    return _deep_merge(defaults, payload)
