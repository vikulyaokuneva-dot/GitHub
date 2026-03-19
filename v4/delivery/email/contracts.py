"""Email delivery contracts.

Input: EmailPayload and optional attachment paths.
Output: delivery-ready message draft.
Does not send SMTP by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailMessageDraft:
    """Serializable email draft used by preview/sender adapters."""

    subject: str
    preheader: str
    mode: str
    body: str
    attachments: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
