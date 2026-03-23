import os
import json
from typing import Optional, List

try:
    from gigachat import GigaChat
    from gigachat.exceptions import NotFoundError
except Exception:
    GigaChat = None
    NotFoundError = Exception


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def generate_report_from_facts(prompt: str) -> str:
    credentials = os.environ.get("GIGACHAT_AUTH_KEY", "").strip()

    # ✅ Fallback без GigaChat
    if not credentials or GigaChat is None:
        return json.dumps({
            "status": "no_gigachat",
            "data": {
                "report": prompt
            }
        }, ensure_ascii=False)

    timeout_sec = int(os.getenv("GIGACHAT_TIMEOUT_SEC", "60"))
    primary_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2").strip() or "GigaChat-2"

    candidates: List[str] = [primary_model]
    if "GigaChat" not in candidates:
        candidates.append("GigaChat")

    verify_ssl_certs = _env_bool("GIGACHAT_VERIFY_SSL_CERTS", default=False)

    last_error: Optional[Exception] = None

    for model_name in candidates:
        client: Optional[GigaChat] = None
        try:
            client = GigaChat(
                credentials=credentials,
                verify_ssl_certs=verify_ssl_certs,
                model=model_name,
                timeout=timeout_sec,
            )

            response = client.chat(prompt)

            # ⚠️ ВАЖНО: тоже приводим к JSON
            return json.dumps({
                "status": "ok",
                "data": {
                    "report": response.choices[0].message.content
                }
            }, ensure_ascii=False)

        except Exception as e:
            last_error = e
            continue
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    # ✅ fallback при ошибке API
    return json.dumps({
        "status": "error",
        "error": str(last_error),
        "data": {
            "report": prompt
        }
    }, ensure_ascii=False)