"""
Task Ledger — Unified Task Awareness
============================================
Append-only JSONL ledger tracking all task lifecycle events across processes.
Single source of truth for "what is actually running right now?"

Design:
  - File-based (JSONL) for cross-process visibility
  - fcntl locking for concurrent access safety
  - Append-only writes (no corruption from partial writes)
  - Automatic stale task cleanup (configurable TTL)

Events (in order of lifecycle):
  STARTED          — Task dispatched/spawned (records parent_id for sub-task tracking)
  CLAIMED_COMPLETE — Caller asserts done; carries attestation_kind + marker; awaits verification (§14)
  ATTESTED         — task_attestation MCP tool verified the marker; promotes to truly completed
  COMPLETED        — Task finished successfully (legacy path — records completed_unattested when no attestation)
  FAILED           — Task finished with error
  TIMEOUT          — Task exceeded time limit (may still be running)

§14 truth contract (the truth contract (see README)):
  "completed" means BOTH (a) ledger COMPLETED|ATTESTED event recorded AND
  (b) an attestation exists. record_complete() alone leaves the task in
  state=completed_unattested visible via get_active_tasks(). Use
  record_claim_complete() + record_attestation() for verified completion.
"""

import fcntl
import json
import os
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DATA = os.environ.get("TASK_LEDGER_DIR", os.path.expanduser("~/.common-operating-picture/data"))
_LEDGER_PATH = os.path.join(_DEFAULT_DATA, "task_ledger.jsonl")
_STALE_TTL = 3600  # 1 hour — tasks older than this without completion are stale


@dataclass
class TaskEvent:
    task_id: str
    event: str              # STARTED, CLAIMED_COMPLETE, ATTESTED, COMPLETED, FAILED, TIMEOUT
    agent: str = ""
    cli: str = ""           # Which CLI dispatched (claude/gemini/copilot)
    description: str = ""
    parent_id: str = ""     # Parent task ID (for sub-task tracking)
    result_summary: str = ""
    error: str = ""
    # §14 attestation fields (populated on CLAIMED_COMPLETE / ATTESTED events)
    attestation_kind: str = ""    # "file_hash" | "audit_marker" | "daemon_health" | "git_commit"
    attestation_marker: str = ""  # the actual marker payload (e.g. "sha256:xxx:/path")
    attestation_verified: bool = False
    attestation_details: str = "" # JSON-encoded verifier details
    timestamp: float = field(default_factory=time.time)


@dataclass
class ActiveTask:
    task_id: str
    agent: str
    cli: str
    description: str
    parent_id: str
    started_at: float
    elapsed: float = 0.0
    # §14 truth-contract surface — populated by get_active_tasks() based on
    # the latest event for this task_id:
    #   "running"             — STARTED, no later event
    #   "claimed_complete"    — STARTED + CLAIMED_COMPLETE, no ATTESTED yet
    #   "completed_unattested"— STARTED + COMPLETED (legacy path, no attestation)
    #   (terminal "completed" + "failed" + "timeout" are filtered out — not active)
    state: str = "running"
    attestation_kind: str = ""
    attestation_marker: str = ""


class TaskLedger:
    """Cross-process task awareness via append-only JSONL ledger.

    Override ledger path with TASK_LEDGER_DIR env var.
    """

    def __init__(self, ledger_path: str = _LEDGER_PATH) -> None:
        self._path = ledger_path
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.exists(self._path):
            Path(self._path).touch()

    def _append(self, event: TaskEvent) -> None:
        """Append a single event to the ledger with file locking."""
        line = json.dumps(asdict(event), default=str) + "\n"
        try:
            with open(self._path, "a") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            logger.error(f"TaskLedger write failed: {e}")

    def _read_events(self) -> List[TaskEvent]:
        """Read all events from the ledger."""
        events = []
        try:
            with open(self._path, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            events.append(TaskEvent(**d))
                        except (json.JSONDecodeError, TypeError):
                            continue
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.error(f"TaskLedger read failed: {e}")
        return events

    # ── Public API ──────────────────────────────────────────────────────────

    def record_start(
        self,
        agent: str = "",
        cli: str = "",
        description: str = "",
        parent_id: str = "",
        task_id: Optional[str] = None,
    ) -> str:
        """Record a task starting. Returns the task_id."""
        tid = task_id or f"task-{uuid.uuid4().hex[:12]}"
        self._append(TaskEvent(
            task_id=tid,
            event="STARTED",
            agent=agent,
            cli=cli,
            description=description[:200],
            parent_id=parent_id,
        ))
        logger.debug(f"TaskLedger: STARTED {tid} agent={agent} cli={cli}")
        return tid

    def record_complete(
        self, task_id: str, result_summary: str = "", success: bool = True
    ) -> None:
        """
        Record a task completing (success or failure) WITHOUT attestation.

        §14 truth contract: a COMPLETED event without a prior CLAIMED_COMPLETE +
        verified ATTESTED is surfaced by get_active_tasks() as
        state="completed_unattested" — NOT as truly completed. Use this only
        when the legacy single-step path is acceptable (e.g. local read-only
        operations, ephemeral subprocess calls).

        For verified completion (the §14-binding path), use:
          record_claim_complete(task_id, attestation_kind, attestation_marker)
          record_attestation(task_id, kind, marker, verified=True, details=…)
        """
        event = "COMPLETED" if success else "FAILED"
        self._append(TaskEvent(
            task_id=task_id,
            event=event,
            result_summary=result_summary[:500],
            error="" if success else result_summary[:500],
        ))
        logger.debug(f"TaskLedger: {event} {task_id}")

    def record_claim_complete(
        self,
        task_id: str,
        attestation_kind: str = "",
        attestation_marker: str = "",
        result_summary: str = "",
    ) -> None:
        """
        §14 step 1 of 2: caller asserts completion + supplies an attestation
        marker. Task transitions to state="claimed_complete" — visible in
        get_active_tasks() (NOT terminal). A peer CLI MUST verify the marker
        via task_attestation MCP tool, which then calls record_attestation()
        to promote claimed_complete → ATTESTED → effectively completed.

        Empty attestation_kind/marker is allowed for back-compat but the task
        will remain in claimed_complete forever (peer cannot verify nothing).
        """
        self._append(TaskEvent(
            task_id=task_id,
            event="CLAIMED_COMPLETE",
            attestation_kind=attestation_kind,
            attestation_marker=attestation_marker[:500],
            result_summary=result_summary[:500],
        ))
        logger.debug(
            f"TaskLedger: CLAIMED_COMPLETE {task_id} kind={attestation_kind}"
        )

    def record_attestation(
        self,
        task_id: str,
        kind: str,
        marker: str,
        verified: bool,
        details: str = "",
        error: str = "",
    ) -> None:
        """
        §14 step 2 of 2: a peer CLI (via task_attestation MCP tool) verified
        the marker. If verified=True, task is promoted from claimed_complete
        to ATTESTED (terminal — get_active_tasks() will not return it).
        If verified=False, task stays in claimed_complete; the failed
        attestation is logged for audit but does not transition state.
        """
        self._append(TaskEvent(
            task_id=task_id,
            event="ATTESTED",
            attestation_kind=kind,
            attestation_marker=marker[:500],
            attestation_verified=verified,
            attestation_details=details[:1000],
            error=error[:500] if error else "",
        ))
        logger.debug(
            f"TaskLedger: ATTESTED {task_id} kind={kind} verified={verified}"
        )

    def record_timeout(self, task_id: str, elapsed: float = 0.0) -> None:
        """Record a task timeout (may still be running in background)."""
        self._append(TaskEvent(
            task_id=task_id,
            event="TIMEOUT",
            error=f"Exceeded time limit after {elapsed:.0f}s",
        ))
        logger.debug(f"TaskLedger: TIMEOUT {task_id} after {elapsed:.0f}s")

    def get_active_tasks(self, stale_ttl: float = _STALE_TTL) -> List[ActiveTask]:
        """
        Return all tasks that have STARTED but not reached a TRULY terminal
        state. §14 truth contract:
          - state="running"               — STARTED, no later event
          - state="claimed_complete"      — STARTED + CLAIMED_COMPLETE, no verified ATTESTED
          - state="completed_unattested"  — STARTED + COMPLETED, no attestation
        Tasks with verified ATTESTED, FAILED, or TIMEOUT are NOT returned (terminal).
        Excludes tasks older than stale_ttl (default 1 hour).
        """
        events = self._read_events()
        now = time.time()

        # Build event maps per task_id
        started: Dict[str, TaskEvent] = {}
        claimed: Dict[str, TaskEvent] = {}
        attested_verified: set = set()
        legacy_completed: Dict[str, TaskEvent] = {}
        terminal_failed: set = set()

        for ev in events:
            if ev.event == "STARTED":
                started[ev.task_id] = ev
            elif ev.event == "CLAIMED_COMPLETE":
                claimed[ev.task_id] = ev
            elif ev.event == "ATTESTED" and ev.attestation_verified:
                attested_verified.add(ev.task_id)
            elif ev.event == "COMPLETED":
                legacy_completed[ev.task_id] = ev
            elif ev.event in ("FAILED", "TIMEOUT"):
                terminal_failed.add(ev.task_id)

        active: List[ActiveTask] = []
        for tid, ev in started.items():
            if tid in attested_verified or tid in terminal_failed:
                continue
            age = now - ev.timestamp
            if age > stale_ttl:
                continue  # Stale — likely orphaned

            # Determine state per §14 truth contract
            state = "running"
            attestation_kind = ""
            attestation_marker = ""
            if tid in claimed:
                state = "claimed_complete"
                attestation_kind = claimed[tid].attestation_kind
                attestation_marker = claimed[tid].attestation_marker
            elif tid in legacy_completed:
                state = "completed_unattested"

            active.append(ActiveTask(
                task_id=tid,
                agent=ev.agent,
                cli=ev.cli,
                description=ev.description,
                parent_id=ev.parent_id,
                started_at=ev.timestamp,
                elapsed=age,
                state=state,
                attestation_kind=attestation_kind,
                attestation_marker=attestation_marker,
            ))

        return active

    def has_active_subtasks(self, parent_id: str) -> bool:
        """Check if a parent task has any active (non-terminal) sub-tasks."""
        if not parent_id:
            return False
        active = self.get_active_tasks()
        return any(t.parent_id == parent_id for t in active)

    def get_active_for_cli(self, cli: str) -> List[ActiveTask]:
        """Get all active tasks dispatched by a specific CLI."""
        return [t for t in self.get_active_tasks() if t.cli == cli]

    def get_active_for_agent(self, agent: str) -> List[ActiveTask]:
        """Get all active tasks assigned to a specific agent."""
        return [t for t in self.get_active_tasks() if t.agent == agent]

    def compact(self, max_age_days: int = 7) -> int:
        """
        Remove ledger entries older than max_age_days.
        Keeps only recent events to prevent unbounded growth.
        Returns number of entries removed.
        """
        events = self._read_events()
        cutoff = time.time() - (max_age_days * 86400)
        kept = [e for e in events if e.timestamp >= cutoff]
        removed = len(events) - len(kept)

        if removed > 0:
            try:
                tmp_path = self._path + ".tmp"
                with open(tmp_path, "w") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        for ev in kept:
                            f.write(json.dumps(asdict(ev), default=str) + "\n")
                        f.flush()
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                os.replace(tmp_path, self._path)
                logger.info(f"TaskLedger: compacted {removed} old entries")
            except OSError as e:
                logger.error(f"TaskLedger compact failed: {e}")
                removed = 0

        return removed

    def summary(self) -> Dict:
        """Get a summary of the ledger state with §14 truth-contract fields."""
        active = self.get_active_tasks()
        events = self._read_events()
        # §14: ATTESTED with verified=True is the ONLY truly-completed terminal.
        # COMPLETED is a legacy completion that has not been attested.
        attested_complete = sum(
            1 for e in events if e.event == "ATTESTED" and e.attestation_verified
        )
        completed_unattested = sum(1 for e in events if e.event == "COMPLETED")
        claimed_pending = sum(
            1 for t in active if t.state == "claimed_complete"
        )
        failed = sum(1 for e in events if e.event == "FAILED")
        timeouts = sum(1 for e in events if e.event == "TIMEOUT")
        return {
            "active_tasks": len(active),
            "active_by_state": {
                "running": sum(1 for t in active if t.state == "running"),
                "claimed_complete": claimed_pending,
                "completed_unattested": sum(
                    1 for t in active if t.state == "completed_unattested"
                ),
            },
            "attested_complete_total": attested_complete,
            "completed_unattested_total": completed_unattested,
            "failed_total": failed,
            "timeout_total": timeouts,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "agent": t.agent,
                    "cli": t.cli,
                    "description": t.description,
                    "elapsed": f"{t.elapsed:.0f}s",
                    "parent_id": t.parent_id or None,
                    "state": t.state,
                    "attestation_kind": t.attestation_kind or None,
                    "attestation_marker": t.attestation_marker or None,
                }
                for t in active
            ],
        }


# ── Module-level singleton ──────────────────────────────────────────────────

_ledger: Optional[TaskLedger] = None


def get_ledger() -> TaskLedger:
    """Get the global TaskLedger instance."""
    global _ledger
    if _ledger is None:
        _ledger = TaskLedger()
    return _ledger
