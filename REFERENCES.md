# Reference Projects Studied

Projects examined as design and implementation references for COP's
process-safe coordination primitives and cross-platform packaging.

| # | Project | Stars | License | Pattern noted |
|---|---------|-------|---------|---------------|
| 1 | [filelock](https://github.com/tox-dev/filelock) | ≥1 k | MIT | Uses a dedicated lock *file* (separate from the data file) so LOCK_EX covers the entire open→write→close cycle; avoids the rename-across-lock problem. **Applied**: COP's `_locked_read_modify_write` now uses `fcntl.flock(LOCK_EX)` on the open state file handle for the full RMW cycle. |
| 2 | [redis-py](https://github.com/redis/redis-py) | ≥12 k | MIT | Exposes both a module-level functional API *and* an instance-based `Redis` class from one source module; instance holds connection state, module functions are convenience wrappers. **Applied**: COP mirrors this pattern — module-level functions (`register_task`, `lock_resource`, …) operate on the global `COP_FILE`; the `COP` class carries its own `_state_file` path. |
| 3 | [apscheduler](https://github.com/agronholm/apscheduler) | ≥13 k | MIT | Uses `atexit` + signal handlers to clean up scheduler state when the host process dies; documents SIGKILL as a known gap. **Applied**: COP's `register_exit_cleanup` / `_cop_exit_cleanup` follow the same pattern; the README now documents the SIGKILL gap explicitly. |
| 4 | [python-dotenv](https://github.com/theskumar/python-dotenv) | ≥8 k | BSD-3 | Env-var config values are read via `os.environ.get(KEY, default)`, not via shell-expansion functions like `os.path.expanduser("${VAR}")`. **Applied**: Fixed `_get_timeouts()` which incorrectly used `expanduser("${COP_CONFIG}")`. |
| 5 | [portalocker](https://github.com/WoLpH/portalocker) | ≥1 k | BSD-3 | Documents platform differences: `fcntl.flock` on Linux/macOS is advisory and process-scoped (OS releases on process exit/crash); on Windows a different code path uses `msvcrt.locking`. **Applied**: COP's README and inline docstrings now explicitly describe the fcntl process-scope guarantee (crash safety) and the macOS NFS advisory-only caveat. |
