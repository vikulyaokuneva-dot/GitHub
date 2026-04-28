from __future__ import annotations

from ai_director.orchestrator import apply_coder_output, parse_coder_output


def test_parse_coder_output_single_file() -> None:
    markdown = """# Summary
Draft.

# Code

## ai_director/logger.py
```python
def log_event(message: str) -> None:
    pass
```

# Tests
Run tests.
"""

    assert parse_coder_output(markdown) == [
        {
            "path": "ai_director/logger.py",
            "language": "python",
            "content": "def log_event(message: str) -> None:\n    pass",
        }
    ]


def test_parse_coder_output_two_files() -> None:
    markdown = """# Code

## ai_director/logger.py
```python
LOGGER = True
```

## tests/test_logger.py
```python
def test_logger():
    assert True
```
"""

    blocks = parse_coder_output(markdown)

    assert [block["path"] for block in blocks] == [
        "ai_director/logger.py",
        "tests/test_logger.py",
    ]
    assert [block["language"] for block in blocks] == ["python", "python"]


def test_apply_coder_output_rejects_parent_reference(tmp_path) -> None:
    markdown = """# Code

## ../outside.py
```python
VALUE = 1
```
"""

    result = apply_coder_output(markdown, project_root=tmp_path)

    assert result["ok"] is False
    assert result["applied_files"] == []
    assert result["violations"] == [{"path": "../outside.py", "reason": "parent_reference"}]
    assert not (tmp_path.parent / "outside.py").exists()


def test_apply_coder_output_rejects_env_file(tmp_path) -> None:
    markdown = """# Code

## .env
```text
SECRET=1
```
"""

    result = apply_coder_output(markdown, project_root=tmp_path)

    assert result["ok"] is False
    assert result["applied_files"] == []
    assert result["violations"] == [{"path": ".env", "reason": "forbidden_path"}]
    assert not (tmp_path / ".env").exists()


def test_apply_coder_output_creates_new_file(tmp_path) -> None:
    markdown = """# Code

## ai_director/logger.py
```python
def log_event(message: str) -> None:
    print(message)
```
"""

    result = apply_coder_output(markdown, project_root=tmp_path)

    assert result["ok"] is True
    assert result["applied_files"] == ["ai_director/logger.py"]
    assert (tmp_path / "ai_director" / "logger.py").is_file()


def test_apply_coder_output_writes_exact_content(tmp_path) -> None:
    content = "def normalize_task_title(title: str) -> str:\n    return title.strip() or 'task'"
    markdown = f"""# Code

## ai_director/utils.py
```python
{content}
```
"""

    result = apply_coder_output(markdown, project_root=tmp_path)

    assert result["ok"] is True
    assert (tmp_path / "ai_director" / "utils.py").read_text(encoding="utf-8") == content
