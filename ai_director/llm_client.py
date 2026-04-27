from __future__ import annotations

import sys
from pathlib import Path

try:
    from src.openrouter_client import generate_text
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.openrouter_client import generate_text


def generate_fix_prompt(task: dict, failure_snapshot: dict) -> str:
    return f"""
You are the AI Director Fixer Agent.

Task:
{task["title"]}

Description:
{task.get("description", "")}

Failure snapshot:
{failure_snapshot}

Your job:
- identify the root cause
- suggest the smallest safe fix
- do not rewrite architecture
- do not change unrelated files

Reply strictly in this format:

STATUS:
FIX_SUMMARY:
FILES_TO_CHANGE:
CODE_CHANGES:
RISKS:
"""


def call_llm(prompt: str) -> str:
    return generate_text(prompt)
