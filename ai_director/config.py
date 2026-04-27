from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_DIRECTOR_DIR = Path(__file__).resolve().parent

TASKS_FILE = AI_DIRECTOR_DIR / "tasks" / "tasks.json"
LOGS_DIR = AI_DIRECTOR_DIR / "logs"
RUNS_DIR = LOGS_DIR / "runs"
PROMPTS_DIR = AI_DIRECTOR_DIR / "prompts"

DEFAULT_CHECKS = ["python -m pytest"]
MAX_ITERATIONS_DEFAULT = 5

LOCAL_LLM_PROVIDER = "ollama"
LOCAL_LLM_BASE_URL = "http://localhost:11434"
LOCAL_LLM_MODEL = "qwen2.5-coder:7b"
LOCAL_LLM_TIMEOUT_SEC = 120

ALLOWED_WRITE_PATHS = (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tests",
    AI_DIRECTOR_DIR,
)

FORBIDDEN_WRITE_PATHS = (
    PROJECT_ROOT / ".git",
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / "credentials",
    PROJECT_ROOT / "secrets",
)
