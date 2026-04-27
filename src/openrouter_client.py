import json
import os
from typing import Any

import requests


API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3-coder:free"
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_MAX_TOKENS = 200
DEFAULT_TEMPERATURE = 0.2


def generate_text(prompt: str, system: str | None = None, **kwargs: Any) -> str:
    result = generate_text_result(prompt, system=system, **kwargs)
    if result.get("ok"):
        return str(result.get("text") or "")
    return str(result.get("last_error") or result.get("error") or "ERROR: OpenRouter request failed")


def generate_text_result(prompt: str, system: str | None = None, **kwargs: Any) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    models = _model_chain()

    if not api_key:
        return _result(
            ok=False,
            final_status="no_llm",
            attempted_models=[],
            selected_model="",
            text="ERROR: no OPENROUTER_API_KEY",
            last_error="ERROR: no OPENROUTER_API_KEY",
            errors=[],
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/vikulyaokuneva-dot/GitHub",
        "X-Title": "AI Director WB",
    }

    attempted_models: list[str] = []
    errors: list[dict[str, Any]] = []
    last_error = ""
    timeout = int(kwargs.get("timeout", DEFAULT_TIMEOUT_SEC))
    max_tokens = int(kwargs.get("max_tokens", DEFAULT_MAX_TOKENS))
    temperature = float(kwargs.get("temperature", DEFAULT_TEMPERATURE))

    for model in models:
        attempted_models.append(model)
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system or "Ты полезный ассистент."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=timeout)
        except requests.exceptions.Timeout as exc:
            last_error = f"ERROR timeout for {model}: {exc}"
            errors.append({"model": model, "status_code": None, "error": last_error, "retryable": True})
            continue
        except requests.exceptions.RequestException as exc:
            last_error = f"ERROR request for {model}: {exc}"
            errors.append({"model": model, "status_code": None, "error": last_error, "retryable": True})
            continue

        if response.status_code == 200:
            try:
                result = response.json()
                text = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = f"ERROR malformed OpenRouter response for {model}: {exc}"
                errors.append({"model": model, "status_code": 200, "error": last_error, "retryable": True})
                continue

            if isinstance(text, str) and text.strip():
                return _result(
                    ok=True,
                    final_status="ok",
                    attempted_models=attempted_models,
                    selected_model=model,
                    text=text,
                    last_error=last_error,
                    errors=errors,
                )

            last_error = f"ERROR empty OpenRouter response for {model}"
            errors.append({"model": model, "status_code": 200, "error": last_error, "retryable": True})
            continue

        body = response.text
        last_error = f"ERROR HTTP {response.status_code} for {model}: {body}"
        retryable = _should_try_next_model(response.status_code, body)
        errors.append(
            {
                "model": model,
                "status_code": response.status_code,
                "error": last_error,
                "retryable": retryable,
            }
        )
        if retryable:
            continue

        return _result(
            ok=False,
            final_status=_status_from_http_error(response.status_code),
            attempted_models=attempted_models,
            selected_model="",
            text=last_error,
            last_error=last_error,
            errors=errors,
        )

    return _result(
        ok=False,
        final_status="api_error",
        attempted_models=attempted_models,
        selected_model="",
        text=last_error or "ERROR: all OpenRouter models failed",
        last_error=last_error or "ERROR: all OpenRouter models failed",
        errors=errors,
    )


def _model_chain() -> list[str]:
    primary = os.getenv("AI_DIRECTOR_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    raw_fallbacks = os.getenv("AI_DIRECTOR_MODEL_FALLBACKS", "")
    candidates = [primary]
    candidates.extend(item.strip() for item in raw_fallbacks.split(",") if item.strip())

    models: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        if model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models or [DEFAULT_MODEL]


def _should_try_next_model(status_code: int, body: str) -> bool:
    if status_code == 429 or 500 <= status_code <= 599:
        return True
    if status_code in {400, 404}:
        normalized = body.lower()
        return (
            "invalid model" in normalized
            or ("model" in normalized and "not found" in normalized)
            or "no endpoints" in normalized
        )
    return False


def _status_from_http_error(status_code: int) -> str:
    if status_code in {401, 403}:
        return "no_llm"
    return "api_error"


def _result(
    *,
    ok: bool,
    final_status: str,
    attempted_models: list[str],
    selected_model: str,
    text: str,
    last_error: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": ok,
        "final_status": final_status,
        "status": final_status,
        "attempted_models": attempted_models,
        "selected_model": selected_model,
        "text": text,
        "last_error": last_error,
        "error": "" if ok else last_error,
        "errors": errors,
    }


if __name__ == "__main__":
    smoke_result = generate_text_result("Ответь одним словом: OK")
    print(json.dumps(smoke_result, ensure_ascii=False, indent=2))
