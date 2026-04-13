from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Dict

from .utils import load_simple_yaml


def _default_config(seller_id: str) -> Dict[str, Any]:
    return {
        "seller_id": seller_id,
        "seller_name": seller_id,
        "timezone": "Europe/Moscow",
        "tax_rate": 0.06,
        "email_reports_to": [],
        "wb": {"token_ref": ""},
        "territorial_distribution": {
            "enable_territorial_distribution_engine": True,
            "wb_irp_effective_date": "2026-03-23",
            "distribution_profit_leak_threshold": 5000.0,
            "localization_watch_threshold": 60.0,
            "localization_weak_threshold": 40.0,
            "localization_critical_threshold": 20.0,
            "min_orders_for_confidence": 3.0,
            "min_orders_for_actionable": 5.0,
            "min_portfolio_coverage_pct": 40.0,
            "min_demand_coverage_pct": 50.0,
            "min_stock_coverage_pct": 40.0,
            "max_unknown_share_pct": 60.0,
        },
        "advertising_efficiency": {
            "enable_advertising_efficiency_engine": True,
            "min_orders_for_confidence": 3,
            "min_query_clicks_for_confidence": 5,
            "high_romi_threshold_pct": 40.0,
            "budget_leak_spend_threshold": 1000.0,
        },
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
    Load seller config for active v3 daily contour.
    Primary format: config.yaml
    Legacy fallback: config.json
    """
    defaults = _default_config(seller_id)
    seller_dir = os.path.join(repo_root, "cabinets", seller_id)
    yaml_path = os.path.join(seller_dir, "config.yaml")
    json_path = os.path.join(seller_dir, "config.json")

    if os.path.exists(yaml_path):
        try:
            payload = load_simple_yaml(yaml_path)
            if isinstance(payload, dict):
                return _deep_merge(defaults, payload)
        except Exception:
            pass

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            if isinstance(payload, dict):
                return _deep_merge(defaults, payload)
        except (OSError, json.JSONDecodeError):
            pass

    return defaults
