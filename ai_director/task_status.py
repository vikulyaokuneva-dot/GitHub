"""
Helper utilities for task status handling within the AI Director.

This module provides a single function `is_terminal_status` that determines
whether a given task status string represents a terminal state of the
task lifecycle.

Terminal statuses (return True):
- DONE
- FAILED
- NEEDS_HUMAN

All other statuses (including unknown strings) return False.
"""

from __future__ import annotations

# Define the set of terminal statuses for quick membership testing.
_TERMINAL_STATUSES = {"DONE", "FAILED", "NEEDS_HUMAN"}


def is_terminal_status(status: str) -> bool:
    """
    Check if the provided task status is a terminal status.

    Parameters
    ----------
    status: str
        The status string to evaluate. Comparison is case‑sensitive and
        expects the exact status identifiers used by the AI Director.

    Returns
    -------
    bool
        ``True`` if ``status`` is one of the terminal statuses
        (``DONE``, ``FAILED``, ``NEEDS_HUMAN``), otherwise ``False``.
    """
    return status in _TERMINAL_STATUSES