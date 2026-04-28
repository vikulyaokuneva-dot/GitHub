import re
import shutil
from ai_director.logger import log_event, _LOG_FILE, _LOG_DIR


def setup_function():
    # очищаем логи перед каждым тестом
    if _LOG_DIR.exists():
        shutil.rmtree(_LOG_DIR)


def test_log_event_writes_file():
    log_event("hello")

    assert _LOG_FILE.exists()

    content = _LOG_FILE.read_text(encoding="utf-8")
    assert "hello" in content


def test_log_event_format():
    log_event("test")

    line = _LOG_FILE.read_text(encoding="utf-8").strip()

    pattern = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] test$"
    assert re.match(pattern, line)