from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_simple_yaml(path: str) -> Dict[str, Any]:
    """Simple YAML parser for config files (dicts + scalar lists)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any, str | None]] = [(0, root, None)]  # (indent, container, parent_key)

    for index, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()

        _, current, parent_key = stack[-1]

        if line.startswith("- "):
            if isinstance(current, list):
                current.append(_parse_scalar(line[2:]))
                continue
            if isinstance(current, dict) and parent_key and isinstance(current.get(parent_key), list):
                current[parent_key].append(_parse_scalar(line[2:]))
                continue
            raise ValueError(f"Invalid list item at {path}:{index + 1}")

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not isinstance(current, dict):
            raise ValueError(f"Invalid mapping at {path}:{index + 1}")

        if value != "":
            current[key] = _parse_scalar(value)
            continue

        next_non_empty = ""
        for look_ahead in lines[index + 1:]:
            if not look_ahead.strip() or look_ahead.lstrip().startswith("#"):
                continue
            next_non_empty = look_ahead
            break

        next_is_list = False
        if next_non_empty:
            next_indent = len(next_non_empty) - len(next_non_empty.lstrip(" "))
            next_is_list = next_indent > indent and next_non_empty.strip().startswith("- ")

        if next_is_list:
            current[key] = []
            stack.append((indent + 2, current[key], key))
        else:
            current[key] = {}
            stack.append((indent + 2, current[key], key))

    return root


def ensure_list_container(cfg: Dict[str, Any], key: str) -> None:
    value = cfg.get(key)
    if value is None:
        cfg[key] = []
    elif not isinstance(value, list):
        cfg[key] = [value] if value != "" else []
