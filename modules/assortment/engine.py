"""Minimal assortment engine placeholder."""

from __future__ import annotations

from pathlib import Path

from shared.io.json_io import write_json


def run_assortment(seller_path: Path) -> dict:
    """Write a minimal assortment summary JSON."""
    summary = {
        "status": "ok",
        "note": "assortment module placeholder",
    }
    write_json(seller_path / "analytics" / "assortment_summary.json", summary)
    return summary

