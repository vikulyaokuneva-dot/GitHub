from enum import Enum


class TaskStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


def normalize_status(status: str) -> str:
    """Normalize a task status string.

    - Strips surrounding whitespace.
    - Converts to upper‑case.
    - If the resulting string is empty, returns ``TaskStatus.NEW``.
    """
    if status is None:
        return TaskStatus.NEW.value
    normalized = status.strip().upper()
    return normalized if normalized else TaskStatus.NEW.value
