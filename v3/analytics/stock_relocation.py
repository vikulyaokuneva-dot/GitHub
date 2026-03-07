from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _load_territorial_distribution(territorial_distribution: Dict[str, Any] | str | Path) -> Dict[str, Any]:
    if isinstance(territorial_distribution, dict):
        return territorial_distribution
    path = Path(territorial_distribution)
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return payload if isinstance(payload, dict) else {}


def build_stock_relocation_plan(territorial_distribution: Dict[str, Any] | str | Path) -> Dict[str, Any]:
    _load_territorial_distribution(territorial_distribution)
    return {
        "metadata": {
            "engine": "stock_relocation_ai",
            "version": "0.1",
        },
        "relocations": [],
    }


def save_stock_relocation_plan(output_path: Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
