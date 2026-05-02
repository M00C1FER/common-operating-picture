# Common Operating Picture (COP)

> Lightweight shared-state bus for multi-CLI/multi-agent coordination — prevent task collisions with atomic file locking and A2A blackboards.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL%20%7C%20Termux-lightgrey)](install.sh)

## What It Does

When multiple AI CLIs run concurrently (Claude Code, Gemini CLI, Copilot CLI), they can clobber each other's file edits. COP solves this with a JSON state file, `fcntl`-based exclusive locking, and an agent-to-agent blackboard that lets participants register tasks, claim resources, and broadcast findings without a central server.

**Key capabilities:**
- Atomic read-modify-write on shared state (`cop_state.json`)
- Task registration and conflict detection across agents/CLIs
- Resource locking with automatic atexit cleanup
- A2A blackboard for sharing intermediate findings between agents
- Zero external dependencies — pure Python stdlib

## Quick Start

```bash
bash install.sh
cop status
cop register --cli myapp --task "build the parser"
cop lock ./src/parser.py --cli myapp
# ... do work ...
cop unlock ./src/parser.py --cli myapp
cop clear --cli myapp
```

## Installation

| Platform | Method |
|----------|--------|
| Linux / WSL | `bash install.sh` |
| Termux (Android) | `bash install.sh` (no sudo) |
| pip | `pip install .` |

```bash
git clone https://github.com/M00C1FER/common-operating-picture
cd common-operating-picture
bash install.sh
```

## Usage

```python
from common_operating_picture import COP

cop = COP()

# Register a task
cop.register_task("agent-1", "Refactor auth module")

# Check for conflicts before editing a file
status = cop.status()
print(status)

# Lock a resource
if cop.lock_resource("agent-1", "./src/auth.py"):
    # ... do edits ...
    cop.unlock_resource("agent-1", "./src/auth.py")

# Share a finding via blackboard
cop.share("auth_pattern", "JWT with RS256")
finding = cop.get_shared("auth_pattern")

# Clear task on completion
cop.clear_task("agent-1")
```

## Architecture (MOSA)

```
common-operating-picture/
├── src/common_operating_picture/
│   ├── cop.py             # COP state manager + blackboard
│   └── __init__.py
├── install.sh             # Cross-platform wizard
├── examples/demo.py       # Two-agent coordination demo
└── TOOLS.md
```

**Go refactor candidate:** COP's locking primitives map directly to Go's `sync.Mutex` + `os.File` locking, with better cross-platform support than Python's `fcntl` (which doesn't work on Windows native).

## Cross-Platform Notes

- **Linux/WSL:** `fcntl` exclusive locks (LOCK_EX via `flock(2)`)
- **macOS:** `fcntl.flock` maps to advisory locks — semantics match Linux for local filesystems; not reliable over NFS
- **Termux:** `fcntl` supported (Android kernel exposes POSIX file-locking)
- **Alpine Linux:** supported via `apk` — see `install.sh`; musl libc fully supports `fcntl`/`flock`
- **Windows native:** `fcntl` unavailable — use WSL2 (Ubuntu base works out of the box)

### Stale lock recovery

Application-level locks in `cop_state.json` (`locks` dict) survive process crashes
because they are stored in the JSON, not in kernel state. The `_clean_stale()` routine
removes entries older than the configured timeout (default 7200 s / 2 h). Stale locks
can also be cleared manually with `cop unlock <resource> --cli <owner>`.

The `fcntl.flock` that guards the read-modify-write cycle is process-scoped: the OS
releases it automatically when the process exits or crashes, so the JSON file itself
is never permanently wedged.

## Tools Reference

See [TOOLS.md](TOOLS.md).

## License

[MIT](LICENSE)
