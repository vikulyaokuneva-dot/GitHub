"""Email output payload exports."""

from .builder import build_email_payload
from .contracts import EmailPayload, EmailSection

__all__ = ["EmailPayload", "EmailSection", "build_email_payload"]
