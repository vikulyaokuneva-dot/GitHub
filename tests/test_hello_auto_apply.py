from ai_director.hello_auto_apply import get_status


def test_get_status() -> None:
    assert get_status() == "AI Director auto apply works"