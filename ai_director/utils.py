import re
from typing import Optional


def normalize_task_title(title: Optional[str]) -> str:
    if not title:
        return "task"

    normalized = title.lower()
    normalized = re.sub(r"[^a-z0-9 _-]+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return "task"

    if len(normalized) > 100:
        normalized = normalized[:100]

    return normalized