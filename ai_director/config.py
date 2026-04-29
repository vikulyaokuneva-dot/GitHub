from __future__ import annotations

from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_DIRECTOR_DIR = Path(__file__).resolve().parent

TASKS_FILE = AI_DIRECTOR_DIR / "tasks" / "tasks.json"
LOGS_DIR = AI_DIRECTOR_DIR / "logs"
RUNS_DIR = LOGS_DIR / "runs"
PROMPTS_DIR = AI_DIRECTOR_DIR / "prompts"

DEFAULT_CHECKS = ["python -m pytest"]
MAX_ITERATIONS_DEFAULT = 5

LLM_PROVIDER = "openrouter"
DEFAULT_AI_DIRECTOR_MODEL = "openai/gpt-oss-120b:free"
DEFAULT_AI_DIRECTOR_MODEL_FALLBACKS = (
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "mistralai/mistral-7b-instruct",
)

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


# =========================
# 🔥 НОВОЕ — loader .env
# =========================

def _project_root() -> Path:
    return PROJECT_ROOT


def load_env_config() -> Dict[str, str]:
    env_path = _project_root() / ".env"
    config: Dict[str, str] = {}

    if not env_path.is_file():
        return config

    try:
        with env_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()

    except OSError:
        return {}

    return config
