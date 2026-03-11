from __future__ import annotations

from typing import Any, MutableMapping


def sync_from_entry(namespace: MutableMapping[str, Any]) -> None:
    from .. import entry as E

    for key, value in E.__dict__.items():
        if key.startswith("__"):
            continue
        namespace.setdefault(key, value)
