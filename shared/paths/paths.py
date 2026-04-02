"""Path helpers for seller-scoped runtime folders."""

from pathlib import Path


def get_paths(seller: str) -> dict[str, Path]:
    """Return all runtime paths for a seller."""
    seller_path = Path("runtime") / "cabinets" / seller
    return {
        "seller_path": seller_path,
        "config": seller_path / "config",
        "raw": seller_path / "raw",
        "normalized": seller_path / "normalized",
        "analytics": seller_path / "analytics",
        "artifacts": seller_path / "artifacts",
        "outputs": seller_path / "outputs",
    }

