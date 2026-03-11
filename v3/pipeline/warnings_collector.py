from __future__ import annotations

from typing import Any, Dict, List


class WarningsCollector:
    def __init__(self, initial: List[Dict[str, Any]] | None = None) -> None:
        self._warnings: List[Dict[str, Any]] = []
        if isinstance(initial, list):
            self.extend_warnings(initial)

    def add_warning(self, code: str, message: str) -> None:
        self._warnings.append(
            {
                "code": str(code or "").strip(),
                "message": str(message or "").strip(),
            }
        )

    def extend_warnings(self, items: List[Dict[str, Any]] | None) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            message = str(item.get("message") or "").strip()
            if not code and not message:
                continue
            normalized = dict(item)
            normalized["code"] = code
            normalized["message"] = message
            self._warnings.append(normalized)

    def export_warnings(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._warnings if isinstance(item, dict)]
