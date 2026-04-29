import pytest
from ai_director.task_status import TaskStatus, normalize_status


def test_task_status_list():
    assert set(TaskStatus.list()) == {"NEW", "IN_PROGRESS", "DONE", "FAILED"}


@pytest.mark.parametrize(
    "input_status,expected",
    [
        ("new", "NEW"),
        ("  in_progress  ", "IN_PROGRESS"),
        ("Done", "DONE"),
        ("failed", "FAILED"),
        ("", "NEW"),
        ("   ", "NEW"),
        (None, "NEW"),
    ],
)
def test_normalize_status(input_status, expected):
    assert normalize_status(input_status) == expected
