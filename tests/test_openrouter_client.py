from __future__ import annotations

import os
from typing import Any

from ai_director import orchestrator
from src import openrouter_client


class DummyResponse:
    def __init__(self, status_code: int, text: str = "", payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload


def test_default_model_chain_includes_requested_fallbacks(monkeypatch) -> None:
    monkeypatch.delenv("AI_DIRECTOR_MODEL", raising=False)
    monkeypatch.delenv("AI_DIRECTOR_MODEL_FALLBACKS", raising=False)

    assert openrouter_client._model_chain() == [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "mistralai/mistral-7b-instruct",
    ]


def test_generate_text_result_tries_next_model_after_503(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("AI_DIRECTOR_MODEL", raising=False)
    monkeypatch.delenv("AI_DIRECTOR_MODEL_FALLBACKS", raising=False)

    responses = [
        DummyResponse(503, "Provider returned error"),
        DummyResponse(200, payload={"choices": [{"message": {"content": "fallback ok"}}]}),
    ]
    requested_models: list[str] = []

    def fake_post(*_args: Any, **kwargs: Any) -> DummyResponse:
        requested_models.append(kwargs["json"]["model"])
        return responses.pop(0)

    monkeypatch.setattr(openrouter_client.requests, "post", fake_post)

    result = openrouter_client.generate_text_result("prompt")

    assert result["ok"] is True
    assert result["text"] == "fallback ok"
    assert result["selected_model"] == "qwen/qwen3-next-80b-a3b-instruct:free"
    assert result["attempted_models"] == [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
    ]
    assert requested_models == result["attempted_models"]


def test_generate_text_result_tries_next_model_after_provider_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_DIRECTOR_MODEL", "primary-model")
    monkeypatch.setenv("AI_DIRECTOR_MODEL_FALLBACKS", "fallback-model")

    responses = [
        DummyResponse(400, "Provider returned error: overloaded"),
        DummyResponse(200, payload={"choices": [{"message": {"content": "provider fallback ok"}}]}),
    ]

    def fake_post(*_args: Any, **_kwargs: Any) -> DummyResponse:
        return responses.pop(0)

    monkeypatch.setattr(openrouter_client.requests, "post", fake_post)

    result = openrouter_client.generate_text_result("prompt")

    assert result["ok"] is True
    assert result["text"] == "provider fallback ok"
    assert result["selected_model"] == "fallback-model"
    assert result["attempted_models"] == ["primary-model", "fallback-model"]


def test_orchestrator_passes_default_fallbacks_to_openrouter_client(monkeypatch) -> None:
    monkeypatch.delenv("AI_DIRECTOR_MODEL", raising=False)
    monkeypatch.delenv("AI_DIRECTOR_MODEL_FALLBACKS", raising=False)
    monkeypatch.setattr(orchestrator, "load_env_config", lambda: {"OPENROUTER_API_KEY": "test-key"})
    monkeypatch.setattr(orchestrator, "log_event", lambda *_args, **_kwargs: None)

    captured_env: dict[str, str] = {}

    def fake_generate_text_result(_prompt: str) -> dict[str, Any]:
        captured_env["model"] = os.environ["AI_DIRECTOR_MODEL"]
        captured_env["fallbacks"] = os.environ["AI_DIRECTOR_MODEL_FALLBACKS"]
        return {
            "ok": True,
            "final_status": "ok",
            "status": "ok",
            "attempted_models": ["openai/gpt-oss-120b:free"],
            "selected_model": "openai/gpt-oss-120b:free",
            "text": "ok",
            "last_error": "",
            "error": "",
            "errors": [],
        }

    monkeypatch.setattr(orchestrator, "generate_text_result", fake_generate_text_result)

    result = orchestrator._call_llm("prompt")

    assert result["ok"] is True
    assert captured_env == {
        "model": "openai/gpt-oss-120b:free",
        "fallbacks": "qwen/qwen3-next-80b-a3b-instruct:free,mistralai/mistral-7b-instruct",
    }
