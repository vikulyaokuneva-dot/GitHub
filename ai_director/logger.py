from __future__ import annotations

import datetime
import pathlib
import threading


_lock = threading.Lock()

_LOG_DIR = pathlib.Path(__file__).resolve().parent / "logs"
_LOG_FILE = _LOG_DIR / "ai_director.log"


def log_event(message: str) -> None:
    if not isinstance(message, str):
        message = str(message)

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        with _lock:
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line)

    except Exception:
        pass