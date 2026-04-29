import pytest
from ai_director.run_summary import format_run_summary


def test_format_run_summary_no_files_no_violations():
    summary = format_run_summary(
        task_id="task-123",
        status="success",
        run_dir="/tmp/run1",
        applied_files=[],
        violations=[],
    )
    expected = (
        "Run Summary for task 'task-123'\n"
        "Status      : success\n"
        "Run directory: /tmp/run1\n"
        "\n"
        "Applied files:\n"
        "  (none)\n"
        "\n"
        "Violations:\n"
        "  (none)"
    )
    assert summary == expected


def test_format_run_summary_with_data():
    summary = format_run_summary(
        task_id="t42",
        status="failed",
        run_dir="/var/run/t42",
        applied_files=["a.py", "b.txt"],
        violations=[
            {"type": "error", "message": "Something went wrong"},
            {"type": "warning", "message": "Potential issue"},
        ],
    )
    expected = (
        "Run Summary for task 't42'\n"
        "Status      : failed\n"
        "Run directory: /var/run/t42\n"
        "\n"
        "Applied files:\n"
        "  - a.py\n"
        "  - b.txt\n"
        "\n"
        "Violations:\n"
        "  1. [error] Something went wrong\n"
        "  2. [warning] Potential issue"
    )
    assert summary == expected
