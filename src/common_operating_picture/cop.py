import atexit
import json
import os
import tempfile
import time
import fcntl
from pathlib import Path
from typing import List, Tuple

COP_HOME = Path(os.environ.get("COP_HOME", os.path.expanduser("~/.common-operating-picture")))
COP_FILE = Path(os.environ.get("COP_STATE_FILE", str(COP_HOME / "cop_state.json")))

def _atomic_write_cop(state: dict) -> None:
    """Write COP state atomically via temp file + rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=COP_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp_path, COP_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def _init_cop() -> None:
    if not COP_FILE.exists():
        COP_FILE.parent.mkdir(parents=True, exist_ok=True)
        COP_FILE.write_text(json.dumps({"tasks": {}, "locks": {}, "bounties": {}}))

def _get_timeouts() -> Tuple[int, int, int]:
    try:
        import yaml
        config_path = os.path.expanduser("${COP_CONFIG}")
        with open(config_path) as f:
            gov = yaml.safe_load(f)
        timeouts = gov.get("observability", {}).get("cop", {}).get("timeouts", {})
        return (
            timeouts.get("task_sec", 7200),
            timeouts.get("lock_sec", 7200),
            timeouts.get("bounty_sec", 86400)
        )
    except Exception:
        return 7200, 7200, 86400

def _clean_stale(state) -> None:
    now = time.time()
    task_t, lock_t, bounty_t = _get_timeouts()
    for c in list(state.get("tasks", {}).keys()):
        if now - state["tasks"][c]["timestamp"] > task_t:
            del state["tasks"][c]
    for r in list(state.get("locks", {}).keys()):
        if now - state["locks"][r]["timestamp"] > lock_t:
            del state["locks"][r]
    for b in list(state.get("bounties", {}).keys()):
        if now - state["bounties"][b]["timestamp"] > bounty_t: # 24 hours
            del state["bounties"][b]

def register_task(cli_name: str, task_description: str) -> str:
    """Registers the active task for a specific CLI."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            _clean_stale(state)
            state.setdefault("tasks", {})[cli_name] = {
                "description": task_description,
                "timestamp": time.time()
            }
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"Task registered for {cli_name}"

def clear_task(cli_name: str) -> str:
    """Clears the active task for a specific CLI."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            if cli_name in state.get("tasks", {}):
                del state["tasks"][cli_name]
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"Task cleared for {cli_name}"

def check_cop() -> str:
    """Returns a formatted string of what all other CLIs are doing."""
    _init_cop()
    with open(COP_FILE, "r") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        state = json.loads(f.read())
        fcntl.flock(f, fcntl.LOCK_UN)

    output = ["--- COMMON OPERATING PICTURE (COP) ---"]
    if not state.get("tasks"):
        output.append("No active CLI tasks. The environment is clear.")
    else:
        for cli, data in state["tasks"].items():
            age = int((time.time() - data["timestamp"]) / 60)
            output.append(f"• {cli.upper()} [Active {age}m ago]: {data['description']}")

    if state.get("bounties"):
        output.append("\n--- ACTIVE A2A BOUNTIES ---")
        for b_id, b_data in state["bounties"].items():
            status = b_data.get("status", "open")
            output.append(f"• [{b_id}] {b_data['task']} (Skill needed: {b_data['required_skill']}) - Status: {status}")

    return "\n".join(output)

def lock_resource(cli_name: str, resource_path: str) -> str:
    """Locks a specific file/resource so other CLIs don't edit it."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            _clean_stale(state)
            state.setdefault("locks", {})

            if resource_path in state["locks"] and state["locks"][resource_path]["cli"] != cli_name:
                owner = state["locks"][resource_path]["cli"]
                return f"DENIED: Resource '{resource_path}' is currently locked by {owner.upper()}."

            state["locks"][resource_path] = {
                "cli": cli_name,
                "timestamp": time.time()
            }
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"LOCKED: {resource_path} by {cli_name.upper()}"

def unlock_resource(cli_name: str, resource_path: str) -> str:
    """Unlocks a previously locked resource."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            if resource_path in state.get("locks", {}) and state["locks"][resource_path]["cli"] == cli_name:
                del state["locks"][resource_path]
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"UNLOCKED: {resource_path}"

def post_bounty(requester: str, required_skill: str, task: str, reward: float = 1.0) -> str:
    """A2A Blackboard: Post a sub-task bounty for another specialized agent to pick up."""
    _init_cop()
    bounty_id = f"bounty_{int(time.time())}"
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            _clean_stale(state)
            state.setdefault("bounties", {})[bounty_id] = {
                "requester": requester,
                "required_skill": required_skill,
                "task": task,
                "reward": reward,
                "status": "open",
                "bids": {},
                "timestamp": time.time()
            }
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"Bounty posted: {bounty_id}"

def bid_bounty(bounty_id: str, agent_name: str, est_cost: float) -> str:
    """A2A Blackboard: Place a bid on an open bounty with an estimated resource cost."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())
            if bounty_id not in state.get("bounties", {}):
                return f"ERROR: Bounty '{bounty_id}' not found."

            bounty = state["bounties"][bounty_id]
            if bounty["status"] != "open":
                return f"DENIED: Bounty '{bounty_id}' no longer open."

            bounty.setdefault("bids", {})[agent_name] = {
                "est_cost": est_cost,
                "timestamp": time.time()
            }
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"BID PLACED: @{agent_name.upper()} bid {est_cost} on {bounty_id}"

def claim_bounty(bounty_id: str, agent_name: str) -> str:
    """A2A Blackboard: Claim a posted bounty."""
    _init_cop()
    with open(COP_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.loads(f.read())

            if bounty_id not in state.get("bounties", {}):
                return f"DENIED: Bounty {bounty_id} does not exist."

            if state["bounties"][bounty_id]["status"] != "open":
                return f"DENIED: Bounty {bounty_id} already claimed or completed."

            state["bounties"][bounty_id]["status"] = f"claimed_by_{agent_name}"
            state["bounties"][bounty_id]["claimed_at"] = time.time()
            _atomic_write_cop(state)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return f"SUCCESS: Bounty {bounty_id} claimed by {agent_name}. You may now execute the task."


# ── Process-exit COP cleanup ─────────────────────────────────────────────────

_exit_cli_name: str = ""
_exit_resource_locks: List[str] = []
_exit_handler_registered: bool = False


def register_exit_cleanup(cli_name: str, resource_paths: "List[str] | None" = None) -> None:
    """Register an atexit handler to release this process's COP entries on exit.

    Call once per process after any register_task() or lock_resource() call so
    that orphaned tasks and locks are cleaned up even when the process dies
    unexpectedly (SIGKILL excluded — nothing cleans up after SIGKILL).

    Args:
        cli_name: The CLI name used in register_task() / lock_resource() calls.
        resource_paths: Optional list of resource paths to unlock on exit.
    """
    global _exit_cli_name, _exit_resource_locks, _exit_handler_registered
    _exit_cli_name = cli_name
    _exit_resource_locks = list(resource_paths or [])
    if not _exit_handler_registered:
        atexit.register(_cop_exit_cleanup)
        _exit_handler_registered = True


def _cop_exit_cleanup() -> None:
    """atexit handler: release COP task + locks for this process."""
    if not _exit_cli_name:
        return
    try:
        clear_task(_exit_cli_name)
    except Exception:
        pass
    for res in _exit_resource_locks:
        try:
            unlock_resource(_exit_cli_name, res)
        except Exception:
            pass


# ── COP class (instance-based API) ──────────────────────────────────────────

class COP:
    """Instance-based wrapper around the Common Operating Picture state file.

    Provides task registration, resource locking, and shared blackboard via
    a per-instance state file (suitable for testing and sandboxed environments).

    Args:
        state_file: Path to the JSON state file. Defaults to the global COP_FILE.

    Example::

        cop = COP(state_file="/tmp/my_cop.json")
        cop.register_task("agent-x", "scanning network")
        cop.share("findings", {"open_ports": [22, 443]})
        print(cop.get_shared("findings"))
        cop.clear_task("agent-x")
    """

    def __init__(self, state_file: "str | None" = None) -> None:
        self._state_file = Path(state_file) if state_file else COP_FILE

    def _load(self) -> dict:
        try:
            return json.loads(self._state_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"tasks": {}, "locks": {}, "shared": {}}

    def _save(self, state: dict) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._state_file.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                json.dump(state, fh, indent=2)
            os.replace(tmp_path, self._state_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def register_task(self, cli_name: str, task_description: str) -> str:
        """Register an active task for a CLI."""
        state = self._load()
        state.setdefault("tasks", {})[cli_name] = {
            "description": task_description,
            "timestamp": time.time(),
        }
        self._save(state)
        return f"Task registered for {cli_name}"

    def clear_task(self, cli_name: str) -> str:
        """Clear the active task for a CLI."""
        state = self._load()
        state.get("tasks", {}).pop(cli_name, None)
        self._save(state)
        return f"Task cleared for {cli_name}"

    def status(self) -> str:
        """Return a human-readable summary of active tasks."""
        state = self._load()
        tasks = state.get("tasks", {})
        if not tasks:
            return "No active tasks."
        lines = []
        for cli, data in tasks.items():
            if isinstance(data, dict):
                lines.append(f"{cli}: {data.get('description', '')}")
            else:
                lines.append(f"{cli}: {data}")
        return "\n".join(lines)

    def share(self, key: str, value: object) -> None:
        """Store a value in the shared blackboard."""
        state = self._load()
        state.setdefault("shared", {})[key] = value
        self._save(state)

    def get_shared(self, key: str) -> object:
        """Retrieve a value from the shared blackboard (None if missing)."""
        return self._load().get("shared", {}).get(key)

    def lock_resource(self, cli_name: str, resource_path: str) -> bool:
        """Acquire an exclusive lock on a resource. Returns True if acquired."""
        state = self._load()
        locks = state.setdefault("locks", {})
        current = locks.get(resource_path)
        if current and (isinstance(current, dict) and current.get("cli") != cli_name):
            return False
        locks[resource_path] = {"cli": cli_name, "timestamp": time.time()}
        self._save(state)
        return True

    def unlock_resource(self, cli_name: str, resource_path: str) -> str:
        """Release a resource lock."""
        state = self._load()
        locks = state.get("locks", {})
        entry = locks.get(resource_path)
        if isinstance(entry, dict) and entry.get("cli") == cli_name:
            del locks[resource_path]
            self._save(state)
        return f"Unlocked: {resource_path}"
