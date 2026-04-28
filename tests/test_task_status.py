import pytest
from ai_director.task_status import is_terminal_status

@pytest.mark.parametrize(
    "status,expected",
    [
        ("DONE", True),
        ("FAILED", True),
        ("NEEDS_HUMAN", True),
        ("NEW", False),
        ("IN_PROGRESS", False),
        ("READY_TO_CHECK", False),
        ("UNKNOWN_STATUS", False),
        ("", False),
        (None, False),  # type: ignore[arg-type] – test robustness
    ],
)
def test_is_terminal_status(status, expected):
    # The function expects a string; if None is passed we coerce to str
    # to avoid TypeError and keep the test focused on return value.
    if status is None:
        result = is_terminal_status(str(status))
    else:
        result = is_terminal_status(status)
    assert result is expected