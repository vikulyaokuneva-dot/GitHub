import os
import requests


API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3-coder:free"


def generate_text(prompt: str, system: str | None = None):
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return "ERROR: no OPENROUTER_API_KEY"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/vikulyaokuneva-dot/GitHub",
        "X-Title": "AI Director WB",
    }

    data = {
        "model": os.getenv("AI_DIRECTOR_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": system or "Ты полезный ассистент."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=60)

        if response.status_code != 200:
            return f"ERROR HTTP {response.status_code}: {response.text}"

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        return f"ERROR: {str(e)}"


if __name__ == "__main__":
    print(generate_text("Ответь одним словом: OK"))
