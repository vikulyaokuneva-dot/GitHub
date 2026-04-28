from __future__ import annotations

import json

from ai_director.apply_engine import parse_llm_response


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
