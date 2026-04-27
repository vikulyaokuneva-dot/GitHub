from __future__ import annotations

import subprocess
import time
from typing import Any


def run_command(command: str, timeout: int = 300) -> dict[str, Any]:
    started_at = time.time()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "duration_sec": round(time.time() - started_at, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
            "duration_sec": round(time.time() - started_at, 3),
        }


def run_checks(checks: list[str], timeout: int = 300) -> dict[str, Any]:
    results = [run_command(command, timeout=timeout) for command in checks]
    return {
        "ok": all(item.get("returncode") == 0 and not item.get("timed_out") for item in results),
        "results": results,
    }
