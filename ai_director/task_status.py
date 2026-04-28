'''Task status utilities.'''

# Existing imports and code (if any) would be here.

def normalize_status(status: str) -> str:
    """Return a normalized task status.

    The function trims whitespace from the input string, converts it to upper‑case,
    and returns ``"NEW"`` when the resulting string is empty.
    """
    normalized = (status or "").strip().upper()
    return normalized if normalized else "NEW"

# Exported symbols
__all__ = [
    "normalize_status",
]
