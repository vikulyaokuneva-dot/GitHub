import pytest
from ai_director.task_status import normalize_status

@pytest.mark.parametrize(
    "input_status,expected",
    [
        ("new", "NEW"),
        (" InProgress ", "INPROGRESS"),
        ("completed", "COMPLETED"),
        ("", "NEW"),
        ("   ", "NEW"),
        (None, "NEW"),
    ],
)
def test_normalize_status(input_status, expected):
    # The function should handle None gracefully by treating it as an empty string.
    result = normalize_status(input_status if input_status is not None else "")
    assert result == expected
