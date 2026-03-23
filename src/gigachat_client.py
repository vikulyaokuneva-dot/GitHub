import os
import json
from typing import Optional, List

try:
    from gigachat import GigaChat
    from gigachat.exceptions import NotFoundError
except Exception:
    GigaChat = None
    NotFoundError = Exception


def generate_report_from_facts(prompt: str) -> str:
    credentials = os.environ.get("GIGACHAT_AUTH_KEY", "").strip()

    # fallback
    if not credentials or GigaChat is None:
        return json.dumps({
            "status": "no_gigachat",
            "data": {"report": prompt}
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "data": {"report": prompt}
    }, ensure_ascii=False)