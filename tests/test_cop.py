"""Smoke tests for common-operating-picture."""
import json
import multiprocessing
import subprocess
import sys
import tempfile
import time
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


# ── New audit tests ──────────────────────────────────────────────────────────

def test_lock_denied_for_other_agent():
    """A second agent cannot acquire a resource already held by another."""
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        sf = str(Path(d) / "state.json")
        cop_a = COP(state_file=sf)
        cop_b = COP(state_file=sf)
        assert cop_a.lock_resource("agent-a", "shared.db") is True
        assert cop_b.lock_resource("agent-b", "shared.db") is False


def test_same_agent_reacquire_lock():
    """The same agent may re-acquire (update timestamp on) a lock it holds."""
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        cop = COP(state_file=str(Path(d) / "state.json"))
        assert cop.lock_resource("agent-a", "res") is True
        assert cop.lock_resource("agent-a", "res") is True


def test_unlock_by_non_owner_is_noop():
    """Unlocking a resource you don't own is a no-op — owner's lock survives."""
    from common_operating_picture import COP
    with tempfile.TemporaryDirectory() as d:
        sf = str(Path(d) / "state.json")
        cop_a = COP(state_file=sf)
        cop_b = COP(state_file=sf)
        cop_a.lock_resource("agent-a", "res")
        cop_b.unlock_resource("agent-b", "res")  # should be ignored
        # agent-b still can't acquire it
        assert cop_b.lock_resource("agent-b", "res") is False


def _worker_lock(state_file: str, agent_name: str, resource: str, result_queue):
    """Subprocess worker: try to acquire a lock and report result."""
    from common_operating_picture import COP
    cop = COP(state_file=state_file)
    ok = cop.lock_resource(agent_name, resource)
    result_queue.put((agent_name, ok))


def test_concurrent_lock_only_one_wins():
    """Two processes racing for the same resource: exactly one wins."""
    with tempfile.TemporaryDirectory() as d:
        sf = str(Path(d) / "state.json")
        q = multiprocessing.Queue()
        p1 = multiprocessing.Process(
            target=_worker_lock, args=(sf, "agent-1", "race.db", q)
        )
        p2 = multiprocessing.Process(
            target=_worker_lock, args=(sf, "agent-2", "race.db", q)
        )
        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        assert p1.exitcode == 0, f"p1 did not exit cleanly: {p1.exitcode}"
        assert p2.exitcode == 0, f"p2 did not exit cleanly: {p2.exitcode}"

        results = {}
        while not q.empty():
            agent, ok = q.get()
            results[agent] = ok

        assert len(results) == 2, "Both workers should have reported"
        # Exactly one should have won
        wins = sum(1 for v in results.values() if v)
        assert wins == 1, f"Expected exactly 1 winner, got {results}"


def test_stale_lock_cleaned_by_timeout():
    """A lock older than the stale threshold is removed by _clean_stale."""
    from common_operating_picture import COP
    from common_operating_picture.cop import _get_timeouts
    _task_t, lock_t, _bounty_t = _get_timeouts()
    _STALE_MARGIN_SECS = 60  # safety margin beyond the stale window
    with tempfile.TemporaryDirectory() as d:
        sf = str(Path(d) / "state.json")
        cop = COP(state_file=sf)
        cop.lock_resource("crashed-agent", "stale.db")

        # Manually backdate the lock entry past the stale threshold
        state_path = Path(sf)
        state = json.loads(state_path.read_text())
        state["locks"]["stale.db"]["timestamp"] = time.time() - (lock_t + _STALE_MARGIN_SECS)
        state_path.write_text(json.dumps(state))

        # Now another agent should be able to acquire it (stale cleaned on lock)
        cop2 = COP(state_file=sf)
        ok = cop2.lock_resource("new-agent", "stale.db")
        assert ok, "Should acquire after stale lock is cleaned"


def test_cli_version():
    """cop --version returns a version string matching semver."""
    from common_operating_picture import __version__
    result = subprocess.run(
        [sys.executable, "-m", "common_operating_picture", "--version"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_cli_status_empty(tmp_path):
    """cop status on a fresh state file reports no active tasks."""
    env = {"COP_STATE_FILE": str(tmp_path / "state.json")}
    import os
    full_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, "-m", "common_operating_picture", "status"],
        capture_output=True, text=True, env=full_env
    )
    assert result.returncode == 0
    assert "No active tasks" in result.stdout


def test_cli_register_and_lock(tmp_path):
    """CLI register + lock + unlock + clear round-trip."""
    sf = str(tmp_path / "state.json")
    import os
    env = {**os.environ, "COP_STATE_FILE": sf}

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "common_operating_picture", *args],
            capture_output=True, text=True, env=env
        )

    assert run("register", "--cli", "ci", "--task", "test").returncode == 0
    assert run("lock", "res.db", "--cli", "ci").returncode == 0
    assert run("unlock", "res.db", "--cli", "ci").returncode == 0
    assert run("clear", "--cli", "ci").returncode == 0

