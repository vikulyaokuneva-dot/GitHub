import pytest
from pathlib import Path

from ai_director.config import load_env_config


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    # подменяем project_root на временную папку
    monkeypatch.setattr("ai_director.config._project_root", lambda: tmp_path)
    return tmp_path


def test_parsing(temp_root):
    (temp_root / ".env").write_text(
        """
        DATABASE_URL=postgres://localhost/db
        DEBUG = True
        TIMEOUT= 30
        """
    )

    cfg = load_env_config()

    assert cfg == {
        "DATABASE_URL": "postgres://localhost/db",
        "DEBUG": "True",
        "TIMEOUT": "30",
    }


def test_ignore_comments(temp_root):
    (temp_root / ".env").write_text(
        """
        # comment
        API_KEY=123
        # comment
        """
    )

    cfg = load_env_config()

    assert cfg == {"API_KEY": "123"}


def test_ignore_empty_lines(temp_root):
    (temp_root / ".env").write_text(
        """

        KEY=VALUE

        """
    )

    cfg = load_env_config()

    assert cfg == {"KEY": "VALUE"}


def test_missing_file(temp_root):
    cfg = load_env_config()
    assert cfg == {}