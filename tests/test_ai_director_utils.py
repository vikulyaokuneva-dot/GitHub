import pytest
from ai_director.utils import normalize_task_title


@pytest.mark.parametrize(
    "input_title,expected",
    [
        ("My New Task!!!", "my new task"),
        ("Task_Example-01 @#$%", "task_example-01"),
        ("   Lots    of    spaces   ", "lots of spaces"),
        ("", "task"),
        (None, "task"),
        ("!!!@@@", "task"),
        ("TASK management", "task management"),
        ("a" * 101, "a" * 100),
        ("Task " + "b" * 95 + " extra text", "task " + "b" * 95),
    ],
)
def test_normalize_task_title(input_title, expected):
    assert normalize_task_title(input_title) == expected