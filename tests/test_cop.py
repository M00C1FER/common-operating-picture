"""Smoke tests for common-operating-picture."""
import tempfile
from pathlib import Path
import pytest


def test_import():
    from common_operating_picture import COP
    assert COP


def test_register_and_clear():
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        cop = COP(state_file=str(Path(d) / "state.json"))
        cop.register_task("agent-x", "test task")
        status = cop.status()
        assert "agent-x" in str(status)
        cop.clear_task("agent-x")


def test_blackboard_share():
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        cop = COP(state_file=str(Path(d) / "state.json"))
        cop.share("key1", {"value": 42})
        result = cop.get_shared("key1")
        assert result["value"] == 42


def test_lock_and_unlock():
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        cop = COP(state_file=str(Path(d) / "state.json"))
        acquired = cop.lock_resource("agent-y", "file.db")
        assert acquired
        cop.unlock_resource("agent-y", "file.db")
