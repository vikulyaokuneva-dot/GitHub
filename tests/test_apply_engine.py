from __future__ import annotations

import json

from ai_director.apply_engine import parse_auto_apply_json_response, parse_llm_response


def test_parse_llm_response_adds_upsert_for_codex_file_format() -> None:
    response = json.dumps(
        {
            "mode": "auto_apply_draft",
            "ok": True,
            "files": [
                {
                    "path": "x.py",
                    "language": "python",
                    "content": "print(1)\n",
                }
            ],
        }
    )

    parsed = parse_llm_response(response)

    assert parsed["ok"] is True
    assert parsed["files"][0]["operation"] == "upsert"
    assert parsed["files"][0]["path"] == "x.py"
    assert parsed["files"][0]["content"] == "print(1)\n"


def test_parse_auto_apply_json_response_accepts_strict_json() -> None:
    response = json.dumps(
        {
            "files": [
                {
                    "path": "ai_director/task_status.py",
                    "operation": "upsert",
                    "content": "VALUE = 1\n",
                }
            ]
        }
    )

    parsed = parse_auto_apply_json_response(response)

    assert parsed["ok"] is True
    assert parsed["files"] == [
        {
            "path": "ai_director/task_status.py",
            "operation": "upsert",
            "content": "VALUE = 1\n",
        }
    ]


def test_parse_auto_apply_json_response_rejects_markdown() -> None:
    parsed = parse_auto_apply_json_response("# Summary\n\n# Code\n")

    assert parsed["ok"] is False
    assert parsed["reason"] == "invalid_format"
    assert parsed["files"] == []
