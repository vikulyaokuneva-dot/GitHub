from __future__ import annotations

import json

from ai_director import orchestrator
from ai_director.orchestrator import (
    _build_auto_apply_diff,
    _build_auto_apply_json_prompt,
    _run_auto_apply_draft_task,
    apply_auto_apply_files,
    apply_coder_output,
    parse_coder_output,
)


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


def test_parse_coder_output_keeps_hash_comments_inside_code_section() -> None:
    markdown = """# Code

## ai_director/task_status.py
```python
# Keep this comment inside the code block.
def is_terminal_status(status: str) -> bool:
    return status in {"DONE", "FAILED", "NEEDS_HUMAN"}
```

# Tests
Run pytest.
"""

    blocks = parse_coder_output(markdown)

    assert blocks == [
        {
            "path": "ai_director/task_status.py",
            "language": "python",
            "content": (
                "# Keep this comment inside the code block.\n"
                "def is_terminal_status(status: str) -> bool:\n"
                '    return status in {"DONE", "FAILED", "NEEDS_HUMAN"}'
            ),
        }
    ]


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


def test_auto_apply_real_upsert_creates_well_formed_diff(tmp_path) -> None:
    path = "ai_director/hello_auto_apply.py"
    blocks = [
        {
            "path": path,
            "language": "python",
            "content": "def get_status() -> str:\n    return 'ok'\n",
        }
    ]

    diff_text = _build_auto_apply_diff(blocks, project_root=tmp_path)
    result = apply_coder_output(
        """# Code

## ai_director/hello_auto_apply.py
```python
def get_status() -> str:
    return 'ok'
```
""",
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert f"--- a/{path}\n" in diff_text
    assert f"+++ b/{path}\n" in diff_text
    assert "@@" in diff_text
    assert f"--- a/{path}+++ b/{path}@@" not in diff_text


def test_apply_auto_apply_files_writes_strict_json_files(tmp_path) -> None:
    files = [
        {
            "path": "ai_director/task_status.py",
            "operation": "upsert",
            "content": "def is_terminal_status(status: str) -> bool:\n    return status == 'DONE'\n",
        }
    ]

    result = apply_auto_apply_files(files, project_root=tmp_path)

    assert result["ok"] is True
    assert result["applied_files"] == ["ai_director/task_status.py"]
    assert (tmp_path / "ai_director" / "task_status.py").read_text(encoding="utf-8") == files[0]["content"]


def test_apply_auto_apply_files_rejects_destructive_line_removal(tmp_path) -> None:
    target = tmp_path / "ai_director" / "existing.py"
    target.parent.mkdir(parents=True)
    original = "value = 1\nvalue += 1\nvalue += 1\nvalue += 1\nvalue += 1\n"
    target.write_text(original, encoding="utf-8")

    result = apply_auto_apply_files(
        [
            {
                "path": "ai_director/existing.py",
                "operation": "upsert",
                "content": "value = 1\nvalue += 1\n",
            }
        ],
        project_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["applied_files"] == []
    assert result["violations"] == [{"path": "ai_director/existing.py", "reason": "destructive_update"}]
    assert target.read_text(encoding="utf-8") == original


def test_auto_apply_json_prompt_uses_strict_json_contract() -> None:
    prompt = _build_auto_apply_json_prompt(
        {
            "title": "Add helper",
            "prompt": "Create ai_director/task_status.py and tests/test_task_status.py.",
        }
    )

    lowered = prompt.lower()

    assert "summary" not in lowered
    assert "instructions" not in lowered
    assert "explain" not in lowered
    assert "return only one json object" in lowered
    assert '"operation": "upsert"' in prompt


def test_auto_apply_markdown_llm_response_writes_raw_and_needs_human(tmp_path, monkeypatch) -> None:
    task = {
        "id": "strict_json_invalid",
        "title": "Invalid format",
        "prompt": "Create a file.",
        "mode": "auto_apply_draft",
        "status": "NEW",
        "iterations": 0,
        "max_iterations": 1,
    }
    tasks_payload = {"tasks": [task]}

    monkeypatch.setattr(orchestrator, "save_tasks", lambda payload: None)
    monkeypatch.setattr(orchestrator, "log_event", lambda message: None)
    monkeypatch.setattr(
        orchestrator,
        "_call_llm",
        lambda prompt: {
            "ok": True,
            "status": "ok",
            "final_status": "ok",
            "provider": "test",
            "model": "test",
            "configured_model": "test",
            "attempted_models": ["test"],
            "selected_model": "test",
            "text": "# Summary\n\n# Code\n",
            "error": "",
            "last_error": "",
            "errors": [],
        },
    )

    exit_code = _run_auto_apply_draft_task(
        task=task,
        tasks_payload=tasks_payload,
        task_id="strict_json_invalid",
        run_dir=tmp_path,
        coder_prompt="Return only JSON.",
        coder_context=None,
    )

    assert exit_code == 1
    assert task["status"] == "NEEDS_HUMAN"
    assert (tmp_path / "llm_raw_response.txt").read_text(encoding="utf-8") == "# Summary\n\n# Code\n"
    apply_result = json.loads((tmp_path / "apply_result.json").read_text(encoding="utf-8"))
    assert apply_result["violations"] == [{"path": "", "reason": "invalid_format"}]
