from __future__ import annotations

import json
import urllib.error
import urllib.request

try:
    from .config import LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, LOCAL_LLM_TIMEOUT_SEC
except ImportError:
    from config import LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, LOCAL_LLM_TIMEOUT_SEC


LOCAL_LLM_FALLBACK_RESPONSE = (
    "MOCK_RESPONSE: Local LLM is not available. Start Ollama and pull the configured model."
)


def generate_fix_prompt(task: dict, failure_snapshot: dict) -> str:
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
    endpoint = f"{LOCAL_LLM_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=LOCAL_LLM_TIMEOUT_SEC) as response:
            raw_body = response.read().decode("utf-8")
        data = json.loads(raw_body)
        llm_response = data.get("response")
        if isinstance(llm_response, str) and llm_response.strip():
            return llm_response
        return LOCAL_LLM_FALLBACK_RESPONSE
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return LOCAL_LLM_FALLBACK_RESPONSE
