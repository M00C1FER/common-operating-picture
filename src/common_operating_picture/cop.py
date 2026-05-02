import atexit
import json
import os
import sys
import tempfile
import time
import fcntl
from pathlib import Path
from typing import List, Tuple

COP_HOME = Path(os.environ.get("COP_HOME", os.path.expanduser("~/.common-operating-picture")))
COP_FILE = Path(os.environ.get("COP_STATE_FILE", str(COP_HOME / "cop_state.json")))

__version__ = "1.0.0"

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
        config_path = os.environ.get("COP_CONFIG", "")
        if not config_path:
            return 7200, 7200, 86400
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
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        # Ensure file exists so we can open it for read+write locking
        if not self._state_file.exists():
            self._state_file.write_text(
                json.dumps({"tasks": {}, "locks": {}, "shared": {}})
            )

    def _locked_read_modify_write(self, fn):
        """Open the state file, acquire an exclusive fcntl lock, run fn(state),
        write the result atomically, then release the lock.

        This is the single safe entry-point for all mutating operations so that
        two concurrent processes never interleave their read-modify-write cycles.
        On Linux and macOS, LOCK_EX via fcntl.flock is process-scoped: if the
        lock holder exits (crash/SIGKILL), the OS releases the lock automatically,
        so no manual stale-lock recovery is needed at the fcntl level.
        Application-level locks stored in the JSON ``locks`` dict ARE cleaned up
        via ``_clean_stale()`` based on configurable timeouts.

        macOS note: ``fcntl.flock`` on macOS converts to an advisory lock
        equivalent to Linux. The semantics match for our use-case (exclusive
        writer, no NFS mounts).
        """
        with open(self._state_file, "r+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                try:
                    state = json.loads(fh.read())
                except (json.JSONDecodeError, ValueError):
                    state = {"tasks": {}, "locks": {}, "shared": {}}
                result = fn(state)
                # Atomic write: temp file + os.replace (same filesystem)
                tmp_fd, tmp_path = tempfile.mkstemp(
                    dir=self._state_file.parent, suffix=".tmp"
                )
                try:
                    with os.fdopen(tmp_fd, "w") as out:
                        json.dump(state, out, indent=2)
                    os.replace(tmp_path, self._state_file)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
                return result
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _locked_read(self):
        """Shared-lock read of state (safe for concurrent readers)."""
        with open(self._state_file, "r") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                try:
                    return json.loads(fh.read())
                except (json.JSONDecodeError, ValueError):
                    return {"tasks": {}, "locks": {}, "shared": {}}
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def register_task(self, cli_name: str, task_description: str) -> str:
        """Register an active task for a CLI."""
        def _mutate(state):
            state.setdefault("tasks", {})[cli_name] = {
                "description": task_description,
                "timestamp": time.time(),
            }
        self._locked_read_modify_write(_mutate)
        return f"Task registered for {cli_name}"

    def clear_task(self, cli_name: str) -> str:
        """Clear the active task for a CLI."""
        def _mutate(state):
            state.get("tasks", {}).pop(cli_name, None)
        self._locked_read_modify_write(_mutate)
        return f"Task cleared for {cli_name}"

    def status(self) -> str:
        """Return a human-readable summary of active tasks."""
        state = self._locked_read()
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
        def _mutate(state):
            state.setdefault("shared", {})[key] = value
        self._locked_read_modify_write(_mutate)

    def get_shared(self, key: str) -> object:
        """Retrieve a value from the shared blackboard (None if missing)."""
        return self._locked_read().get("shared", {}).get(key)

    def lock_resource(self, cli_name: str, resource_path: str) -> bool:
        """Acquire an exclusive application-level lock on a resource.

        Returns True if the lock was acquired; False if another CLI holds it.
        Uses fcntl.flock for the read-modify-write so two processes cannot
        race when evaluating the same resource_path simultaneously.
        """
        acquired = [False]

        def _mutate(state):
            _clean_stale(state)
            locks = state.setdefault("locks", {})
            current = locks.get(resource_path)
            if current and isinstance(current, dict) and current.get("cli") != cli_name:
                acquired[0] = False
                return
            locks[resource_path] = {"cli": cli_name, "timestamp": time.time()}
            acquired[0] = True

        self._locked_read_modify_write(_mutate)
        return acquired[0]

    def unlock_resource(self, cli_name: str, resource_path: str) -> str:
        """Release a resource lock held by cli_name."""
        def _mutate(state):
            locks = state.get("locks", {})
            entry = locks.get(resource_path)
            if isinstance(entry, dict) and entry.get("cli") == cli_name:
                del locks[resource_path]
        self._locked_read_modify_write(_mutate)
        return f"Unlocked: {resource_path}"


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point: ``cop <subcommand> [args]``."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="cop",
        description="Common Operating Picture — shared state bus for multi-agent ops",
    )
    parser.add_argument("--version", action="version", version=f"cop {__version__}")

    sub = parser.add_subparsers(dest="cmd", metavar="<command>")

    # status
    sub.add_parser("status", help="Show active tasks and locks")

    # register
    p_reg = sub.add_parser("register", help="Register a task")
    p_reg.add_argument("--cli", required=True, help="CLI/agent name")
    p_reg.add_argument("--task", required=True, help="Task description")

    # clear
    p_clr = sub.add_parser("clear", help="Clear a task")
    p_clr.add_argument("--cli", required=True, help="CLI/agent name")

    # lock
    p_lock = sub.add_parser("lock", help="Lock a resource")
    p_lock.add_argument("resource", help="Resource path or name")
    p_lock.add_argument("--cli", required=True, help="CLI/agent name")

    # unlock
    p_unlock = sub.add_parser("unlock", help="Unlock a resource")
    p_unlock.add_argument("resource", help="Resource path or name")
    p_unlock.add_argument("--cli", required=True, help="CLI/agent name")

    # blackboard get/set
    p_bb_set = sub.add_parser("bb-set", help="Set a blackboard key")
    p_bb_set.add_argument("key", help="Key name")
    p_bb_set.add_argument("value", help="JSON-encoded value")
    p_bb_set.add_argument("--cli", default="cli", help="CLI/agent name")

    p_bb_get = sub.add_parser("bb-get", help="Get a blackboard key")
    p_bb_get.add_argument("key", help="Key name")

    args = parser.parse_args()

    cop = COP()

    if args.cmd == "status":
        print(cop.status())
    elif args.cmd == "register":
        print(cop.register_task(args.cli, args.task))
    elif args.cmd == "clear":
        print(cop.clear_task(args.cli))
    elif args.cmd == "lock":
        ok = cop.lock_resource(args.cli, args.resource)
        if ok:
            print(f"LOCKED: {args.resource} by {args.cli.upper()}")
        else:
            print(f"DENIED: {args.resource} is locked by another agent")
            sys.exit(1)
    elif args.cmd == "unlock":
        print(cop.unlock_resource(args.cli, args.resource))
    elif args.cmd == "bb-set":
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value
        cop.share(args.key, value)
        print(f"SET: {args.key}")
    elif args.cmd == "bb-get":
        result = cop.get_shared(args.key)
        print(json.dumps(result, indent=2) if result is not None else "null")
    else:
        parser.print_help()
        sys.exit(1)
