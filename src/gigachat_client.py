import os
from typing import Optional, List

from gigachat import GigaChat
from gigachat.exceptions import NotFoundError


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def generate_report_from_facts(prompt: str) -> str:
    """
    Генерирует текст отчёта через официальный SDK GigaChat.

    ВАЖНО (PoC):
    - verify_ssl_certs=False отключает проверку SSL цепочки (в GitHub Actions часто нужно).
      В проде лучше сделать verify_ssl_certs=True и настроить доверенный CA.
    """
    credentials = os.environ.get("GIGACHAT_AUTH_KEY", "").strip()
    if not credentials:
        raise RuntimeError("GIGACHAT_AUTH_KEY is missing in environment")

    timeout_sec = int(os.getenv("GIGACHAT_TIMEOUT_SEC", "60"))

    # Как в твоём примере из другого репо:
    # основная модель может быть "GigaChat-2", запасная — "GigaChat"
    primary_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2").strip() or "GigaChat-2"
    candidates: List[str] = [primary_model]
    if "GigaChat" not in candidates:
        candidates.append("GigaChat")

    # Для PoC оставим отключение SSL, как в примере
    verify_ssl_certs = _env_bool("GIGACHAT_VERIFY_SSL_CERTS", default=False)

    last_error: Optional[Exception] = None

    for model_name in candidates:
        client: Optional[GigaChat] = None
        try:
            client = GigaChat(
                credentials=credentials,
                verify_ssl_certs=verify_ssl_certs,  # <-- ключевой параметр
                model=model_name,
                timeout=timeout_sec,
            )

            response = client.chat(prompt)
            return response.choices[0].message.content

        except NotFoundError as e:
            # модель не найдена — пробуем следующую
            last_error = e
            continue
        except Exception as e:
            # любая другая ошибка — пробуем следующий candidate
            last_error = e
            continue
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    raise RuntimeError(f"GigaChat failed for all models. Last error: {last_error}")
