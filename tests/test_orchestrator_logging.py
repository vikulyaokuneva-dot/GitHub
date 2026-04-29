import builtins
import types
from unittest import mock

import pytest

from ai_director import orchestrator


class DummyLogger:
    def __init__(self):
        self.events = []
        self.infos = []
        self.exceptions = []

    def info(self, msg):
        self.infos.append(msg)

    def exception(self, msg):
        self.exceptions.append(msg)

    def log_event(self, event_type, payload):
        self.events.append((event_type, payload))


def test_run_task_success(monkeypatch):
    dummy = DummyLogger()
    # Patch logger and log_event used in orchestrator
    monkeypatch.setattr(orchestrator, "logger", dummy)
    monkeypatch.setattr(orchestrator, "log_event", dummy.log_event)

    # Stub the internal _execute to return a known value
    monkeypatch.setattr(orchestrator, "_execute", lambda name, *a, **k: "ok")

    result = orchestrator.run_task("sample")
    assert result == "ok"
    # Verify logging calls
    assert any(e[0] == "task_start" for e in dummy.events)
    assert any(e[0] == "task_success" for e in dummy.events)
    assert not dummy.exceptions


def test_run_task_error(monkeypatch):
    dummy = DummyLogger()
    monkeypatch.setattr(orchestrator, "logger", dummy)
    monkeypatch.setattr(orchestrator, "log_event", dummy.log_event)

    # Force _execute to raise
    def raise_error(*a, **k):
        raise ValueError("boom")
    monkeypatch.setattr(orchestrator, "_execute", raise_error)

    with pytest.raises(ValueError):
        orchestrator.run_task("fail")

    # Verify error logging
    assert any(e[0] == "task_start" for e in dummy.events)
    assert any(e[0] == "task_error" for e in dummy.events)
    assert dummy.exceptions
