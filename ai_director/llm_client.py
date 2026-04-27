from __future__ import annotations

from pathlib import Path


def generate_fix_prompt(task: dict, failure_snapshot: dict) -> str:
    _ = Path
    return f"""
Ты Fixer Agent.

Задача:
{task["title"]}

Описание:
{task.get("description", "")}

Ошибки:
{failure_snapshot}

Твоя задача:
- определить причину ошибки
- предложить минимальный фикс
- не переписывать архитектуру
- не менять лишние файлы

Ответ строго в формате:

STATUS:
FIX_SUMMARY:
FILES_TO_CHANGE:
CODE_CHANGES:
RISKS:
"""


def call_llm(prompt: str) -> str:
    _ = prompt
    return "MOCK_RESPONSE: LLM not connected yet"
